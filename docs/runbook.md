# Pipeline runbook

## 1. Validate

```text
pipeline validate --config sample.yaml --run-dir runs/sample-001
```

Creates a new, non-empty-protected run directory and writes the normalized
sample, `input/input_lock.json`, and the four reports under `reports/`:
`validation.json`, `solver_readiness.json`, `qa_report.md`, and `run_manifest.json`.
The input lock binds configuration, source files and the effective validation
policy to SHA-256 hashes. Later stages check that their prerequisites and
artifacts still match. Use a new run when inputs change.

Data validation and solver readiness are distinct results. A valid experimental
sample can have `validation.passed=true` while `solver_readiness.ready=false`.
The combined validate stage then reports incomplete solver inputs, but data
export remains possible. Inspect both reports before choosing the next stage.

The authoritative default policy is the installed package resource
`experiment_to_cpfe/_resources/validation_policy.yaml`.
`configs/validation_policy.yaml` is a human-readable template, not an automatic
runtime override. Editing that template alone does not change validation.

## 2. Build INP

```text
pipeline build-inp --config sample.yaml --run-dir runs/sample-001
```

Requires a solver-ready sample. The template path writes `input/model.inp` and a
static-check report. Native input bundles use the explicit `abaqus.input_bundle`
configuration described below. Content and readiness checks do not establish
physical calibration or solver convergence. Existing output is not overwritten.

### Checked solver profiles

The initial checked profile is a flat three-dimensional solid model, one named
material and one named static step with explicit displacement loading. Supported
connectivity types are C3D4, C3D8, C3D8R, C3D10, C3D20 and C3D20R. The declared
grain mapping must assign every actual element once, and declared nodes,
connectivity, sections, material constants, boundaries and output requests must
agree with the deck. The gate also checks rigid-body constraint rank.

`solver_inputs.material_model` selects one of:

- `isotropic_elastic`: `material_parameters: {E: ..., nu: ...}` must match the
  plain `*ELASTIC` definition; PEEQ and SDV outputs are incompatible with this
  profile.
- `umat`: explicitly supply `constants`, one `constant_units` entry per constant,
  and positive `depvar` under `material_parameters`. These must match
  `*USER MATERIAL` and `*DEPVAR`; separately configure an authorized
  `abaqus.user_subroutine`.

`orientation_required: false` is appropriate only when the declared material
does not require orientation assignment. For a UMAT that expects orientation in
STATEV, set `orientation_required: true` and explicitly map grain-table columns
to one-based state-variable indices:

```yaml
solver_inputs:
  orientation_required: true
  orientation_state_variables:
    columns: [q0, q1, q2, q3]
    indices: [1, 2, 3, 4]
```

The actual deck must supply `*INITIAL CONDITIONS, TYPE=SOLUTION` values for every
element through explicit element labels or sets, with every DEPVAR value
provided. The first row supplies a target and up to seven values; continuation
rows supply up to eight values each. The gate verifies complete, non-overlapping
coverage and exact agreement of the selected STATEV values with mapped grain
orientations. Euler, quaternion and rotation-matrix representations require
their explicit source conventions; quaternion norm and proper matrix rotations
are checked. The UMAT must actually interpret these entries according to those
declared conventions; this check does not implement its constitutive equations.

Other orientation-assignment schemes, assembly-scoped models, periodic equations,
unsupported keywords/options and additional loading procedures remain blocked
by this initial profile. The synthetic example demonstrates the isotropic
profile; toggling the orientation flag cannot supply missing CPFE physics.

The Python API `check_deck_readiness(sample, deck_text)` checks declarations
against expanded actual deck text; the native-bundle path resolves and hashes
INCLUDE files before calling it. `check_solver_readiness(sample, "abaqus_cpfe")`
checks the configured template blocks. Neither function estimates material
parameters or changes scientific conventions.

### Native INCLUDE bundles

An existing native deck must declare a source root, entrypoint, original
submission directory, required auxiliary files and license. Relative
`source_root` is resolved against the YAML file. Entrypoint, submission directory
and auxiliary file paths are resolved against that source root.

```yaml
abaqus:
  command: [abaqus]
  job_name: sample_001
  input_bundle:
    source_root: native_inputs
    entrypoint: model/main.inp
    submission_dir: model
    auxiliary_files: []
    license: user-supplied-authorized-input
```

This is a configuration fragment, not a complete solver-ready sample. Replace
the license description with the actual authorization/source terms. INCLUDE
references are resolved with the explicitly declared submission-directory
semantics. Missing dependencies, cycles, paths escaping the source root,
excessive file count/size and existing destinations are rejected.

```text
pipeline stage-input-bundle --config sample.yaml --run-dir runs/sample-001
```

This optional stage makes a byte-preserving, hash-recorded copy under
`input/native_bundle/` with `reports/native_bundle.json`. For a non-ASCII run
path, an explicitly configured ASCII temporary root holds the prepared bundle;
the report records its actual location. The stage establishes file
staging only. `build-inp` and `run-abaqus` must still pass their solver checks;
staging cannot supply missing units or material metadata.

## 3. Abaqus datacheck

```text
pipeline run-abaqus --config sample.yaml --run-dir runs/sample-001 --stage datacheck
```

The Abaqus command is read from configuration or `EXP2CPFE_ABAQUS_COMMAND`.
Use command tokens such as `command: [abaqus]`; machine-specific compiler setup
belongs in a local wrapper referenced by configuration/environment, outside the
public source tree. An unavailable executable or an invalid staging path is
reported as blocked. Solver errors and missing evidence are reported with the
captured logs. A zero process exit code alone is insufficient.

Datacheck and analysis use separate stage directories. Default execution is one
CPU with a configured timeout; the chosen staging directory must be ASCII-only.
Run datacheck first and inspect its status before analysis.

