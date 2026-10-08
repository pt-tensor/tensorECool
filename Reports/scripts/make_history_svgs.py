#!/usr/bin/env python3
"""Plot residuals, PBGA ΔT, and Vave vs iteration (Hatakeyama cases).

Reads:
  log.buoyantBoussinesqSimpleFoam
  postProcessing/heaterT/*/surfaceFieldValue.dat
  postProcessing/inletT/*/surfaceFieldValue.dat
  postProcessing/validationLines/<time>/line_Uy_Y{80,100,120}_T_U.xy

Writes:
  Reports/data/residuals.csv
  Reports/data/deltaT_history.csv
  Reports/data/Vave_history.csv
  Reports/figures/residuals.svg
  Reports/figures/deltaT_history.svg
  Reports/figures/Vave_history.svg

Usage (from case root):
  python3 Reports/scripts/make_history_svgs.py
"""
from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

CASE = Path(__file__).resolve().parents[2]
LOG_NAME = "log.chtMultiRegionSimpleFoam"
PKG = (0.0775, 0.1225)  # PBGA xy [m]
PKG_Y_MM = (80, 100, 120)  # sample lines that cut the package at Z=7 mm

SERIES = (
    ("Ux", "#1f77b4"),
    ("Uy", "#ff7f0e"),
    ("Uz", "#2ca02c"),
    ("h", "#d62728"),
    ("p_rgh", "#9467bd"),
)

TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)\s*$", re.M)
RES_RE = re.compile(
    r"Solving for (Ux|Uy|Uz|h|T|p_rgh), Initial residual = ([0-9.eE+-]+)"
)


def parse_residuals(path: Path) -> list[dict[str, float]]:
    text = path.read_text(errors="replace")
    time_matches = list(TIME_RE.finditer(text))
    rows: list[dict[str, float]] = []
    for i, tm in enumerate(time_matches):
        t = float(tm.group(1))
        start = tm.start()
        end = time_matches[i + 1].start() if i + 1 < len(time_matches) else len(text)
        block = text[start:end]
        row: dict[str, float] = {"time": t}
        for m in RES_RE.finditer(block):
            key = m.group(1)
            if key not in row:
                row[key] = float(m.group(2))
        if len(row) > 1:
            rows.append(row)
    by_t = {r["time"]: r for r in rows}
    return [by_t[t] for t in sorted(by_t)]


