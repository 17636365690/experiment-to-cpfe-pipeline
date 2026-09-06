# Abaqus toolchain recheck — 2026-09-05

## Outcome and scope

The project drive became accessible again. The configured local Abaqus wrapper
passed `verify -user_std -retainFiles`. The pipeline's `run_abaqus` API then ran
one datacheck and one analysis, each with `cpus=1`, in distinct fresh ASCII-only
directories. Both returned completed, with separate compile and link evidence.
The analysis produced a real ODB, STA, DAT and MSG; the STA confirms completion.
Abaqus Python opened the ODB read-only: Step-1 has three frames and Step-2 has two.
The final frames contain A, E, RF, S, U and V.

This is the installed Abaqus **DISP verification example**, not a crystal-plasticity
UMAT or a public experimental dataset. It confirms the tested compiler/linker/
solver path only. CPFE sample readiness remains false; no units, orientations,
constitutive law or calibration parameters were inferred.

## Code changes and tests

- `src/experiment_to_cpfe/solvers/abaqus/runner.py`: recognize ordered Abaqus
  Standard/Explicit Begin/End compilation and linking markers; expose separate
  statuses; preserve failure on recognized Intel compiler/linker diagnostics;
  decode partial byte output on timeout instead of raising a second exception.
- `src/experiment_to_cpfe/pipeline.py`: include separate compile/link statuses in
  stage records, retaining the existing combined status for compatibility.
- `tests/fixtures/fake_solver.py`: replace invented success strings with driver
  marker fixtures and add independent compiler/linker failures.
- `tests/unit/test_abaqus_runner.py`: verify marker recognition, compile/link
  separation and timeout log retention.

Before implementation, the targeted suite had **4 failed, 6 passed**, exposing the
unsupported real marker format, absent separate statuses and timeout TypeError.
After implementation, it had **10 passed**. The full suite has **76 passed,
1 skipped** (the opt-in integration test). The real API runs above are additional
manual integration checks, not the skipped test.

Commands executed from the checkout:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_abaqus_runner.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m build
git diff --check
& .\runs\toolchain\abaqus_with_oneapi.bat verify -user_std -retainFiles
```

The API invocations and their exact effective commands are recorded in the local
`reports/datacheck_result.json` and `reports/analysis_result.json`. Each used a
180-second timeout. The initial vendor verification output was created under
`verify/`, then moved without overwriting into the ignored recheck run directory
after completion. No files were deleted.

## Artifacts, evidence and provenance

Local-only artifacts are under `runs/compiler-recheck-20260905/`:

- `verify/user_std/`: unmodified installed vendor inputs, vendor verification
  logs and outputs, including the official reference comparison PASS.
- `runner-datacheck/` and `runner-analysis/`: independent stages and their logs.
- `reports/`: run manifest, validation, solver readiness, QA and stage receipts.

Analysis ODB SHA-256:
`15063b989238f2d13663c270e3708e2ef32d90e7042f99f8ef4bbae56c77bbef`.
The local run manifest records input, wrapper, code, log and output hashes;
`manifest.sha256` records the manifest's hash without a self-reference.

Evidence classification: installed INP/Fortran are **input**; ODB and solver
fields are **simulated**. There is no measured or inferred material evidence in
this run. No data conversion or lossy conversion occurred. The local vendor
example was used only for optional integration verification; neither its source
nor its outputs are part of the public repository. The report and generic code
do not contain developer-machine absolute paths.

## Limitations and next stage

- ifx reports unsupported `/Qprec-sqrt` and `/Qfp-stack-check` options; the vendor
  verification also reports LNK4210. These warnings remain in the retained logs.
  No global Abaqus settings were changed to hide them.
- The parser covers tested English driver markers and recognized Intel
  diagnostics, not every compiler or locale. Unknown evidence stays unverified
  or missing, rather than being claimed as successful compilation.
- No S/LE/PEEQ/STATEV dataset was exported: this example does not contain all those
  fields. Missing fields were not filled with zero.
- These checks do not fix or validate recursive INP include staging, fresh-stage
  CLI orchestration, the complete readiness gate or ODB-to-HDF5 semantics.
- The next stage is fixed-revision public NTNU bundle acquisition and provenance
  checks, followed by include staging and a bounded CPFE solve when its metadata
  requirements are met. AZ31B experimental ingestion remains a separate sample.
- No GitHub push was performed for this recheck.

The distinction between data-check and analysis completion follows the
[Abaqus 2025 model-checking documentation](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEGSARefMap/simagsa-t-abscheckinput.htm).
