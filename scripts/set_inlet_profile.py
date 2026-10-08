#!/usr/bin/env python3
"""Write a fully developed rectangular-duct inlet on the fluid region.

Area-average speed matches Qin / A_inlet. k and omega follow local |U|
(I = 5 %, mixing length 0.07 Dh). For kOmegaSSTLM, gammaInt = 1 and
ReThetat uses the Langtry–Menter freestream correlation from local Tu.
Avoids codedFixedValue so Docker can run.
"""
from __future__ import annotations

import importlib.util
import math
import re
from pathlib import Path

CASE = Path(__file__).resolve().parents[1]
MESH = CASE / "constant" / "fluid" / "polyMesh"
H = 0.010
I_TURB = 0.05
CMU = 0.09
NTERMS = 21


def load_params():
    spec = importlib.util.spec_from_file_location(
        "case_params", CASE / "scripts" / "case_params.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _list_body(text: str) -> tuple[int, str]:
    m = re.search(r"\n(\d+)\s*\n\(", text)
    if not m:
        raise RuntimeError("No sized list in polyMesh file")
    return int(m.group(1)), text[m.end() - 1 :]


def read_points(path: Path) -> list[tuple[float, float, float]]:
    n, body = _list_body(path.read_text())
    pts = [
        (float(m.group(1)), float(m.group(2)), float(m.group(3)))
        for m in re.finditer(
            r"\(\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\)",
            body,
        )
    ]
    if len(pts) != n:
        raise RuntimeError(f"points: expected {n}, got {len(pts)}")
    return pts


def read_faces(path: Path) -> list[list[int]]:
    n, body = _list_body(path.read_text())
    faces = []
    for m in re.finditer(r"(\d+)\s*\(([^)]*)\)", body):
        ids = [int(v) for v in m.group(2).split()]
        if int(m.group(1)) != len(ids):
            continue
        faces.append(ids)
    if len(faces) != n:
        raise RuntimeError(f"faces: expected {n}, got {len(faces)}")
    return faces


def read_patch(path: Path, name: str) -> tuple[int, int]:
    text = path.read_text()
    m = re.search(
        rf"{re.escape(name)}\s*\{{(.*?)\}}",
        text,
        re.S,
    )
    if not m:
        raise RuntimeError(f"Patch {name} not found")
    block = m.group(1)
    n = int(re.search(r"nFaces\s+(\d+)", block).group(1))
    start = int(re.search(r"startFace\s+(\d+)", block).group(1))
    return n, start


def face_centre_area(
    verts: list[tuple[float, float, float]],
) -> tuple[tuple[float, float, float], float]:
    n = len(verts)
    cx = sum(p[0] for p in verts) / n
    cy = sum(p[1] for p in verts) / n
    cz = sum(p[2] for p in verts) / n
    area = 0.0
    for i in range(n):
        x1, y1, z1 = verts[i]
        x2, y2, z2 = verts[(i + 1) % n]
        area += math.hypot(
            (y1 - cy) * (z2 - cz) - (z1 - cz) * (y2 - cy),
            (z1 - cz) * (x2 - cx) - (x1 - cx) * (z2 - cz),
            (x1 - cx) * (y2 - cy) - (y1 - cy) * (x2 - cx),
        )
    return (cx, cy, cz), 0.5 * area


def uy_shape(xi: float, eta: float, width: float, height: float) -> float:
    xi = min(max(xi, 1e-9), 1.0 - 1e-9)
    eta = min(max(eta, 1e-9), 1.0 - 1e-9)
    s = 0.0
    for i in range(1, NTERMS, 2):
        for j in range(1, NTERMS, 2):
            s += (
                math.sin(i * math.pi * xi)
                * math.sin(j * math.pi * eta)
                / (i * j * ((i / width) ** 2 + (j / height) ** 2))
            )
    return max(s, 0.0)


def replace_patch_list(path: Path, patch: str, kind: str, body: str) -> None:
    text = path.read_text()
    pat = re.compile(
        rf"({re.escape(patch)}\s*\{{.*?type\s+\S+;\s*)value\s+.*?;",
        re.S,
    )

    def repl(m: re.Match) -> str:
        return m.group(1) + f"value           nonuniform List<{kind}>\n    " + body + ";"

    new, n = pat.subn(repl, text, count=1)
    if n != 1:
        raise RuntimeError(f"Could not patch {patch} in {path}")
    path.write_text(new)


def main() -> None:
    p = load_params()
    xin_lo = p.Xin - 0.5 * p.Win
    width, height = p.Win, H
    dh = 2.0 * width * height / (width + height)
    mix_l = 0.07 * dh
    cmu25 = CMU**0.25

    points = read_points(MESH / "points")
    faces = read_faces(MESH / "faces")
    n_faces, start = read_patch(MESH / "boundary", "inlet")
    inlet = faces[start : start + n_faces]

    raw = []
    areas = []
    for ids in inlet:
        verts = [points[i] for i in ids]
        (x, _y, z), a = face_centre_area(verts)
        xi = (x - xin_lo) / width
        eta = z / height
        raw.append(uy_shape(xi, eta, width, height))
        areas.append(a)

    flux_raw = sum(u * a for u, a in zip(raw, areas))
    if flux_raw <= 0:
        raise RuntimeError("Inlet profile integral is zero")
    scale = p.Qin / flux_raw
    uys = [u * scale for u in raw]
    area = sum(areas)
    u_mean = sum(u * a for u, a in zip(uys, areas)) / area

    def re_thetat(tu_pct: float) -> float:
        """Langtry–Menter freestream Re_θt from turbulence intensity Tu [%]."""
        tu = max(tu_pct, 0.027)
        if tu <= 1.3:
            return 1173.51 - 589.428 * tu + 0.2196 * tu * tu
        return 331.50 * (tu - 0.5658) ** (-0.671)

    ks = []
    omegas = []
    gammas = []
    rets = []
    for uy in uys:
        k = max(1.5 * (I_TURB * uy) ** 2, 1e-8)
        omega = math.sqrt(k) / (cmu25 * mix_l)
        tu_pct = 100.0 * math.sqrt(2.0 * k / 3.0) / max(uy, 1e-6)
        ks.append(k)
        omegas.append(omega)
        gammas.append(1.0)
        rets.append(re_thetat(tu_pct))

    n = len(uys)
    u_body = (
        f"{n}\n    (\n"
        + "".join(f"        (0 {uy:.8e} 0)\n" for uy in uys)
        + "    )"
    )
    k_body = f"{n}\n    (\n" + "".join(f"        {v:.8e}\n" for v in ks) + "    )"
    w_body = f"{n}\n    (\n" + "".join(f"        {v:.8e}\n" for v in omegas) + "    )"
    g_body = f"{n}\n    (\n" + "".join(f"        {v:.8e}\n" for v in gammas) + "    )"
    r_body = f"{n}\n    (\n" + "".join(f"        {v:.8e}\n" for v in rets) + "    )"

    fluid0 = CASE / "0" / "fluid"
    replace_patch_list(fluid0 / "U", "inlet", "vector", u_body)
    replace_patch_list(fluid0 / "k", "inlet", "scalar", k_body)
    replace_patch_list(fluid0 / "omega", "inlet", "scalar", w_body)
    if (fluid0 / "gammaInt").is_file():
        replace_patch_list(fluid0 / "gammaInt", "inlet", "scalar", g_body)
    if (fluid0 / "ReThetat").is_file():
        replace_patch_list(fluid0 / "ReThetat", "inlet", "scalar", r_body)

    print(
        f"Fully-developed inlet: {n} faces, A={area:.4e} m2, "
        f"Q={p.Qin:.3e} m3/s, Umean={u_mean:.3f} m/s, Umax={max(uys):.3f} m/s, "
        f"ReThetat~{sum(rets)/len(rets):.0f}"
    )


if __name__ == "__main__":
    main()
