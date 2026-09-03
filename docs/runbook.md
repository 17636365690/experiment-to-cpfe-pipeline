# Pipeline runbook

## 1. Validate

```text
pipeline validate --config sample.yaml --run-dir runs/sample-001
```

Creates a new, non-empty-protected run directory and writes the normalized sample, `validation.json`, `solver_readiness.json`, `qa_report.md`, and `run_manifest.json`. Unknown units, frames, conventions, dangling IDs, nonfinite arrays, and incomplete solver inputs are reported rather than guessed.

## 2. Build INP

```text
pipeline build-inp --config sample.yaml --run-dir runs/sample-001
```

Requires a ready sample, an explicit template, and configured replacements. It writes `input/model.inp` and a static-check report. Existing output is never overwritten.

## 3. Abaqus datacheck

```text
pipeline run-abaqus --config sample.yaml --run-dir runs/sample-001 --stage datacheck
```

The Abaqus command is read from configuration or `EXP2CPFE_ABAQUS_COMMAND`. Missing executables, licenses, or non-ASCII staging paths produce `blocked`. Expected DAT/MSG evidence is required even when the process exit code is zero.

## 4. Abaqus analysis

```text
pipeline run-abaqus --config sample.yaml --run-dir runs/sample-001 --stage analysis
```

Analysis requires ODB, STA, DAT, and MSG artifacts plus a successful STA completion statement. Datacheck, optional user-subroutine compile/link status, and analysis are recorded separately.

## 5. Extract ODB

```text
pipeline extract-odb --config sample.yaml --run-dir runs/sample-001
```

The extraction script runs under `abaqus python` and imports `odbAccess` there. The host environment reads JSON/CSV output. Missing requested fields such as S, LE, PEEQ, or STATEV remain explicit missing fields; zeros are never substituted.

## 6. Export

```text
pipeline export --config sample.yaml --run-dir runs/sample-001 --format hdf5
pipeline export --config sample.yaml --run-dir runs/sample-001 --format npz
pipeline export --config sample.yaml --run-dir runs/sample-001 --format pyg
```

HDF5 is canonical. NPZ and PyG are derived and require the HDF5 source hash. PyG export requires the optional `ml` dependency group and graph arrays.

## Inspect

```text
pipeline inspect --run-dir runs/sample-001
```

Prints the manifest with stage statuses, hashes, artifacts, commands, and limitations.
