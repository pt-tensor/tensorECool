#!/usr/bin/env python3
"""Validate streamwise PIV Uy(x) at Z = 7 mm and PBGA temperature rise.

Compares OpenFOAM line samples at Z = 7 mm, Y = 60/80/100/120/140 mm to
experiment CSVs in Reports/data/experiment/.

Usage (from case root):
  python3 Reports/scripts/validate_vs_experiment.py
  # or: ./Post
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from pathlib import Path

import numpy as np

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "matplotlib required. Use case .venv:\n"
        "  .venv/bin/python Reports/scripts/validate_vs_experiment.py"
    ) from exc

CASE = Path(__file__).resolve().parents[2]
EXP_DIR = CASE / "Reports" / "data" / "experiment"
OUT_DATA = CASE / "Reports" / "data"
OUT_FIG = CASE / "Reports" / "figures"
OUT_MD = CASE / "Reports" / "validation_report.md"
Y_MM = (60, 80, 100, 120, 140)


def load_xin_mm() -> int:
    spec = importlib.util.spec_from_file_location(
        "case_params", CASE / "scripts" / "case_params.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return int(round(mod.Xin * 1000))


def latest_time(case: Path) -> str | None:
    times: list[float] = []
    for p in case.iterdir():
        if not p.is_dir() or p.name in {"0", "0.orig"}:
            continue
        try:
            times.append(float(p.name))
        except ValueError:
            continue
    if not times:
        return None
    t = max(times)
    return str(int(t)) if t == int(t) else str(t)


def read_xy(path: Path) -> tuple[np.ndarray, np.ndarray]:
    x, y = [], []
    with path.open(newline="") as fh:
        r = csv.DictReader(fh)
        keys = r.fieldnames or []
        kx, ky = keys[0], keys[1]
        for row in r:
            x.append(float(row[kx]))
            y.append(float(row[ky]))
    return np.asarray(x), np.asarray(y)


def load_xy(path: Path) -> np.ndarray:
    rows = []
    with path.open() as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.replace(",", " ").split()
            rows.append([float(v) for v in parts])
    if not rows:
        raise RuntimeError(f"No data in {path}")
    return np.asarray(rows, dtype=float)


def extract_uy(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return x [mm], Uy [m/s] from a streamwise line sample."""
    ncol = arr.shape[1]
    if ncol >= 7:
        # x y z Ux Uy Uz T  or  x y z T Ux Uy Uz
        if float(np.nanmean(arr[:, 3])) > 50:
            x, uy = arr[:, 0], arr[:, 5]
        else:
            x, uy = arr[:, 0], arr[:, 4]
    elif ncol == 6:
        x, uy = arr[:, 0], arr[:, 4]
    elif ncol == 5:
        if float(np.nanmean(arr[:, 1])) > 50:
            x, uy = arr[:, 0], arr[:, 3]  # x T Ux Uy Uz
        else:
            x, uy = arr[:, 0], arr[:, 4]
    elif ncol == 4:
        x, uy = arr[:, 0], arr[:, 2]
    elif ncol == 2:
        x, uy = arr[:, 0], arr[:, 1]
    else:
        raise RuntimeError(f"Unexpected sample columns: {ncol}")
    x_mm = np.where(np.nanmax(np.abs(x)) < 1.0, x * 1e3, x)
    return x_mm, uy


def find_line(post: Path, y: int, time: str | None) -> Path | None:
    bases = []
    for fo in ("validationLines", "sets", "sampleLines"):
        for base in (post / fo, *post.glob(f"*/{fo}"), *post.glob(f"{fo}/*")):
            if base.is_dir():
                bases.append(base)
    roots = []
    seen: set[Path] = set()
    for base in bases:
        if base in seen:
            continue
        seen.add(base)
        timed = []
        for p in base.iterdir():
            if not p.is_dir():
                continue
            try:
                timed.append((float(p.name), p))
            except ValueError:
                continue
        if not timed:
            continue
        timed.sort()
        if time is not None:
            match = [p for _v, p in timed if p.name == str(time)]
            roots.append(match[-1] if match else timed[-1][1])
        else:
            roots.append(timed[-1][1])
    needle = f"line_uy_y{y}"
    for root in roots:
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            low = p.name.lower()
            if needle not in low:
                continue
            if low.endswith("_u.xy") or low.endswith("_u"):
                return p
            if "t.xy" in low:
                continue
            return p
    return None


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def metrics(x_exp, u_exp, x_cfd, u_cfd) -> dict[str, float]:
    order = np.argsort(x_cfd)
    u_i = np.interp(x_exp, x_cfd[order], u_cfd[order])
    err = u_i - u_exp
    return {
        "n": float(len(u_exp)),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "mae": float(np.mean(np.abs(err))),
        "max_abs": float(np.max(np.abs(err))),
    }


