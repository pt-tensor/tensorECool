#!/usr/bin/env python3
"""Build PIV and ΔT validation SVGs from Post CSVs.

Reads:
  Reports/data/cfd_fig6_Y{60,80,100,120,140}.csv
  Reports/data/experiment/fig6_Y{60,80,100,120,140}.csv

Writes:
  Reports/figures/fig6_Y{Y}_validation.svg
  Reports/figures/fig6_Uy_validation.svg   (stacked)

Usage (from case root):
  python3 Reports/scripts/make_validation_svgs.py
"""
from __future__ import annotations

import csv
import importlib.util
import math
from pathlib import Path

CASE = Path(__file__).resolve().parents[2]
OUT_DATA = CASE / "Reports" / "data"
EXP_DIR = OUT_DATA / "experiment"
OUT_FIG = CASE / "Reports" / "figures"
Y_MM = (60, 80, 100, 120, 140)


def load_xin_mm() -> int:
    spec = importlib.util.spec_from_file_location(
        "case_params", CASE / "scripts" / "case_params.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return int(round(mod.Xin * 1000))


def read_xy(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    with path.open(newline="") as fh:
        r = csv.DictReader(fh)
        keys = r.fieldnames or []
        kx, ky = keys[0], keys[1]
        for row in r:
            rows.append((float(row[kx]), float(row[ky])))
    return rows


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


def y_lim(cfd: list[tuple[float, float]], exp: list[tuple[float, float]]) -> tuple[float, float]:
    ys = [y for _, y in cfd] + [y for _, y in exp]
    if not ys:
        return (-0.5, 4.0)
    lo, hi = min(ys), max(ys)
    pad = max(0.15, 0.08 * (hi - lo))
    return (math.floor((lo - pad) * 2) / 2, math.ceil((hi + pad) * 2) / 2)


def draw_panel(
    parts: list[str],
    *,
    cfd: list[tuple[float, float]],
    exp: list[tuple[float, float]],
    ml: float,
    mt: float,
    pw: float,
    ph: float,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    xlabel: str | None,
    ylabel: str,
    label: str,
    xticks: bool,
) -> None:
    x0, x1 = xlim
    y0, y1 = ylim

    def X(x: float) -> float:
        return ml + (x - x0) / (x1 - x0) * pw

    def Y(y: float) -> float:
        return mt + (1.0 - (y - y0) / (y1 - y0)) * ph

    parts.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#333" stroke-width="1.1"/>')
    parts.append(
        f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#333" stroke-width="1.1"/>'
    )
    for xv in nice_ticks(x0, x1, 7):
        xx = X(xv)
        parts.append(
            f'<line x1="{xx:.2f}" y1="{mt}" x2="{xx:.2f}" y2="{mt+ph}" stroke="#eee" stroke-width="1"/>'
        )
        if xticks:
            parts.append(
                f'<text x="{xx:.2f}" y="{mt+ph+14}" text-anchor="middle" '
                f'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#555">{xv:g}</text>'
            )
    for yv in nice_ticks(y0, y1, 5):
        yy = Y(yv)
        parts.append(
            f'<line x1="{ml}" y1="{yy:.2f}" x2="{ml+pw}" y2="{yy:.2f}" stroke="#eee" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{ml-6}" y="{yy+3:.2f}" text-anchor="end" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#555">{yv:g}</text>'
        )
    parts.append(
        f'<text x="{ml-36}" y="{mt+ph/2:.1f}" text-anchor="middle" '
        f'transform="rotate(-90 {ml-36} {mt+ph/2:.1f})" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#444">{ylabel}</text>'
    )
    parts.append(
        f'<text x="{ml+8}" y="{mt+14}" font-family="Helvetica,Arial,sans-serif" '
        f'font-size="11" fill="#222">{label}</text>'
    )
    if xlabel:
        parts.append(
            f'<text x="{ml+pw/2:.1f}" y="{mt+ph+28}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#444">{xlabel}</text>'
        )
    if cfd:
        d = " ".join(
            f"{'M' if i == 0 else 'L'}{X(x):.2f},{Y(y):.2f}" for i, (x, y) in enumerate(cfd)
        )
        parts.append(
            f'<path d="{d}" fill="none" stroke="#c0392b" stroke-width="2.0" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
    for x, y in exp:
        cx, cy = X(x), Y(y)
        s = 4.5
        parts.append(
            f'<line x1="{cx-s:.2f}" y1="{cy:.2f}" x2="{cx+s:.2f}" y2="{cy:.2f}" '
            f'stroke="#111" stroke-width="1.4"/>'
        )
        parts.append(
            f'<line x1="{cx:.2f}" y1="{cy-s:.2f}" x2="{cx:.2f}" y2="{cy+s:.2f}" '
            f'stroke="#111" stroke-width="1.4"/>'
        )


def legend(parts: list[str], lx: float, ly: float) -> None:
    parts.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+26}" y2="{ly}" stroke="#c0392b" stroke-width="2.0"/>')
    parts.append(
        f'<text x="{lx+32}" y="{ly+4}" font-family="Helvetica,Arial,sans-serif" '
        f'font-size="11" fill="#222">OpenFOAM (this case)</text>'
    )
    ly2 = ly + 16
    parts.append(f'<line x1="{lx+7}" y1="{ly2}" x2="{lx+19}" y2="{ly2}" stroke="#111" stroke-width="1.4"/>')
    parts.append(f'<line x1="{lx+13}" y1="{ly2-6}" x2="{lx+13}" y2="{ly2+6}" stroke="#111" stroke-width="1.4"/>')
    parts.append(
        f'<text x="{lx+32}" y="{ly2+4}" font-family="Helvetica,Arial,sans-serif" '
        f'font-size="11" fill="#222">Experiment (PIV)</text>'
    )


def write_svg(path: Path, parts: list[str]) -> None:
    parts.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"Wrote {path.relative_to(CASE)}")


def write_fig7_svg(xin_mm: int) -> None:
    path = OUT_DATA / "fig7_scalars.csv"
    if not path.is_file():
        return
    rows = list(csv.DictReader(path.open(newline="")))
    by_q = {r["quantity"]: r for r in rows}
    r = by_q.get("deltaT_K")
    if r is None or not r.get("exp") or not r.get("cfd"):
        return
    exp_v = float(r["exp"])
    cfd_v = float(r["cfd"])
    ymax = max(exp_v, cfd_v, 1e-9) * 1.25
    w, h = 420, 220
    base_y, bh, x0 = 190, 110, 130
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="PBGA temperature rise Xin={xin_mm} mm">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{w/2:.1f}" y="24" text-anchor="middle" '
        'font-family="Helvetica,Arial,sans-serif" font-size="14" font-weight="600" fill="#111">'
        f"PBGA temperature rise — Xin={xin_mm} mm</text>",
        '<text x="210" y="52" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" '
        'font-size="11" fill="#555">ΔT [K]</text>',
    ]

    def bar(x, val, color, label):
        hh = 0 if ymax <= 0 else bh * val / ymax
        y = base_y - hh
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="54" height="{hh:.1f}" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{x+27:.1f}" y="{y-6:.1f}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#222">'
            f"{val:.2f}</text>"
        )
        parts.append(
            f'<text x="{x+27:.1f}" y="{base_y+16:.1f}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="10" fill="#555">{label}</text>'
        )

    bar(x0, exp_v, "#111111", "exp")
    bar(x0 + 80, cfd_v, "#c0392b", "CFD")
    pct = r.get("rel_error_pct") or ""
    if pct:
        parts.append(
            f'<text x="210" y="{base_y+36:.1f}" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="11" fill="#333">'
            f"rel. error {float(pct):+.1f} %</text>"
        )
    parts.append("</svg>")
    (OUT_FIG / "fig7_validation.svg").write_text("\n".join(parts) + "\n", encoding="utf-8")
    print("Wrote Reports/figures/fig7_validation.svg")


