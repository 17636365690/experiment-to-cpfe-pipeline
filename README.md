# Experiment-to-CPFE Pipeline

A dataset-neutral, provenance-preserving Python pipeline for moving experimental and microstructure assets through validation, solver-input preparation, real Abaqus execution, result extraction, and machine-learning dataset export.

The project does not infer missing units, coordinate systems, tensor order, orientation conventions, material models, or boundary conditions. A stress–strain curve is treated as a calibration or validation target; it is not converted into a complete CPFE material card. The solver workflow records real Abaqus execution and checks its ODB and companion artifacts before extraction. Hashes detect changed files; they do not independently authenticate a third-party solver result.

Version 0.1 provides an offline multimodal pipeline and an opt-in Abaqus backend. Checked solver inputs include flat isotropic-elastic or explicit UMAT models, with optional grain-orientation mapping to explicitly initialized STATEV entries. Format registration is broader than semantic parsing: vendor binary EBSD, DREAM.3D, DAMASK and Neper files can be described as native assets, but do not all have parsers or solver backends. See [supported formats](docs/data-modalities.md) and [known limitations](docs/limitations.md) before preparing a dataset.

## Install

Python 3.12 or newer is required.

```text
python -m venv .venv
.venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build
```

The activation command above is for Windows PowerShell. On POSIX shells use
`source .venv/bin/activate`. Alternatively, invoke the environment's Python and
`pipeline` executables directly. Keep the working directory at the repository
root for the examples below.

Install the optional `ml` extra to export a PyTorch/PyG bundle:

```text
python -m pip install -e ".[ml]"
```

## Offline synthetic example

The public example contains only tiny synthetic CSV, JSON, and INP files. It exercises a mechanical time series, grain orientations, a DIC point field, a voxel grid, a mesh asset, parent-asset provenance, solver readiness, INP rendering, and HDF5 export. Generated example values use the `input` evidence class and a `synthetic` source description; they are not experimental measurements or a calibrated material model. The reserved `measured_observations` table name shows the table layout only and does not override the asset's evidence class.

The mechanical example is small-strain linear elasticity and requests `E` for
strain. An appropriate finite-strain model may request `LE`; the extractor does
not silently substitute one strain measure for the other.

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

Use a new run directory for a changed configuration or input. The pipeline binds
inputs and reports to hashes, isolates datacheck and analysis directories, and
refuses to overwrite completed stage outputs. Each initialized run contains
`reports/run_manifest.json`, `reports/validation.json`,
`reports/solver_readiness.json`, and `reports/qa_report.md`.

HDF5 is the canonical package. NPZ/PyG exports read that file with its recorded
hash and preserve the sample's tables, assets, units and provenance. PyG requires
explicit graph arrays and feature metadata; the minimal example does not create
a graph or infer training labels.

## Public-data boundary

The repository is intended to contain generic code, schemas, configuration templates, synthetic fixtures, tests, and documentation. Do not add raw experiments, large ODB/CAE files, checkpoints, private material cards, unlicensed UMAT/VUMAT sources, credentials, machine-specific manifests, or developer-machine paths.

See [the schema guide](docs/schema.md), [data modality guide](docs/data-modalities.md), and [runbook](docs/runbook.md).

The [release checklist](docs/release_checklist.md) records the publication gates.
A project-wide distribution license has not yet been selected. License labels
in public-source manifests describe those external sources only.
