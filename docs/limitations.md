# Version 0.1 scope and operating conditions

Version 0.1 supports single-sample ingestion, validation, Abaqus preparation and
execution, result extraction, and HDF5/NPZ packaging. The
[format guide](data-modalities.md) identifies implemented parsers and formats
handled as native references.

## Scientific interpretation

A CPFE run needs a material model and parameters, mesh and grain assignments,
orientations, coordinate and unit conventions, loading conditions and output
definitions. Mechanical curves serve as calibration or validation targets.
Readiness checks this declared input contract. Physical validation additionally
examines constitutive behavior, parameter identification, mesh convergence and
agreement with experiments.

The checked Abaqus profile supports flat three-dimensional solid meshes, one
named isotropic-elastic, isotropic-plastic or explicit UMAT material, and one static displacement
step. It compares the deck with the sample declarations. Grain-orientation
columns can map to UMAT STATEV indices through complete
`*INITIAL CONDITIONS, TYPE=SOLUTION` initialization. Assembly scoping, periodic
equations and additional material/loading schemes need dedicated profiles.
The constitutive implementation comes from the supplied material model or UMAT.
The isotropic-plastic profile uses explicit elastic constants and an increasing
stress/plastic-strain table. Isotropic continuum models can declare a material
region and a reasoned inapplicable orientation. Crystalline profiles retain their
orientation and grain-assignment requirements.

Units are explicit per quantity. Table adapters execute declared affine
conversions and preserve source and target units. Coordinate transforms,
spatial registration and time synchronization require their own definitions.
`measured`, `inferred`, `input` and `simulated` record evidence origin, while
synthetic fixtures retain their generator description.

## Input and result coverage

Configured ANG/CTF/text EBSD, selected HDF5 datasets, MAT5 numeric/struct/cell
arrays, multichannel NPY, instrument blocks and XLSX value blocks have readers.
Selected spreadsheet formulas need an evaluated-value export. Vendor binary
EBSD and MATLAB class/MCOS data use upstream numerical exports.

Geometry support includes scalar ASCII VTI and a selected Gmsh 2.2 ASCII profile
with native Neper Rodrigues orientations. Binary/vector VTI, general VTK,
DAMASK result semantics and FEPX execution are subsequent adapter work.
Image correlation, segmentation, meshing and graph construction supply inputs
through upstream tools.

ODB extraction reads requested field outputs and reports missing fields or
locations. Small-strain `E` and logarithmic strain `LE` retain their distinct
field names and measures. Broader history outputs and homogenized response
calculations need additional extractors or postprocessing.

The complete sample contract includes coordinates and orientation applicability.
`pipeline adapt` handles earlier ingestion work, keeping selected arrays and
listing declarations needed for promotion. The
[native adapter guide](native-adapters.md) gives configurations and examples.

## Working size and data quality

The default workflow processes a small sample. Several readers and exports hold
arrays in memory. HDF5 slicing and NPY selection bound the requested array,
while peak memory also depends on compressed chunks and selected MAT5 variables.
MAT5 cell/struct decoding loads the selected variable before accessing a leaf.
HDF5 reference/compound and external/virtual storage need an upstream conversion
that records their dependencies.

Quality masks and residuals preserve source values. Drafts retain nonfinite
entries for inspection, and canonical promotion uses an explicitly selected
finite subset. The training collection builder checks identities and group splits
across canonical files using a declared sample, experiment or case grouping.
Its target-source check keeps each raw target origin within one split, including
when that origin contains multiple specimens. The optional CPU MLP interface
trains explicitly grouped numerical bundles and selects its checkpoint on the
validation split. Distributed execution and broader training architectures are
later workflow extensions.

Training collection selection supports table columns and scalar array components,
exact identity alignment, shared row slicing and explicit affine conversions.
It holds the assembled collection in memory. Aggregation, interpolation and
registration belong in upstream processing with recorded definitions. See the
[training dataset guide](training-datasets.md) for input and output contracts.

## Verification and distribution

Source records and stage receipts keep inputs, conversions and outputs traceable.
Run manifests belong with local run artifacts. Public candidates contain generic
code, documentation and small synthetic fixtures.

The public NTNU input bundle still needs full unit/convention confirmation and
a profile for periodic equations. Existing toolchain/DISP checks establish the
compile/link path. The recorded synthetic elastic solve exercises ODB extraction
and HDF5/NPZ packaging against an analytic elastic result. Public experimental
CPFE validation remains a separate work item.

Project code uses Apache-2.0. The [license review](licensing.md) describes the
CC-BY-4.0 public tensile materials and separately licensed external inputs.
Build and test evidence is recorded in the [release checklist](release_checklist.md)
and dated verification reports.