def main() -> int:
    xin_mm = load_xin_mm()
    data = {}
    missing = []
    for y in Y_MM:
        cfd_p = OUT_DATA / f"cfd_fig6_Y{y}.csv"
        exp_p = EXP_DIR / f"fig6_Y{y}.csv"
        if not cfd_p.is_file() or not exp_p.is_file():
            missing.append(cfd_p if not cfd_p.is_file() else exp_p)
            continue
        data[y] = (read_xy(cfd_p), read_xy(exp_p))
    if missing:
        print("ERROR: missing Post data files:")
        for p in missing:
            print(" ", p)
        print("Run ./Post first (or validate_vs_experiment.py).")
        return 1

    xlim = (40.0, 160.0)
    width, panel_h, ml, mr, mt0, mb = 640, 168, 58, 18, 36, 36
    n = len(Y_MM)
    height = mt0 + n * panel_h + mb
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Uy vs X at Z=7 mm, Xin={xin_mm} mm">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width/2:.1f}" y="22" text-anchor="middle" '
        f'font-family="Helvetica,Arial,sans-serif" font-size="14" font-weight="600" fill="#111">'
        f"Uy(x) at Z=7 mm, Xin={xin_mm} mm</text>",
    ]
    legend(parts, ml + 8, mt0 + 4)
    pw = width - ml - mr
    ph = panel_h - 22
    # Stack Y=140 at top → Y=60 at bottom (streamwise upward).
    y_stack = tuple(reversed(Y_MM))
    for i, y in enumerate(y_stack):
        cfd, exp = data[y]
        mt = mt0 + 18 + i * panel_h
        last = i == n - 1
        draw_panel(
            parts,
            cfd=cfd,
            exp=exp,
            ml=ml,
            mt=mt,
            pw=pw,
            ph=ph,
            xlim=xlim,
            ylim=y_lim(cfd, exp),
            xlabel="X [mm]" if last else None,
            ylabel="Uy [m/s]",
            label=f"Y = {y} mm",
            xticks=last,
        )
    write_svg(OUT_FIG / "fig6_Uy_validation.svg", parts)

    for y in Y_MM:
        cfd, exp = data[y]
        w, h = 640, 280
        p = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" role="img" aria-label="Uy Y={y} mm">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
            f'<text x="{w/2:.1f}" y="22" text-anchor="middle" '
            f'font-family="Helvetica,Arial,sans-serif" font-size="13" font-weight="600" fill="#111">'
            f"Uy(x) — Y={y} mm, Z=7 mm, Xin={xin_mm} mm</text>",
        ]
        legend(p, 66, 38)
        draw_panel(
            p,
            cfd=cfd,
            exp=exp,
            ml=58,
            mt=56,
            pw=w - 58 - 18,
            ph=h - 56 - 42,
            xlim=xlim,
            ylim=y_lim(cfd, exp),
            xlabel="X [mm]",
            ylabel="Uy [m/s]",
            label="",
            xticks=True,
        )
        write_svg(OUT_FIG / f"fig6_Y{y}_validation.svg", p)
    write_fig7_svg(xin_mm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
