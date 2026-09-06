# Normalized schema

## Stable identifiers

Every sample declares `sample_id`, `experiment_id`, `microstructure_id`, `load_path_id`, and `schema_version`. Increment-level records carry `increment_id` when time or loading order matters.

## Evidence classes

- `measured`: directly observed experimental data.
- `inferred`: segmentation, interpolation, reconstruction, fitting, or another derived estimate.
- `input`: a deliberate solver or model input.
- `simulated`: output from a real solver or an explicitly identified synthetic generator.

Evidence class follows the source through representation changes. Converted measured EBSD remains measured, while a statistically reconstructed RVE is inferred.

## Asset contract

`AssetRef` records a stable asset ID, optional parent asset ID, modality, native
format and layout, URI, evidence class, data layer, units, coordinate frame,
axis order, dtype, shape, source hash, license and lossy transformations.
`descriptive_metadata` retains modality-specific descriptors such as voxel
origin/spacing, selected field columns and explicit orientation declarations.
`AssetManifest` rejects duplicate IDs, unresolved parents and parent cycles.

An optional `ConversionRecord` records source/target formats and integrity
receipts for files (`hash_scope: files`) or arrays (`hash_scope: logical_payload`).
`source_hash_verified=true` records local source-file agreement. ODB extraction
retains its own source asset and execution record.

Parsed external arrays retain their raw asset and add a `<raw-id>:normalized`
child in the curated layer. The child preserves evidence class, records selection
losses and points to its canonical array. Detailed array integrity metadata stays
with the conversion record.

Supported modalities are `table`, `time_series`, `orientation_map`, `image`, `voxel_grid`, `point_field`, `mesh`, `grain_graph`, and `field_sequence`. Data layers are `raw`, `curated`, `solver_input`, `solver_output`, and `derived_ml`.

## Spatial and tensor conventions

Coordinates declare a named frame, ordered axes and units. Orientations declare representation, convention, angle units where applicable and crystal symmetry. Tensor component order comes from the explicit input declaration.

A homogenized isotropic model can supply
`orientation: {representation: not_applicable, reason: ...}`. This represents
model applicability. Crystalline orientation data continue to use a resolved
Euler/quaternion/matrix convention. `material_region_mapping` assigns explicitly
named element sets for orientation-independent isotropic models, while
`microstructure_mapping` retains grain identity for crystalline models.

Field records carry units by field name. Stress, displacement and a state variable may have
different dimensions. State variables require individual declarations.
The field-location identity includes the step/frame, original field/component,
instance, position and available node/element/integration-point/section-point
labels. These fields jointly identify each record.

`experiment_to_cpfe/_resources/field_contract.py` is the dependency-free shared
contract for the standalone Abaqus extractor, host numeric parsing and record
identity validation. Its version is recorded in extraction metadata. Native
string identifiers retain their spelling; missing inapplicable labels remain
empty and nonfinite numeric values are rejected.

`SamplePackage` holds metadata, reserved normalized tables, named NumPy arrays,
assets and explicit solver inputs. Reserved tables are `grains`,
`grain_boundaries`, `mesh_nodes`, `mesh_elements`, `load_history`,
`measured_observations` and `simulation_records`. The package does not infer that
rows from different evidence classes correspond physically.

`NativeDraft` is a separate ingestion result. It holds selected arrays and
unresolved semantic conditions without filling the complete sample's metadata.
`PipelineConfig.imports` promotes eligible drafts into ordinary arrays/assets.
Per-array meanings retain component axes, spatial descriptors, tensor/reference
conventions, quality and entity links, and target grouping. The
[native guide](native-adapters.md) describes these declarations.

## Canonical HDF5 groups

```text
/meta
/assets
/geometry
/mesh
/grains
/grain_boundaries
/load_history
/measured
/simulation
/macro_response
/derived
/provenance
/quality
```

The root attributes `container_format=experiment-to-cpfe` and
`container_version=1` identify the canonical format. The sample schema version
is a separate value under `/meta`. The reader rejects foreign or unsupported
container identifiers.

Table records are stored as JSON with numeric common columns additionally
available as datasets. Arrays live under `/derived/arrays`; empty reserved
groups do not mean a physical quantity was computed. Asset metadata and the
source manifest retain provenance. The file does not embed every original
vendor binary or Abaqus ODB.

Mapped table rows carry `source_asset_id` and `source_kind`. These reserved
fields bind every row to its raw source and its declared column units. Each
source also has a curated `normalized-table-json` child with a conversion
receipt, source hash and logical row-payload hash. Its source-selected row
subset is verified on HDF5 writing and reading; reordering, deleting or changing
rows requires a new conversion. The logical hash is not presented as a file
hash. Column selection and original text-format loss are recorded while the raw
file remains unchanged. Independent sources retain separate clocks and IDs.

Native blocks also retain physical source rows, worksheet and specimen metadata.
For explicit unit conversions, raw assets describe source units, curated assets
describe target units, and the source view records `normalized_units` for its
mapped output rows. Native mesh connectivity retains original node IDs; graph
edge indices instead address rows of `graph_node_ids`.

Numeric, Boolean, fixed-width byte and Unicode arrays, including scalars and
empty arrays, have explicit dtype/shape metadata. Unicode is stored in UTF-8 with
its original NumPy dtype descriptor restored on read. Object, structured and
datetime arrays require prior normalization and are rejected before output
creation; embedded NUL or invalid UTF-8 Unicode content is not supported.

HDF5 is the normalized project container, not a universal interpretation of
arbitrary vendor HDF5 files. Vendor files remain external native assets with
hashes and explicit layout descriptions. NPZ/PyG exports derive from a verified
canonical HDF5 file and record their loss of HDF5 storage layout, compression and
attributes outside the modeled sample contract.
