import pytest
from pydantic import ValidationError


def make_asset(**updates):
    from experiment_to_cpfe.assets.models import (
        AssetKind,
        AssetRef,
        DataLayer,
        SourceKind,
    )

    values = {
        "asset_id": "asset-raw-001",
        "parent_asset_id": None,
        "modality": AssetKind.ORIENTATION_MAP,
        "format": "ang",
        "uri": "fixtures/map.ang",
        "source_kind": SourceKind.MEASURED,
        "layer": DataLayer.RAW,
        "units": {"x": "um", "y": "um", "euler": "degree"},
        "coordinate_frame": "sample",
        "axis_order": ("y", "x"),
        "dtype": "float64",
        "shape": (2, 3),
        "native_layout": "generic_ang_columns",
        "sha256": "a" * 64,
        "license": "synthetic",
        "lossy_transformations": (),
    }
    values.update(updates)
    return AssetRef(**values)


def test_asset_enums_cover_required_modalities_and_layers():
    from experiment_to_cpfe.assets.models import AssetKind, DataLayer

    assert {kind.value for kind in AssetKind} == {
        "table",
        "time_series",
        "orientation_map",
        "image",
        "voxel_grid",
        "point_field",
        "mesh",
        "grain_graph",
        "field_sequence",
    }
    assert {layer.value for layer in DataLayer} == {
        "raw",
        "curated",
        "solver_input",
        "solver_output",
        "derived_ml",
    }


def test_asset_ref_preserves_native_and_lossy_provenance():
    asset = make_asset(
        asset_id="asset-curated-001",
        parent_asset_id="asset-raw-001",
        layer="curated",
        lossy_transformations=("nearest-neighbor resampling to 1 um",),
    )

    assert asset.parent_asset_id == "asset-raw-001"
    assert asset.native_layout == "generic_ang_columns"
    assert asset.lossy_transformations == (
        "nearest-neighbor resampling to 1 um",
    )


def test_asset_manifest_rejects_duplicate_ids():
    from experiment_to_cpfe.assets.models import AssetManifest

    first = make_asset()

    with pytest.raises(ValidationError, match="duplicate asset_id"):
        AssetManifest(assets=(first, first))


def test_asset_manifest_rejects_dangling_parent():
    from experiment_to_cpfe.assets.models import AssetManifest

    child = make_asset(
        asset_id="asset-curated-001",
        parent_asset_id="asset-missing",
        layer="curated",
    )

    with pytest.raises(ValidationError, match="parent_asset_id"):
        AssetManifest(assets=(child,))


def test_asset_manifest_resolves_parent_chain():
    from experiment_to_cpfe.assets.models import AssetManifest

    parent = make_asset()
    child = make_asset(
        asset_id="asset-curated-001",
        parent_asset_id=parent.asset_id,
        layer="curated",
    )
    manifest = AssetManifest(assets=(parent, child))

    assert manifest.get("asset-curated-001").parent_asset_id == parent.asset_id
