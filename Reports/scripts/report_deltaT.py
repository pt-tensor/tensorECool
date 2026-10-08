#!/usr/bin/env python3
"""ΔT = area-average T on heater minus inlet T (paper: PBGA rise vs ambient)."""
from pathlib import Path
import csv
import importlib.util

CASE = Path(__file__).resolve().parents[2]
OUT = CASE / "Reports" / "data"
OUT.mkdir(parents=True, exist_ok=True)
T_INLET = 300.0


def load_xin_mm() -> int:
    spec = importlib.util.spec_from_file_location(
        "case_params", CASE / "scripts" / "case_params.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return int(round(mod.Xin * 1000))


def latest_numeric_subdir(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    times = sorted(
        (p for p in root.iterdir() if p.is_dir()),
        key=lambda p: float(p.name),
    )
    return times[-1] if times else None


def last_average(path: Path) -> float | None:
    if not path.is_file():
        return None
    last = None
    with path.open() as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split()
            try:
                last = float(parts[-1])
            except ValueError:
                continue
    return last


def find_monitor_dir(case: Path, name: str) -> Path | None:
    post = case / "postProcessing"
    for p in (post / name, post / "PBGA" / name, post / "fluid" / name):
        if p.is_dir():
            return p
    if post.is_dir():
        for child in post.iterdir():
            cand = child / name
            if child.is_dir() and cand.is_dir():
                return cand
    return None


def main() -> None:
    xin_mm = load_xin_mm()
    pkg = find_monitor_dir(CASE, "packageT")
    inlet = find_monitor_dir(CASE, "inletT")
    heater_dir = latest_numeric_subdir(pkg) if pkg else None
    inlet_dir = latest_numeric_subdir(inlet) if inlet else None
    if heater_dir is None:
        raise SystemExit("No postProcessing/packageT — run the solver first.")

    t_h = last_average(heater_dir / "volFieldValue.dat")
    if t_h is None:
        t_h = last_average(heater_dir / "volFieldValue_0.dat")
    if t_h is None:
        t_h = last_average(heater_dir / "surfaceFieldValue.dat")
    t_i = T_INLET
    if inlet_dir is not None:
        t_in = last_average(inlet_dir / "surfaceFieldValue.dat")
        if t_in is not None:
            t_i = t_in
    if t_h is None:
        raise SystemExit(f"Could not read T from {heater_dir}")

    dT = t_h - t_i
    dest = OUT / "deltaT.csv"
    with dest.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Xin_mm", "T_inlet_K", "T_heater_K", "deltaT_K"])
        w.writerow([xin_mm, f"{t_i:.6f}", f"{t_h:.6f}", f"{dT:.6f}"])
    print(f"Xin={xin_mm} mm  T_inlet={t_i:.3f} K  T_heater={t_h:.3f} K  ΔT={dT:.3f} K")
    print(f"Wrote {dest}")

    fig7 = OUT / "experiment" / "fig7.csv"
    if fig7.is_file():
        with fig7.open(newline="") as f:
            for row in csv.DictReader(f):
                if int(round(float(row["Xin_mm"]))) == xin_mm:
                    dT_exp = float(row["deltaT_K"])
                    e = dT - dT_exp
                    pct = 100.0 * e / dT_exp
                    print(
                        f"ΔT: exp={dT_exp:.2f} K  CFD={dT:.2f} K  "
                        f"error={e:+.2f} K  ({pct:+.1f} %)"
                    )
                    break


if __name__ == "__main__":
    main()
