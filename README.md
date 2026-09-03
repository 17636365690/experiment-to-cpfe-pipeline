# Experiment-to-CPFE Pipeline

A dataset-neutral, provenance-preserving Python pipeline for moving experimental and microstructure assets through validation, solver-input preparation, real Abaqus execution, result extraction, and machine-learning dataset export.

The project does not infer missing units, coordinate systems, tensor order, orientation conventions, material models, or boundary conditions. A stress–strain curve is treated as a calibration or validation target; it is not converted into a complete CPFE material card. An ODB is accepted only as an Abaqus-produced solver artifact.

## Install

Python 3.12 or newer is required.

```text
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
python -m pytest -q
python -m build
```

Install the optional `ml` extra to export a PyTorch/PyG bundle:

```text
python -m pip install -e ".[ml]"
```

## Offline synthetic example

The public example contains only tiny synthetic CSV, JSON, and INP files. It exercises a mechanical time series, grain orientations, a DIC point field, a voxel grid, a mesh asset, parent-asset provenance, solver readiness, INP rendering, and HDF5 export.

```text
pipeline validate --config examples/synthetic_minimal/sample.yaml --run-dir runs/synthetic-001
pipeline build-inp --config examples/synthetic_minimal/sample.yaml --run-dir runs/synthetic-001
pipeline export --config examples/synthetic_minimal/sample.yaml --run-dir runs/synthetic-001 --format hdf5
pipeline export --config examples/synthetic_minimal/sample.yaml --run-dir runs/synthetic-001 --format npz
pipeline inspect --run-dir runs/synthetic-001
```

No Abaqus installation is required for these commands. Real execution is explicit:

```text
pipeline run-abaqus --config sample.yaml --run-dir runs/sample-001 --stage datacheck
pipeline run-abaqus --config sample.yaml --run-dir runs/sample-001 --stage analysis
pipeline extract-odb --config sample.yaml --run-dir runs/sample-001
```

## Public-data boundary

The repository is intended to contain generic code, schemas, configuration templates, synthetic fixtures, tests, and documentation. Do not add raw experiments, large ODB/CAE files, checkpoints, private material cards, unlicensed UMAT/VUMAT sources, credentials, machine-specific manifests, or developer-machine paths.

See [the schema guide](docs/schema.md), [data modality guide](docs/data-modalities.md), and [runbook](docs/runbook.md).