def read_surface(root: Path) -> dict[float, float]:
    out: dict[float, float] = {}
    if not root.is_dir():
        return out
    files = [
        p
        for p in list(root.glob("*/volFieldValue*.dat"))
        + list(root.glob("*/surfaceFieldValue*.dat"))
        if p.is_file() and p.stat().st_size > 80
    ]
    for path in files:
        for line in path.read_text(errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            if len(parts) < 2:
                continue
            try:
                out[float(parts[0])] = float(parts[-1])
            except ValueError:
                continue
    return out


def load_uy_line(path: Path) -> list[tuple[float, float, float]]:
    """Return (x, Uy, |U|) rows."""
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        p = [float(v) for v in line.split()]
        if len(p) >= 7:
            x, ux, uy, uz = p[0], p[4], p[5], p[6]
        elif len(p) >= 5:
            x, ux, uy, uz = p[0], p[2], p[3], p[4]
        else:
            continue
        mag = math.sqrt(ux * ux + uy * uy + uz * uz)
        rows.append((x, uy, mag))
    return rows


def vave_over_pbga(sets_dir: Path) -> float | None:
    mags: list[float] = []
    for y in PKG_Y_MM:
        rows = load_uy_line(sets_dir / f"line_Uy_Y{y}_T_U.xy")
        if not rows:
            rows = load_uy_line(sets_dir / f"line_Uy_Y{y}_U.xy")
        for x, _uy, mag in rows:
            if PKG[0] <= x <= PKG[1]:
                mags.append(mag)
    if not mags:
        return None
    return sum(mags) / len(mags)


def parse_vave(case: Path) -> list[tuple[float, float]]:
    bases = [case / "postProcessing" / "validationLines"]
    nested = case / "postProcessing" / "validationLines" / "fluid"
    if nested.is_dir():
        bases.append(nested)
    out = []
    for base in bases:
        if not base.is_dir():
            continue
        for p in base.iterdir():
            if not p.is_dir():
                continue
            try:
                t = float(p.name)
            except ValueError:
                continue
            v = vave_over_pbga(p)
            if v is not None:
                out.append((t, v))
    out.sort()
    return out


def parse_deltaT(case: Path) -> list[tuple[float, float]]:
    post = case / "postProcessing"
    th = read_surface(post / "packageT")
    if not th:
        th = read_surface(post / "PBGA" / "packageT")
    ti = read_surface(post / "inletT")
    if not ti:
        ti = read_surface(post / "fluid" / "inletT")
    times = sorted(th)
    rows = []
    for t in times:
        t_i = ti.get(t, 300.0)
        rows.append((t, th[t] - t_i))
    return rows


def write_xy_csv(path: Path, header: list[str], rows: list[tuple[float, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for a, b in rows:
            w.writerow([f"{a:.8g}", f"{b:.8g}"])


def log_ticks(ymin: float, ymax: float) -> list[float]:
    if ymin <= 0 or ymax <= 0 or ymax < ymin:
        return [1e-6, 1e-3, 1.0]
    e0 = math.floor(math.log10(ymin))
    e1 = math.ceil(math.log10(ymax))
    return [10.0**e for e in range(e0, e1 + 1)]


def nice_ticks(a: float, b: float, n: int = 6) -> list[float]:
    if b <= a:
        return [a]
    span = b - a
    step = 10 ** math.floor(math.log10(span / max(n - 1, 1)))
    for m in (1.0, 2.0, 2.5, 5.0, 10.0):
        if span / (m * step) <= n:
            step *= m
            break
    start = math.ceil(a / step - 1e-12) * step
    ticks = []
    x = start
    while x <= b + 0.5 * step:
        if a - 1e-9 <= x <= b + 1e-9:
            ticks.append(x)
        x += step
    return ticks or [a, b]


def fmt_sci(v: float) -> str:
    if v == 0:
        return "0"
    exp = int(math.floor(math.log10(abs(v))))
    mant = v / (10.0**exp)
    if abs(mant - 1.0) < 1e-9:
        return f"10^{exp}"
    return f"{mant:g}×10^{exp}"


def svg_header(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{title}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="26" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="14" font-weight="600" fill="#111">'
        f"{title}</text>",
    ]


def write_residual_svg(path: Path, rows: list[dict[str, float]], title: str) -> None:
    width, height = 820, 480
    ml, mr, mt, mb = 72, 160, 44, 52
    pw, ph = width - ml - mr, height - mt - mb
    times = [r["time"] for r in rows]
    xmin, xmax = min(times), max(times)
    if xmax <= xmin:
        xmax = xmin + 1.0
    vals = [r[k] for r in rows for k, _ in SERIES if k in r and r[k] > 0]
    if not vals:
        path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">'
            f'<text x="20" y="40">No residuals in log</text></svg>\n'
        )
        return
    ymin = max(min(vals) / 2.0, 1e-12)
    ymax = max(vals) * 2.0

    def X(t: float) -> float:
        return ml + (t - xmin) / (xmax - xmin) * pw

    def Y(v: float) -> float:
        v = max(v, ymin)
        return mt + (
            1.0
            - (math.log10(v) - math.log10(ymin))
            / (math.log10(ymax) - math.log10(ymin))
        ) * ph

    parts = svg_header(width, height, title)
    parts += [
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#333" stroke-width="1.2"/>',
        f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#333" stroke-width="1.2"/>',
        f'<text x="{ml-10}" y="{mt-8}" text-anchor="end" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#444">initial residual</text>',
        f'<text x="{ml+pw/2:.1f}" y="{height-14}" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#444">iteration</text>',
    ]
    for yv in log_ticks(ymin, ymax):
        if yv < ymin * 0.999 or yv > ymax * 1.001:
            continue
        yy = Y(yv)
        parts.append(
            f'<line x1="{ml}" y1="{yy:.2f}" x2="{ml+pw}" y2="{yy:.2f}" stroke="#eee" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ml-8}" y="{yy+3:.2f}" text-anchor="end" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#555">{fmt_sci(yv)}</text>'
        )
    for i in range(9):
        t = xmin + (xmax - xmin) * i / 8
        xx = X(t)
        parts.append(
            f'<line x1="{xx:.2f}" y1="{mt}" x2="{xx:.2f}" y2="{mt+ph}" stroke="#f3f3f3" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{xx:.2f}" y="{mt+ph+16}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#555">{t:.0f}</text>'
        )
    for key, color in SERIES:
        pts = [(r["time"], r[key]) for r in rows if key in r and r[key] > 0]
        if len(pts) < 2:
            continue
        if len(pts) > 2500:
            step = max(1, len(pts) // 2000)
            pts = pts[::step] + [pts[-1]]
        d = " ".join(
            f"{'M' if i == 0 else 'L'}{X(t):.2f},{Y(v):.2f}" for i, (t, v) in enumerate(pts)
        )
        parts.append(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round" opacity="0.92"/>'
        )
    lx, ly = ml + pw + 16, mt + 8
    parts.append(
        f'<text x="{lx}" y="{ly}" font-family="Helvetica,Arial,sans-serif" '
        f'font-size="11" font-weight="600" fill="#222">fields</text>'
    )
    for i, (key, color) in enumerate(SERIES):
        y = ly + 18 + i * 18
        parts.append(
            f'<line x1="{lx}" y1="{y}" x2="{lx+22}" y2="{y}" stroke="{color}" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{lx+28}" y="{y+4}" font-family="Helvetica,Arial,sans-serif" '
            f'font-size="11" fill="#222">{key}</text>'
        )
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def load_exp_deltaT(case: Path) -> float | None:
    """Experimental package ΔT [K] from fig7.csv for this Xin."""
    import importlib.util

    params = case / "scripts" / "case_params.py"
    fig7 = case / "Reports" / "data" / "experiment" / "fig7.csv"
    if not params.is_file() or not fig7.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("case_params", params)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        xin_mm = int(round(float(mod.Xin) * 1000))
    except Exception:  # noqa: BLE001
        return None
    for line in fig7.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.lower().startswith("xin"):
            continue
        parts = s.split(",")
        if len(parts) < 2:
            continue
        try:
            if int(round(float(parts[0]))) == xin_mm:
                return float(parts[1])
        except ValueError:
            continue
    return None


def write_linear_svg(
    path: Path,
    rows: list[tuple[float, float]],
    *,
    title: str,
    ylabel: str,
    color: str,
    ymin0: float | None = None,
    ymax0: float | None = None,
    markers: bool = False,
    target: float | None = None,
    target_label: str = "target (exp)",
) -> None:
    width, height = 820, 420
    ml, mr, mt, mb = 72, 28, 44, 52
    pw, ph = width - ml - mr, height - mt - mb
    times = [t for t, _ in rows]
    vals = [v for _, v in rows]
    xmin, xmax = min(times), max(times)
    if xmax <= xmin:
        xmax = xmin + 1.0
    ymin = min(vals) if ymin0 is None else ymin0
    ymax = max(vals) if ymax0 is None else ymax0
    if target is not None:
        ymax = max(ymax, target)
        if ymin0 is None:
            ymin = min(ymin, target)
    pad = 0.08 * (ymax - ymin if ymax > ymin else 1.0)
    if ymin0 is None:
        ymin -= pad
    if ymax0 is None:
        ymax += pad
    if target is not None and ymax0 is None:
        # Keep target inside the frame with a little headroom.
        ymax = max(ymax, target + pad)
    if ymin == ymax:
        ymax = ymin + 1.0

    def X(t: float) -> float:
        return ml + (t - xmin) / (xmax - xmin) * pw

    def Y(v: float) -> float:
        return mt + (1.0 - (v - ymin) / (ymax - ymin)) * ph

    parts = svg_header(width, height, title)
    parts += [
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#333" stroke-width="1.2"/>',
        f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#333" stroke-width="1.2"/>',
        f'<text x="{ml-36}" y="{mt+ph/2:.1f}" text-anchor="middle" '
        f'transform="rotate(-90 {ml-36} {mt+ph/2:.1f})" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#444">{ylabel}</text>',
        f'<text x="{ml+pw/2:.1f}" y="{height-14}" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#444">iteration</text>',
    ]
    for xv in nice_ticks(xmin, xmax, 8):
        xx = X(xv)
        parts.append(
            f'<line x1="{xx:.2f}" y1="{mt}" x2="{xx:.2f}" y2="{mt+ph}" stroke="#eee" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{xx:.2f}" y="{mt+ph+16}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#555">{xv:g}</text>'
        )
    for yv in nice_ticks(ymin, ymax, 6):
        yy = Y(yv)
        parts.append(
            f'<line x1="{ml}" y1="{yy:.2f}" x2="{ml+pw}" y2="{yy:.2f}" stroke="#eee" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ml-8}" y="{yy+3:.2f}" text-anchor="end" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#555">{yv:g}</text>'
        )
    if target is not None and ymin <= target <= ymax:
        yy = Y(target)
        parts.append(
            f'<line x1="{ml}" y1="{yy:.2f}" x2="{ml+pw}" y2="{yy:.2f}" '
            f'stroke="#2c3e50" stroke-width="1.6" stroke-dasharray="8 5" opacity="0.9"/>'
        )
        parts.append(
            f'<text x="{ml+pw-4:.1f}" y="{yy-5:.2f}" text-anchor="end" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#2c3e50">'
            f"{target_label}: {target:.2f} K</text>"
        )
    d = " ".join(
        f"{'M' if i == 0 else 'L'}{X(t):.2f},{Y(v):.2f}" for i, (t, v) in enumerate(rows)
    )
    parts.append(
        f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2.0" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
    )
    if markers:
        for t, v in rows:
            parts.append(
                f'<circle cx="{X(t):.2f}" cy="{Y(v):.2f}" r="3.2" fill="{color}"/>'
            )
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> int:
    case = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else CASE
    fig = case / "Reports" / "figures"
    data = case / "Reports" / "data"
    fig.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)

    log = case / LOG_NAME
    if not log.is_file():
        print(f"ERROR: no {LOG_NAME}", file=sys.stderr)
        return 1
    res = parse_residuals(log)
    if not res:
        print("ERROR: no residuals parsed", file=sys.stderr)
        return 1
    cols = ["time"] + [k for k, _ in SERIES]
    with (data / "residuals.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in res:
            w.writerow({c: (f"{r[c]:.8e}" if c in r else "") for c in cols})
    write_residual_svg(
        fig / "residuals.svg",
        res,
        title=f"{case.name} — residuals vs iteration",
    )
    print(f"Wrote Reports/data/residuals.csv ({len(res)} steps)")
    print("Wrote Reports/figures/residuals.svg")

    dT = parse_deltaT(case)
    if dT:
        target = load_exp_deltaT(case)
        write_xy_csv(data / "deltaT_history.csv", ["iteration", "deltaT_K"], dT)
        write_linear_svg(
            fig / "deltaT_history.svg",
            dT,
            title=f"{case.name} — PBGA temperature rise vs iteration",
            ylabel="ΔT [K]",
            color="#c0392b",
            ymin0=0.0,
            target=target,
            target_label="target (exp)",
        )
        print(f"Wrote Reports/data/deltaT_history.csv ({len(dT)} samples)")
        print("Wrote Reports/figures/deltaT_history.svg")
        print(f"  last ΔT = {dT[-1][1]:.3f} K")
        if target is not None:
            print(f"  target ΔT = {target:.3f} K")
    else:
        print("WARNING: no heaterT / inletT history")

    vave = parse_vave(case)
    if vave:
        write_xy_csv(data / "Vave_history.csv", ["iteration", "Vave_mps"], vave)
        write_linear_svg(
            fig / "Vave_history.svg",
            vave,
            title=f"{case.name} — mean |U| over PBGA (Z=7 mm) vs iteration",
            ylabel="Vave [m/s]",
            color="#1f77b4",
            ymin0=0.0,
            markers=True,
        )
        print(f"Wrote Reports/data/Vave_history.csv ({len(vave)} samples)")
        print("Wrote Reports/figures/Vave_history.svg")
        print(f"  last Vave = {vave[-1][1]:.3f} m/s")
    else:
        print("WARNING: no validationLines samples for Vave")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
