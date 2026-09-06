# Experiment-to-CPFE Pipeline

A dataset-neutral, provenance-preserving Python pipeline for moving experimental and microstructure assets through validation, solver-input preparation, real Abaqus execution, result extraction, and machine-learning dataset export.

Each dataset declares its units, coordinates, tensor order, orientation conventions and evidence sources. Stress-strain curves serve as calibration or validation targets. Solver preparation uses an explicit material model and boundary conditions, and result extraction reads the recorded Abaqus outputs.

Version 0.1 provides an offline multimodal pipeline and an opt-in Abaqus backend. Checked solver inputs include flat isotropic-elastic, isotropic-plastic and explicit UMAT models, with grain-orientation mapping to initialized STATEV entries. The [format guide](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/data-modalities.md) lists implemented readers and formats retained as native assets. [Operating conditions](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/limitations.md) describe supported solver profiles and data requirements.

## Install

Python 3.12 or newer is required. Install the wheel from the
[v0.1.0 release](https://github.com/17636365690/experiment-to-cpfe-pipeline/releases/tag/v0.1.0):

```text
python -m pip install "https://github.com/17636365690/experiment-to-cpfe-pipeline/releases/download/v0.1.0/experiment_to_cpfe-0.1.0-py3-none-any.whl"
pipeline --help
```

The Release contains the wheel and source distribution. For the examples,
tests and documentation, check out the same version:

```text
git clone --branch v0.1.0 --depth 1 https://github.com/17636365690/experiment-to-cpfe-pipeline.git
cd experiment-to-cpfe-pipeline
```

For development and running the offline tests:

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

The optional `native` extra adds MAT5 and XLSX readers. Configured native blocks,
multidimensional arrays, Gmsh meshes and grain graphs can be inspected before
complete sample conventions are available:

```text
python -m pip install -e ".[native]"
pipeline adapt --config examples/synthetic_native/imports.yaml --run-dir runs/native-example
```

The report separates decoded values from unresolved physical meaning. Checked
arrays enter the existing pipeline through an `imports` list. See the
[native adapter guide](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/native-adapters.md) for selectors and examples.

## Public experiment to neural surrogate

The [CuSn8Ni2 tensile example](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/examples/kupfer_tensile/README.md) runs public
experimental data through material calibration, a generated Abaqus model,
real ODB extraction, HDF5/NPZ packaging and a small neural surrogate.
Its [verification record](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/verification/2026-09-06-public-tensile-surrogate.md)
reports twelve completed FE cases and separate simulation/experiment holdouts.

For the 0-0.8% engineering-strain gauge model, the MLP reaches 0.682 MPa RMSE
on held-out FE cases. On experimental specimen H_18, FE and MLP RMSE are
4.428 MPa and 4.477 MPa. The [reference INP](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/examples/kupfer_tensile/reference/base.inp)
and [result summary](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/verification/assets/public-tensile-20260906/summary.json)
accompany the case.

![CuSn8Ni2 experiment, FE and neural surrogate comparison](https://raw.githubusercontent.com/17636365690/experiment-to-cpfe-pipeline/v0.1.0/docs/verification/assets/public-tensile-20260906/experimental-workflow.png)

Experimental curves are processed from the KupferDigital dataset by
H. Beygi Nasrabadi et al. ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)).
The verification record documents the preprocessing, model and data splits.

The `training` extra provides the CPU MLP interface:

```text
python -m pip install -e ".[training]"
pipeline train-surrogate --config training.json --run-dir runs/trained-model
```

The training configuration names the dataset, feature/target units and model
settings. Each parameter case keeps one train, validation or test assignment.

## Offline synthetic example

The public example contains tiny synthetic CSV, JSON and INP files. It exercises a mechanical time series, grain orientations, a DIC point field, voxels, a mesh asset, readiness checks, INP rendering and HDF5 export. Values carry the `input` evidence class and a `synthetic` source description, including records placed in the reserved `measured_observations` table.

The mechanical example uses small-strain linear elasticity and requests `E`.
Finite-strain models can request `LE` with its corresponding measure and definition.

```text
pipeline validate --config examples/synthetic_minimal/sample.yaml --run-dir runs/synthetic-001
pipeline build-inp --config examples/synthetic_minimal/sample.yaml --run-dir runs/synthetic-001
pipeline export --config examples/synthetic_minimal/sample.yaml --run-dir runs/synthetic-001 --format hdf5
pipeline export --config examples/synthetic_minimal/sample.yaml --run-dir runs/synthetic-001 --format npz
pipeline inspect --run-dir runs/synthetic-001
```

These commands run in ordinary Python. Use the following stages for Abaqus execution:

```text
pipeline run-abaqus --config sample.yaml --run-dir runs/sample-001 --stage datacheck
pipeline run-abaqus --config sample.yaml --run-dir runs/sample-001 --stage analysis
pipeline extract-odb --config sample.yaml --run-dir runs/sample-001
```

Use a new run directory for a changed configuration or input. Datacheck and
analysis keep separate stage artifacts. Each initialized run contains
`reports/run_manifest.json`, `reports/validation.json`,
`reports/solver_readiness.json`, and `reports/qa_report.md`.

HDF5 is the canonical package. NPZ/PyG exports preserve its tables, assets,
units and source records. PyG uses explicitly supplied graph arrays and feature
metadata, as described in the native adapter guide.

## Public-data boundary

The repository contains generic code, schemas, configuration templates, synthetic fixtures, tests and documentation. Research data, solver outputs, material cards and machine-specific run records belong in local data/run directories, with their source and license information.

See [the schema guide](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/schema.md), [data modality guide](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/data-modalities.md), and [runbook](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/runbook.md).

The [release checklist](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/release_checklist.md) records the publication gates.

## License

Project code, documentation and synthetic fixtures are licensed under
[Apache-2.0](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/LICENSE), with the public tensile case materials listed in
[THIRD_PARTY_NOTICES.md](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/THIRD_PARTY_NOTICES.md) distributed under CC-BY-4.0.
That notice records the KupferDigital authors, source version and processing.
Dependencies and external inputs retain their own licenses. See the
[license review](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/docs/licensing.md) and [changelog](https://github.com/17636365690/experiment-to-cpfe-pipeline/blob/v0.1.0/CHANGELOG.md).