def plot_stack(xin_mm: int, profiles: dict, out: Path) -> None:
    fig, axes = plt.subplots(len(Y_MM), 1, figsize=(5.4, 11.0), sharex=True)
    # Y=140 at top → Y=60 at bottom
    for ax, y in zip(axes, reversed(Y_MM)):
        xe, ue = profiles[y]["exp"]
        xc, uc = profiles[y]["cfd"]
        ax.plot(xc, uc, color="#c0392b", lw=1.8, label="OpenFOAM (this case)")
        ax.plot(xe, ue, "k+", ms=7, mew=1.3, label="Experiment (PIV)")
        ax.set_ylabel(r"$U_y$ [m/s]")
        ax.text(0.02, 0.88, f"Y = {y} mm", transform=ax.transAxes, fontsize=9)
        ax.set_xlim(40, 160)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel("X [mm]")
    axes[0].set_title(rf"$U_y(x)$ at $Z=7$ mm, $X_{{\mathrm{{in}}}}={xin_mm}$ mm")
    fig.tight_layout()
    fig.savefig(out, dpi=160)
    plt.close(fig)


def load_fig7_exp(xin_mm: int) -> dict[str, float] | None:
    path = EXP_DIR / "fig7.csv"
    if not path.is_file():
        return None
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if int(round(float(row["Xin_mm"]))) == xin_mm:
                return {"deltaT": float(row["deltaT_K"])}
    return None


def rel_err_pct(cfd: float, exp: float) -> float:
    return 100.0 * (cfd - exp) / exp if exp != 0 else float("nan")


def write_fig7_csv(dT: float, exp: dict[str, float]) -> None:
    write_csv(
        OUT_DATA / "fig7_scalars.csv",
        ["quantity", "exp", "cfd", "error", "rel_error_pct"],
        [
            [
                "deltaT_K",
                f"{exp['deltaT']:.6f}",
                f"{dT:.6f}",
                f"{dT - exp['deltaT']:.6f}",
                f"{rel_err_pct(dT, exp['deltaT']):.4f}",
            ]
        ],
    )


def find_monitor(post: Path, name: str) -> Path | None:
    for p in (post / name, post / "PBGA" / name, post / "fluid" / name):
        if p.is_dir():
            return p
    if post.is_dir():
        for p in post.iterdir():
            cand = p / name
            if p.is_dir() and cand.is_dir():
                return cand
    return None


