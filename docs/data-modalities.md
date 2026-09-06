# Data modalities and conversion rules

## Implementation scope

Registering an asset records its format, hash, evidence class and declared
metadata. It does not prove that the contents have been parsed or converted.
The table below distinguishes the current interfaces.

| Data or format | Available in version 0.1 | Required preparation or limitation |
|---|---|---|
| CSV, delimited TXT, JSON record arrays | Configured table ingestion | Explicit column map, delimiter where applicable, units and evidence class |
| Headered EBSD text | Generic text profile | Explicit column names, units and orientation convention |
| Native ANG/CTF text | Configured text profiles | ANG uses explicit zero-based column indices; CTF uses exact source header names; no orientation/unit inference |
| Vendor HDF5, h5ebsd, DREAM.3D | Layout inventory and explicit dataset-to-column mapping | Each selected component must yield aligned 1D rows; a layout name alone does not supply semantics or make a file canonical |
| OSC, CRC/CPR and other vendor binaries | Native asset references | Vendor-specific decoding remains an extension point |
| DIC/DVC point fields | CSV/TXT coordinate and component arrays | Explicit columns, units, frame and axes; no image correlation or automatic registration |
| Regular DIC/DVC grids and CT voxels | NPY, selected HDF5 dataset, nested JSON arrays, scalar ASCII VTI | Explicit spatial metadata, units and frame; VTI reads its own origin/spacing/extent |
| SEM, DIC and other images | Native image asset references | No image decoding, segmentation or DIC processing in the pipeline |
| Nodes, elements and grain assignments | Configured normalized tables and Abaqus input bundles | No general-purpose mesher or arbitrary mesh-format conversion |
| Grain graphs | `SamplePackage` arrays and NPZ/PyG export | Explicit node IDs, features, edge indices, directedness and feature units; no automatic grain-graph construction |
| Abaqus ODB field sequences | Abaqus-Python extraction followed by host loading | Completed recorded analysis, explicit requested fields/units/location and unchanged artifacts |
| DAMASK VTI/VTK/HDF5 and YAML, Neper/FEPX formats | Native asset references; generic scalar ASCII VTI and explicit HDF5 column mapping | Complete backend material/result semantics and solver execution are not implemented |
| Excel workbooks | Native asset references | Export selected sheets/blocks to supported tables with provenance; no XLSX ingestion adapter |

## Tables and time series

CSV, delimited TXT, and JSON record arrays require an explicit target-to-source column map and units. Typical records include force, displacement, stress, strain, temperature, time, cycle, and control mode. Mechanical curves are calibration or validation evidence unless a user separately supplies a complete material model and parameters.

## EBSD and orientation maps

Text profiles map coordinate, phase, orientation and quality columns explicitly.
Set `modality: orientation_map`, `format: ang` or `ctf`, and provide an
`adapter_config` with `profile`, `column_map` and `orientation`. ANG maps string
representations of zero-based column indices to normalized target names. CTF
uses exact column names from its header. Generic CSV/TXT uses named columns.
Unrecognized layouts fail rather than trying another vendor convention.

```yaml
adapter_config:
  profile: ang
  column_map:
    euler_1: '0'
    euler_2: '1'
    euler_3: '2'
    x: '3'
    y: '4'
    quality: '5'
    phase_id: '7'
  orientation:
    representation: euler
    convention: explicit-source-convention
    angle_units: radian
    crystal_symmetry: explicit-source-symmetry
```

This fragment illustrates configuration syntax, not a vendor-wide convention.
Use the actual file's columns, angle units and documented conventions. Asset
units must cover mapped target columns, and frame/axis metadata must be declared.
Native files remain unchanged; conversion provenance retains the original hash.

`inspect_hdf5_layout` inventories dataset paths, shapes and dtypes under an
explicit layout name. Semantic parsing additionally requires `dataset_map`,
such as `{x: 'Group/X', u: {path: 'Group/U', component: 0}}`. Each selection must
produce a one-dimensional column with the same row count; no implicit flattening
or transposition is applied. Orientation maps require the explicit orientation
declaration; point fields also name coordinate and field columns. Dataset names
do not determine units, phase definitions or crystal symmetry. Vendor HDF5 and
project HDF5 remain different contracts even with the same extension.

## Images and DIC/DVC fields

Reference/deformed images remain image assets. Point-field ingestion loads
coordinate and displacement/strain components in configured order. Regular
arrays use the voxel adapter and require origin, spacing, axis order, units and
coordinate frame. Interpolation, registration, smoothing and resampling require
separate implementations and child-asset records; describing an operation in a
loss record does not perform it.

## CT and voxel grids

NumPy, explicitly addressed HDF5 datasets, and tiny JSON synthetic fixtures preserve origin, spacing, axis order, dtype, shape, units, and frame. Future segmentation and voxel-to-mesh adapters must create new child assets and preserve raw scans.

The VTI adapter supports one full-extent ImageData Piece and a selected scalar
ASCII DataArray. Declare `array_name`, `association: PointData` or `CellData`,
spatial `units`, `value_units`, `coordinate_frame` and `axis_order: [z, y, x]`
under `adapter_config`. Asset units must separately describe spacing and the
selected value, for example `{spacing: mm, phase: '1'}`.

VTI origin, spacing and extent come from the file; conflicting configured values
are rejected. The adapter preserves native XYZ descriptors and records the
normalized ZYX sampling origin/spacing, using cell centers for CellData. PointData
allows singleton dimensions; CellData currently requires a full 3D grid. Binary,
appended, vector, multipiece, partial-extent and rotated-direction VTI require
additional adapters. The explicit array selection follows the
[VTK XML format](https://docs.vtk.org/en/latest/vtk_file_formats/vtkxml_file_format.html)
and its structured-grid ordering; it does not infer DAMASK field semantics.

## Meshes and microstructure mappings

Normalized mesh tables declare node and element IDs, connectivity, element type
and grain assignments. Native mesh files retain their original content and
hashes. Grain-to-element mappings must reference existing grain IDs. Readiness
and static checks cover the implemented contract, not every Abaqus keyword or
physical modeling choice. A mesh does not imply a material model or boundary
conditions.

## Grain graphs and field sequences

Grain graphs use `graph_node_ids`, `graph_node_features`, `graph_edge_index` and
optional `graph_edge_features`. `solver_inputs.graph_contract` supplies
directedness and feature names/units. Undirected graphs must contain explicit
reverse edges. PyG exports contain a real `torch_geometric.data.Data` object and
an embedded portable NPZ payload for non-graph records and metadata. No training
target or field-to-node registration is inferred.

ODB field sequences preserve step, frame, increment, time, instance, available
node/element/integration-point/section-point location labels, component, original
field name and field unit. NPZ and PyG exports retain the canonical HDF5 hash and
record the loss of HDF5 storage layout and unmodeled HDF5 attributes.

## Solver formats

Abaqus `.inp`, `.odb`, `.sta`, `.dat`, and `.msg` are distinct evidence artifacts.
Only the Abaqus backend currently executes and extracts solver results. DAMASK
`material.yaml`, `numerics.yaml`, VTI/VTK and HDF5 remain backend-specific assets.
Neper/FEPX `.tess`, `.tesr`, `.msh`, `.ori` and `.sim` may be referenced explicitly
without imposing Abaqus semantics.
