#!/usr/bin/env python3
"""Plot CFD Uy(x) at Z = 7 mm for the PIV stations."""
from pathlib import Path
import importlib.util

import matplotlib.pyplot as plt
import numpy as np

CASE = Path(__file__).resolve().parents[2]
SETS = CASE / "postProcessing" / "validationLines"
OUT = CASE / "Reports" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

Y_MM = (60, 80, 100, 120, 140)


def load_xin_mm() -> int:
    spec = importlib.util.spec_from_file_location(
        "case_params", CASE / "scripts" / "case_params.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return int(round(mod.Xin * 1000))


def latest_sets_dir() -> Path:
    bases = [SETS]
    nested = SETS / "fluid"
    if nested.is_dir():
        bases.append(nested)
    times: list[Path] = []
    for base in bases:
        if not base.is_dir():
            continue
        for p in base.iterdir():
            if not p.is_dir():
                continue
            try:
                float(p.name)
            except ValueError:
                continue
            times.append(p)
    times.sort(key=lambda p: float(p.name))
    if not times:
        raise SystemExit(f"No sampled sets under {SETS}. Run ./Post after ./Run.")
    return times[-1]


def load_line(path: Path) -> tuple[np.ndarray, np.ndarray]:
    rows = []
    with path.open() as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split()
            # raw format: x y z Ux Uy Uz
            rows.append([float(parts[0]), float(parts[4])])
    arr = np.asarray(rows)
    return arr[:, 0] * 1e3, arr[:, 1]


def main() -> None:
    xin_mm = load_xin_mm()
    d = latest_sets_dir()
    fig, axes = plt.subplots(len(Y_MM), 1, figsize=(5.2, 10.5), sharex=True)
    # Y=140 at top → Y=60 at bottom
    for ax, y in zip(axes, reversed(Y_MM)):
        x_mm, uy = load_line(d / f"line_Uy_Y{y}_U.xy")
        ax.plot(x_mm, uy, color="tab:red", lw=1.6, label="CFD")
        ax.set_ylabel("Uy [m/s]")
        ax.text(0.02, 0.88, f"Y = {y} mm", transform=ax.transAxes, fontsize=9)
        ax.set_xlim(40, 160)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel("X [mm]")
    axes[0].set_title(rf"Streamwise velocity at $Z=7$ mm, $X_{{in}}={xin_mm}$ mm")
    fig.tight_layout()
    dest = OUT / f"fig6_Uy_profiles_Xin{xin_mm}.svg"
    fig.savefig(dest)
    print(f"Wrote {dest}")


if __name__ == "__main__":
    main()
