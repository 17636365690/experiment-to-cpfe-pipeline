# Changelog

## 0.1.0 — 2026-09-06

First formal GitHub release, distributed as a Python wheel and sdist.

- Multimodal assets, explicit units and evidence classes, conversion records,
  validation, solver readiness, and HDF5/NPZ datasets.
- Native instrument/XLSX blocks, MAT5/HDF5/NPY arrays, Gmsh 2.2 meshes,
  Rodrigues orientations, grain graphs and configured stiffness pairing.
- Abaqus input preparation, stage-specific execution records and real ODB
  field extraction for checked isotropic-elastic, isotropic-plastic and
  explicit UMAT profiles.
- Grouped CPU MLP training with train-only normalization and validation-based
  checkpoint selection; optional PyG export with an explicit graph contract.
- A public CuSn8Ni2 tensile case with twelve real FE cases, 84 completed
  stages and separate FE and experimental holdouts. At 0–0.8% engineering
  strain, MLP/held-out-FE RMSE is 0.682 MPa; FE/MLP against H_18 is
  4.428/4.477 MPa.
- Apache-2.0 project license, CC-BY-4.0 case attribution, package license
  metadata and version-specific download/install instructions.

Python 3.12 or newer is required. `native`, `training` and `ml` extras supply
the corresponding optional dependencies. Solver execution uses the user's
Abaqus installation. The scientific case retains its small-strain uniform
gauge assumptions, H_08/H_16/H_18 split and existing results.

[Release and downloads](https://github.com/17636365690/experiment-to-cpfe-pipeline/releases/tag/v0.1.0)
· [Verification](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/verification/2026-09-06-v0.1.0-release.md)
