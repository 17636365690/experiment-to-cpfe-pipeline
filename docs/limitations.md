# Version 0.1 scope and limitations

The first version targets reproducible single-sample ingestion, validation,
Abaqus preparation/execution and data packaging. The supported paths and
registration-only formats are listed in [data-modalities.md](data-modalities.md).
An extension point is not a completed adapter.

## Scientific interpretation

- A complete CPFE material model, parameters, mesh, grain assignments,
  orientations, coordinate/unit conventions, boundary conditions and outputs
  must be supplied explicitly. The package does not calibrate a constitutive
  model automatically from a stress–strain curve.
- Readiness checks establish the declared input contract. They do not validate
  constitutive equations, parameter identifiability, mesh convergence or
  agreement with experiments. Abaqus datacheck and a successful analysis do not
  replace those scientific checks.
- The checked solver profile supports flat three-dimensional solid meshes, one
  named isotropic-elastic or explicit UMAT material, and one static displacement
  loading step. It checks actual deck content against declarations. Explicit
  grain-orientation columns may be mapped to UMAT STATEV indices and verified
  against complete `*INITIAL CONDITIONS, TYPE=SOLUTION` initialization. Other
  orientation schemes, assembly scoping, periodic equations and additional
  constitutive/loading semantics require adapters and are blocked by this initial
  profile. UMAT support does not itself implement crystal plasticity.
- Unit strings are declared metadata; the pipeline does not perform a general
  dimensional-analysis or unit-conversion calculation. Orientation conventions
  are not silently converted. Coordinate transforms, spatial registration and
  time synchronization are not automatically estimated.
- `measured`, `inferred`, `input` and `simulated` describe evidence origin. Tiny
  synthetic fixtures carry explicit synthetic descriptions. Test fixtures and
  successful export tests are not new experimental or solver evidence.

## Input and result coverage

- Configured ANG/CTF and generic EBSD text profiles and explicit HDF5 dataset
  mapping are supported. Vendor binary EBSD decoding and automatic HDF5 layout
  discovery/translation are not.
- Image correlation, segmentation, voxel-to-mesh conversion, general mesh
  generation and automatic grain-graph extraction are not implemented.
- Scalar ASCII VTI ImageData has an explicit adapter. Binary/appended/vector VTI,
  general VTK layouts, DAMASK-specific material/result semantics and Neper/FEPX
  semantic ingestion/execution remain extension work. Excel blocks must first be
  converted explicitly to a supported table format with source and loss records.
- ODB extraction is limited to requested field outputs. It does not currently
  extract every Abaqus history-output type or compute homogenized stress/strain
  curves. Requested absent fields or locations are reported, never zero-filled.
  Small-strain `E` and logarithmic strain `LE` are distinct fields and are never
  substituted for one another by the extractor.
- Large datasets are loaded into memory by several adapters and exports. The
  default workflow is one small sample; distributed execution, streaming
  conversion, resumable batch scheduling and model training are out of scope.
- The sample contract currently requires coordinate and orientation metadata
  even for some table-only studies. Supply only documented conventions; retain
  unresolved material as native references until it can be normalized honestly.

## Reproducibility and release

Input and artifact hashes detect accidental changes and bind stage evidence.
They are not signatures and do not authenticate an arbitrary external ODB or
protect against an actor who can rewrite both data and manifests. The trusted
runner executable and the source/license statements remain the caller's
responsibility. Run manifests may contain local paths and belong outside the
public repository.

The public NTNU source manifest pins a small input bundle and its file hashes.
Its presence does not establish a verified public CPFE-to-HDF5 scientific
benchmark. Full physical unit/convention confirmation is still required before
that case can pass solver readiness, and its periodic equations require an
additional checked profile. Local toolchain/DISP checks verify the installed
compile/link path. The small synthetic elastic solve additionally exercises real
ODB extraction and HDF5/NPZ packaging with an analytic elastic check; it does not
validate NTNU crystal-plasticity physics against public experiments.

The repository has no project-wide license selection yet. External MIT or
CC-BY source descriptions apply only to those sources and do not license this
project. Tests, build results, public-file review and remaining release actions
are recorded in the [release checklist](release_checklist.md) and dated
verification reports.
