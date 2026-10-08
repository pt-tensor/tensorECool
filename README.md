# Hatakeyama CHT — Xin = 100 mm

Conjugate heat transfer recreation of [`../CFD/Xin100`](../CFD/Xin100):
air + **PCB** + **PBGA** with `chtMultiRegionSimpleFoam`.

2.6 W is a volumetric source in the **PBGA** region. Heat conducts into the PCB
and convects to the air through coupled walls (`turbulentTemperatureCoupledBaffleMixed`).

| Item | Value |
|------|--------|
| Solver | `chtMultiRegionSimpleFoam` (steady, Boussinesq air) |
| Turbulence | RAS `kOmegaSST` |
| Air | `rho0 = 1.2`, `nu` via `mu = 1.8e-05`, `Pr = 0.7`, `T0 = 300` K |
| PCB | anisotropic `κ = (2, 2, 0.35)` W/m/K (in-plane / through-thickness) |
| PBGA | mold `k = 1` W/m/K; **Q = 2.6 W** in whole package (die zone kept for FO `dieT`) |
| Mesh | 1 mm in-plane; wall-normal slabs at PCB / PBGA / lid |
| Inlet | Xin = **100 mm**, fully developed 20×10 mm duct, Qin = 5.64e-4 m³/s |

ΔT for validation is the **volume-average PBGA temperature** minus inlet T
(the experimental package rise).

```bash
./buildMesh
./Run
./Post
```
