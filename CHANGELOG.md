# Changelog

## 0.1.0 — 2026-09-06

Initial GitHub release. A wheel and sdist are available below.

- Multimodal ingestion, unit and source records, validation, solver readiness
  checks, and HDF5/NPZ datasets.
- Native instrument/XLSX blocks, MAT5/HDF5/NPY arrays, Gmsh 2.2 meshes,
  Rodrigues orientations, grain graphs and configured stiffness pairing.
- Abaqus input preparation, execution records and ODB
  field extraction for checked isotropic-elastic, isotropic-plastic and
  explicit UMAT profiles.
- Grouped CPU MLP training with train-only normalization and validation-based
  checkpoint selection; optional PyG export with an explicit graph contract.
- A public CuSn8Ni2 tensile case with twelve real FE cases, 84 completed
  stages and separate FE and experimental holdouts. At 0–0.8% engineering
  strain, MLP/held-out-FE RMSE is 0.682 MPa; FE/MLP against H_18 is
  4.428/4.477 MPa.
- Apache-2.0 project license and CC-BY-4.0 attribution for the public tensile materials.

Python 3.12 or newer is required. `native`, `training` and `ml` extras supply
the corresponding optional dependencies. Solver execution uses the user's
Abaqus installation. The tensile case uses a small-strain uniform gauge model,
with H_08 for calibration, H_16 for model checking and H_18 for final evaluation.

[Release and downloads](https://github.com/17636365690/experiment-to-cpfe-pipeline/releases/tag/v0.1.0)
· [Verification](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/verification/2026-09-06-v0.1.0-release.md)
