import hashlib


def test_registry_preserves_native_layout_and_vendor_bytes(tmp_path):
    from experiment_to_cpfe.assets.models import AssetKind, DataLayer, SourceKind
    from experiment_to_cpfe.assets.registry import inspect_asset, register_asset

    source = tmp_path / "vendor.h5"
    source.write_bytes(b"not-a-universal-layout")
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    inspection = inspect_asset(source, AssetKind.ORIENTATION_MAP)
    asset = register_asset(
        source,
        inspection,
        SourceKind.MEASURED,
        DataLayer.RAW,
        parent_asset_id=None,
        license="user-supplied",
    )

    assert asset.modality is AssetKind.ORIENTATION_MAP
    assert asset.native_layout == "uninspected_hdf5"
    assert asset.sha256 == before
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_register_derived_asset_preserves_parent_and_losses(tmp_path):
    from experiment_to_cpfe.assets.models import AssetKind, DataLayer, SourceKind
    from experiment_to_cpfe.assets.registry import AssetInspection, register_asset

    source = tmp_path / "normalized.npy"
    source.write_bytes(b"derived")
    inspection = AssetInspection(
        path=source,
        modality=AssetKind.VOXEL_GRID,
        format="npy",
        size_bytes=7,
        dtype="uint8",
        shape=(2, 2, 2),
        axis_order=("z", "y", "x"),
        units={"spacing": "um"},
        coordinate_frame="ct",
        native_layout="numpy_c_order",
        lossy_transformations=("threshold segmentation",),
        warnings=(),
    )
    asset = register_asset(
        source,
        inspection,
        SourceKind.INFERRED,
        DataLayer.CURATED,
        parent_asset_id="asset-raw-ct",
        license="synthetic",
    )

    assert asset.parent_asset_id == "asset-raw-ct"
    assert asset.lossy_transformations == ("threshold segmentation",)
