# Validation reports

Compare OpenFOAM $U_y(x)$ at $Z=7$ mm to digitised PIV, and PBGA $\Delta T$ to the measured package temperature rise.

## Quick start

From the case root (after `./Run` finishes):

```bash
./Post
```

This:

1. Samples PIV lines via `buoyantBoussinesqSimpleFoam -postProcess`
2. Loads digitised PIV CSVs from `data/experiment/`
3. Writes overlays, RMSE/MAE, ΔT error, `validation_report.md`

## Layout

| Path | Role |
|------|------|
| `data/experiment/` | Digitised PIV profiles and ΔT — tracked |
| `scripts/validate_vs_experiment.py` | Overlay PNG + PIV/ΔT metrics + markdown |
| `scripts/make_validation_svgs.py` | SVG rebuild from CSVs (no matplotlib) |
| `scripts/make_history_svgs.py` | Residuals, ΔT, Vave vs iteration |
| `scripts/report_deltaT.py` | Heater ΔT vs inlet and experiment |
| `figures/residuals.svg` | Solver residuals |
| `figures/deltaT_history.svg` | PBGA ΔT vs iteration |
| `figures/Vave_history.svg` | Mean `|U|` over PBGA vs iteration |
| `figures/*_validation.svg` | CFD vs experiment overlays (from Post) |
| `validation_report.md` | Summary (generated) |

```bash
# SVG-only rebuild from existing Post CSVs (no OpenFOAM needed)
python3 Reports/scripts/make_validation_svgs.py
```

Use the case `.venv` (created automatically by `./Post`) for matplotlib/numpy.