def last_monitor_value(root: Path | None) -> float | None:
    if root is None or not root.is_dir():
        return None
    times = sorted(
        (p for p in root.iterdir() if p.is_dir()),
        key=lambda p: float(p.name),
    )
    if not times:
        return None
    last = None
    folder = times[-1]
    files = sorted(
        list(folder.glob("volFieldValue*.dat")) + list(folder.glob("surfaceFieldValue*.dat")),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    for path in files:
        with path.open() as fh:
            for line in fh:
                if not line.strip() or line.startswith("#"):
                    continue
                try:
                    last = float(line.split()[-1])
                except ValueError:
                    continue
        if last is not None:
            return last
    return last


def write_report(xin_mm: int, time: str, rows: list[dict]) -> None:
    lines = [
        f"# CFD vs experiment — Xin = {xin_mm} mm",
        "",
        "Reference: Hatakeyama et al., *J. Phys.: Conf. Ser.* **395** 012024 (2012).",
        "PIV: streamwise velocity $U_y(x)$ at $Z=7$ mm. Thermal: PBGA temperature rise ΔT.",
        "",
        f"- Case: `Xin{xin_mm}`",
        f"- CFD time folder: `{time}`",
        "- Sample lines: $Y=60,80,100,120,140$ mm, $X=40$–$160$ mm, $Z=7$ mm",
    ]
    post = CASE / "postProcessing"
    t_h = last_monitor_value(find_monitor(post, "packageT"))
    t_i = last_monitor_value(find_monitor(post, "inletT")) or 300.0
    dT = None
    if t_h is not None:
        dT = t_h - t_i
        write_csv(
            OUT_DATA / "deltaT.csv",
            ["Xin_mm", "T_inlet_K", "T_heater_K", "deltaT_K"],
            [[xin_mm, f"{t_i:.6f}", f"{t_h:.6f}", f"{dT:.6f}"]],
        )
        lines.append(
            f"- PBGA ΔT = $T_\\mathrm{{heater}} - T_\\mathrm{{inlet}}$ = "
            f"**{dT:.2f} K** ({t_h:.2f} K − {t_i:.2f} K)"
        )
    exp7 = load_fig7_exp(xin_mm)
    if dT is not None and exp7 is not None:
        write_fig7_csv(dT, exp7)
    lines += [
        "",
        "## Overlay",
        "",
        "| | PNG | SVG |",
        "|---|-----|-----|",
        "| Streamwise $U_y$ (stacked) | [png](figures/fig6_Uy_validation.png) | [svg](figures/fig6_Uy_validation.svg) |",
        "",
        "![Streamwise velocity](figures/fig6_Uy_validation.svg)",
        "",
        "## Per-station SVG",
        "",
        "| Station | SVG |",
        "|---------|-----|",
    ]
    for y in Y_MM:
        lines.append(f"| Y = {y} mm | [svg](figures/fig6_Y{y}_validation.svg) |")
    lines += [
        "",
        "## Error vs digitised PIV (CFD interpolated onto experiment $X$)",
        "",
        "| Y [mm] | n | RMSE [m/s] | MAE [m/s] | max \\|err\\| [m/s] |",
        "|--------|--:|-----------:|----------:|-------------------:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['Y_mm']} | {int(r['n'])} | {r['rmse']:.3f} | {r['mae']:.3f} | {r['max_abs']:.3f} |"
        )
    if dT is not None and exp7 is not None:
        e_dt = dT - exp7["deltaT"]
        p_dt = rel_err_pct(dT, exp7["deltaT"])
        lines += [
            "",
            "## PBGA temperature rise vs experiment",
            "",
            f"Xin = {xin_mm} mm. Relative error is "
            r"$(\mathrm{CFD}-\mathrm{exp})/\mathrm{exp}$.",
            "",
            "| Quantity | Experiment | CFD | Error | Rel. error |",
            "|----------|-----------:|----:|------:|-----------:|",
            f"| ΔT [K] | {exp7['deltaT']:.2f} | {dT:.2f} | {e_dt:+.2f} | {p_dt:+.1f} % |",
            "",
            "![Temperature rise](figures/fig7_validation.svg)",
            "",
            "CFD ΔT is the volume-average temperature of region `PBGA` "
            "minus inlet $T$. Experiment ΔT is the measured PBGA package rise.",
        ]
    lines += [
        "",
        "## Data files",
        "",
        "- Experimental (digitised): `data/experiment/fig6_Y*.csv`",
        "- Source scans: `../../../References/validation-benchmarks/Xin"
        + str(xin_mm)
        + "-Y*.csv`",
        "- CFD profiles: `data/cfd_fig6_Y*.csv`",
        "- Metrics: `data/validation_metrics.csv`",
        "- ΔT scalars: `data/fig7_scalars.csv`",
        "- ΔT experiment: `data/experiment/fig7.csv`",
        "- Rebuild SVGs only: `python3 Reports/scripts/make_validation_svgs.py`",
        "",
        "## Notes",
        "",
        "- PIV markers were digitised from the published streamwise-velocity plots; small digitisation scatter remains.",
        "- Paper CFD was laminar SIMPLE (flow only). This case also solves Boussinesq energy (2.6 W PBGA).",
        "",
    ]
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--time", default="LATEST")
    ap.add_argument("--skip-sample", action="store_true")
    args = ap.parse_args()

    OUT_DATA.mkdir(parents=True, exist_ok=True)
    OUT_FIG.mkdir(parents=True, exist_ok=True)
    xin_mm = load_xin_mm()
    time = latest_time(CASE) if args.time.upper() == "LATEST" else args.time

    profiles: dict = {}
    metric_rows = []
    missing_exp = []
    for y in Y_MM:
        exp_path = EXP_DIR / f"fig6_Y{y}.csv"
        if not exp_path.is_file():
            missing_exp.append(exp_path)
            continue
        x_exp, u_exp = read_xy(exp_path)
        sample = find_line(CASE / "postProcessing", y, time)
        cached = OUT_DATA / f"cfd_fig6_Y{y}.csv"
        if sample is not None:
            x_cfd, u_cfd = extract_uy(load_xy(sample))
        elif cached.is_file():
            print(f"NOTE: using cached {cached.name} (no postProcessing sample)")
            x_cfd, u_cfd = read_xy(cached)
        else:
            print(
                f"ERROR: no CFD sample for Y={y} mm under postProcessing/validationLines/",
                file=sys.stderr,
            )
            return 2
        write_csv(
            cached,
            ["x_mm", "Uy_mps"],
            [[f"{a:.6f}", f"{b:.6f}"] for a, b in zip(x_cfd, u_cfd)],
        )
        m = metrics(x_exp, u_exp, x_cfd, u_cfd)
        m["Y_mm"] = y
        metric_rows.append(m)
        profiles[y] = {"exp": (x_exp, u_exp), "cfd": (x_cfd, u_cfd)}

    if missing_exp:
        print("ERROR: missing experiment CSVs:", file=sys.stderr)
        for p in missing_exp:
            print(" ", p, file=sys.stderr)
        return 1

    if time is None:
        time = "cached"
    write_csv(
        OUT_DATA / "validation_metrics.csv",
        ["Y_mm", "n", "RMSE_mps", "MAE_mps", "max_abs_mps"],
        [
            [
                r["Y_mm"],
                int(r["n"]),
                f"{r['rmse']:.6f}",
                f"{r['mae']:.6f}",
                f"{r['max_abs']:.6f}",
            ]
            for r in metric_rows
        ],
    )
    plot_stack(xin_mm, profiles, OUT_FIG / "fig6_Uy_validation.png")
    write_report(xin_mm, time, metric_rows)
    print(f"Wrote {OUT_MD.relative_to(CASE)}")
    print(f"Figures in {OUT_FIG.relative_to(CASE)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