Set `abaqus.ascii_temp_root` to a local ASCII-only directory when execution needs
to occur outside the run directory. Each stage creates a fresh temporary job
directory beneath that root, runs there, then archives outputs into
`solver/<stage>/` under the run. Native bundles preserve their relative
submission directory inside that archive. Existing stage output is not reused.
Temporary inputs and native source originals remain separate, and the recorded
command keeps the actual execution location for provenance.

## 4. Abaqus analysis

```text
pipeline run-abaqus --config sample.yaml --run-dir runs/sample-001 --stage analysis
```

Analysis requires ODB, STA, DAT, and MSG artifacts plus a successful STA completion statement. Datacheck, optional user-subroutine compile/link status, and analysis are recorded separately.

## 5. Extract ODB

```text
pipeline extract-odb --config sample.yaml --run-dir runs/sample-001
```

The packaged extraction script runs under `abaqus python` and imports
`odbAccess` there. The host environment reads JSON/CSV output and writes HDF5.
Extraction requires a successful recorded analysis and unchanged registered
solver artifacts. ODB access is read-only.

Declare the requested fields and their physical units individually:

```yaml
abaqus:
  required_fields: [S, E, U, RF]
  extraction_position: native
  extraction_max_records: 1000000
  field_units: {S: MPa, E: '1', U: mm, RF: N}
```

These units are an illustrative consistent declaration, not default units.
Use only units supported by the actual model. This small-strain example requests
`E`; a suitable finite-strain model may request logarithmic strain `LE`. If
Abaqus replaces an unavailable request with a different field, the extractor
reports the requested field as missing rather than silently aliasing E and LE.
Available position selections are
`integration_point`, `nodal`, `element_nodal`, `element_face`, `centroid`, and
`native`; `native` retains stored locations without interpolating new values.
For user-material state variables, declare units for the actual names such as
`SDV1` and `SDV2`; a single `SDV` unit does not cover heterogeneous state variables.
Only request PEEQ/SDV when the model provides those outputs.

Missing fields/locations are recorded per frame. Missing S, LE, PEEQ or SDV
components are never substituted with zeros. Original field/component names,
available location labels and numerical precision are retained in the extracted
records; field units are bound in the host metadata.

## 6. Export

```text
pipeline export --config sample.yaml --run-dir runs/sample-001 --format hdf5
pipeline export --config sample.yaml --run-dir runs/sample-001 --format npz
pipeline export --config sample.yaml --run-dir runs/sample-001 --format pyg
```

HDF5 is canonical. NPZ and PyG read the completed HDF5 export and verify its
recorded source hash. Run HDF5 export before either derived export. NPZ uses
non-pickled arrays plus JSON metadata and can be opened with
`numpy.load(path, allow_pickle=False)`.

PyG requires the optional `ml` dependencies, explicit graph node IDs/features,
integer edge indices and a graph contract with names, units and directedness.
The exported `Data` object embeds a portable package for records that are not
graph features. It does not assign experimental observations or ODB fields to
graph nodes or generate training targets. Load serialized PyTorch objects only
from a trusted source.

Formal exports require the hash-bound `validation.json` to report `passed: true`.
This is separate from solver readiness: valid experimental data may be exported
without a mesh or material model, even when the combined validate stage reports
incomplete solver inputs. Such an export does not make the sample solver-ready.

Once an `extract-odb` attempt is recorded in the run manifest, export requires its
successful completion and unchanged, registered `metadata.json` and `frames.csv`.
Deleting or moving the extraction directory cannot revert the run to an
experiment-only export. Missing evidence produces `blocked`; use a new run for a
different workflow rather than removing stage artifacts.

## Inspect

```text
pipeline inspect --run-dir runs/sample-001
```

Prints the manifest with stage statuses, hashes, artifacts, commands, and limitations.

## Verification and scope

```text
python -m pytest -q
python -m build
```

These checks need no Abaqus. The installed-wheel integration test is separately
enabled by `EXP2CPFE_WHEEL_DIR`; the opt-in solver test requires
`EXP2CPFE_RUN_ABAQUS=1`, `EXP2CPFE_ABAQUS_CONFIG` and
`EXP2CPFE_ABAQUS_RUN_DIR`. It starts from a nonexistent run directory and runs
validate, build-inp, datacheck, analysis, extraction, HDF5 export and NPZ export.
The user-supplied configuration must already declare a complete solver-ready,
authorized model, one CPU, a timeout of at most 600 seconds per stage, and
nonempty requested output fields with their units. The test enforces at most
1000 elements and 10000 nodes before launching Abaqus. It does not prepare or
calibrate missing material inputs.

For a local PowerShell session, after preparing that small configuration:

```powershell
$env:EXP2CPFE_RUN_ABAQUS = "1"
$env:EXP2CPFE_ABAQUS_CONFIG = "my-authorized-smoke.yaml"
$env:EXP2CPFE_ABAQUS_RUN_DIR = "runs/real-integration-new"
python -m pytest -q -rs tests/integration/test_abaqus_optional.py
Remove-Item Env:EXP2CPFE_RUN_ABAQUS
```

The test verifies a nonempty ODB, read-only ODB hash stability, nonempty simulated
HDF5 records with finite values and units, NPZ agreement, all seven completed
stage receipts and recorded artifact hashes. An unavailable command or license
reported as `blocked` produces an explicit pytest **skip**, never a passing
solver test. Invalid model contracts and failed analysis/extraction/export
remain failures. Inspect the `-rs` skip reasons when reporting results.

Do not infer a real CPFE validation claim from fake-solver fixtures or offline
synthetic tests. See [limitations](limitations.md) for the remaining scientific
and adapter scope.
