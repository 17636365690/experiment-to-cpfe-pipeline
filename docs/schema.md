# Normalized schema

## Stable identifiers

Every sample declares `sample_id`, `experiment_id`, `microstructure_id`, `load_path_id`, and `schema_version`. Increment-level records carry `increment_id` when time or loading order matters.

## Evidence classes

- `measured`: directly observed experimental data.
- `inferred`: segmentation, interpolation, reconstruction, fitting, or another derived estimate.
- `input`: a deliberate solver or model input.
- `simulated`: output from a real solver or an explicitly identified synthetic generator.

Changing representation does not change evidence class. For example, converting measured EBSD text into HDF5 remains measured, while a statistically reconstructed RVE is inferred.

## Asset contract

`AssetRef` records a stable asset ID, optional parent asset ID, modality, native format and layout, URI, evidence class, data layer, units, coordinate frame, axis order, dtype, shape, source hash, license, and lossy transformations. Parent links must resolve within an `AssetManifest`.

Supported modalities are `table`, `time_series`, `orientation_map`, `image`, `voxel_grid`, `point_field`, `mesh`, `grain_graph`, and `field_sequence`. Data layers are `raw`, `curated`, `solver_input`, `solver_output`, and `derived_ml`.

## Spatial and tensor conventions

Coordinates declare a named frame, ordered axes, and units. Orientations declare representation, convention, angle units when applicable, and crystal symmetry. Tensor component order is explicit. No adapter guesses any of these values.

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

HDF5 is the normalized project container, not a universal interpretation of arbitrary vendor HDF5 files. Vendor files remain external native assets with hashes and named layout profiles.
