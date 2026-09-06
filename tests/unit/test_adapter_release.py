"""Regression cases for lossless, explicit public adapter contracts."""

import json

import h5py
import numpy as np
import pytest

from experiment_to_cpfe.adapters.ebsd import load_ebsd_text
from experiment_to_cpfe.adapters.fields import load_point_field
from experiment_to_cpfe.adapters.tabular import assemble_sample
from experiment_to_cpfe.adapters.voxel import load_voxel_array
from experiment_to_cpfe.config import load_pipeline_config
from experiment_to_cpfe.datasets.hdf5 import read_hdf5, write_hdf5
from experiment_to_cpfe.schema.io import dump_sample_json, load_sample_json


def test_voxel_spatial_metadata_survives_full_roundtrip(multimodal_sample_config, tmp_path):
    config = load_pipeline_config(multimodal_sample_config)
    assets = list(config.assets)
    voxel = assets[1]
    assets[1] = voxel.model_copy(update={"adapter_config": {
        **voxel.adapter_config, "origin": [11, 12, 13], "spacing": [0.2, 0.3, 0.4],
        "lossy_transformations": ["upstream thresholding"],
    }, "lossy_transformations": ("upstream crop",)})
    sample = assemble_sample(config.model_copy(update={"assets": tuple(assets)}))
    path = tmp_path / "sample.h5"
    write_hdf5(sample, path)
    restored = read_hdf5(path)
    asset = next(a for a in restored.assets if a.asset_id == "ct-voxels")
    assert asset.descriptive_metadata["origin"] == [11.0, 12.0, 13.0]
    assert asset.descriptive_metadata["spacing"] == [0.2, 0.3, 0.4]
    assert asset.descriptive_metadata["axis_order"] == ["z", "y", "x"]
    assert asset.lossy_transformations == ("upstream crop", "upstream thresholding")
    assert asset.source_kind.value == "measured"
    assert asset.sha256 == next(a.sha256 for a in sample.assets if a.asset_id == asset.asset_id)
    np.testing.assert_array_equal(restored.arrays[asset.asset_id], np.arange(8).reshape(2, 2, 2))


@pytest.mark.parametrize("changes", [{"origin": [float("nan"), 0]}, {"spacing": [1, float("inf")]}, {"axis_order": ["x", "x"]}])
def test_voxel_rejects_invalid_spatial_metadata(tmp_path, changes):
    path = tmp_path / "voxel.npy"
    np.save(path, np.ones((2, 2)))
    config = {"format": "npy", "origin": [0, 0], "spacing": [1, 1], "axis_order": ["y", "x"], "units": "mm", "coordinate_frame": "scanner", **changes}
    with pytest.raises(ValueError):
        load_voxel_array(path, config)


def test_voxel_rejects_nonfinite_values(tmp_path):
    path = tmp_path / "voxel.npy"
    np.save(path, np.array([[np.nan]]))
    with pytest.raises(ValueError, match="finite"):
        load_voxel_array(path, {"format": "npy", "origin": [0, 0], "spacing": [1, 1], "axis_order": ["y", "x"], "units": "mm", "coordinate_frame": "scanner"})


@pytest.mark.parametrize("changes", [{"axis_order": ["point"]}, {"field_columns": ["x"]}, {"units": {"x": "mm", "y": "", "u": "mm"}}])
def test_point_field_rejects_ambiguous_layout(tmp_path, changes):
    path = tmp_path / "dic.csv"
    path.write_text("x,y,u\n0,0,0.1\n", encoding="utf-8")
    config = {"format": "csv", "delimiter": ",", "coordinate_columns": ["x", "y"], "field_columns": ["u"], "units": {"x": "mm", "y": "mm", "u": "mm"}, "coordinate_frame": "camera", "axis_order": ["point", "component"], **changes}
    with pytest.raises(ValueError):
        load_point_field(path, config)


def test_point_field_rejects_nonfinite_values(tmp_path):
    path = tmp_path / "dic.csv"
    path.write_text("x,y,u\n0,0,nan\n", encoding="utf-8")
    with pytest.raises(ValueError, match="finite"):
        load_point_field(path, {"format": "csv", "delimiter": ",", "coordinate_columns": ["x", "y"], "field_columns": ["u"], "units": {"x": "mm", "y": "mm", "u": "mm"}, "coordinate_frame": "camera", "axis_order": ["point", "component"]})


def test_canonical_reader_rejects_vendor_file_even_with_familiar_groups(tmp_path, make_sample):
    path = tmp_path / "vendor.h5"
    write_hdf5(make_sample(), path)
    with h5py.File(path, "r+") as handle:
        for key in list(handle.attrs):
            del handle.attrs[key]
    with pytest.raises(ValueError, match="canonical"):
        read_hdf5(path)


def test_canonical_reader_rejects_unknown_version(tmp_path, make_sample):
    path = tmp_path / "future.h5"
    write_hdf5(make_sample(), path)
    with h5py.File(path, "r+") as handle:
        handle.attrs["container_version"] = "999"
    with pytest.raises(ValueError, match="version"):
        read_hdf5(path)


def test_scalar_hdf5_and_empty_json_roundtrip(tmp_path, make_sample):
    sample = make_sample()
    sample.arrays = {"scalar": np.array(12.5), "empty": np.empty((0, 3), dtype=np.int16)}
    path = tmp_path / "sample.h5"
    write_hdf5(sample, path)
    h5_sample = read_hdf5(path)
    assert h5_sample.arrays["scalar"].shape == ()
    assert h5_sample.arrays["scalar"].item() == 12.5
    dump_sample_json(h5_sample, tmp_path / "sample.json")
    restored = load_sample_json(tmp_path / "sample.json")
    assert restored.arrays["empty"].shape == (0, 3)
    assert restored.arrays["empty"].dtype == np.int16


def test_ang_profile_reads_headerless_rows_with_explicit_indices(tmp_path):
    path = tmp_path / "map.ang"
    path.write_text("# vendor header\n0.1 0.2 0.3 11 22 99 0.8 2\n0.4 0.5 0.6 12 22 80 0.9 1\n", encoding="utf-8")
    rows = load_ebsd_text(path, "ang", {"euler_1": "0", "euler_2": "1", "euler_3": "2", "x": "3", "y": "4", "quality": "5", "phase_id": "7"})
    assert len(rows) == 2
    assert rows[0] == {"euler_1": 0.1, "euler_2": 0.2, "euler_3": 0.3, "x": 11.0, "y": 22.0, "quality": 99.0, "phase_id": 2.0}


def test_ctf_profile_finds_data_header_without_interpreting_preamble(tmp_path):
    path = tmp_path / "map.ctf"
    path.write_text("Channel Text File\nPrj\tsynthetic\nXCells\t2\nPhase\tX\tY\tEuler1\tEuler2\tEuler3\tMAD\n1\t0\t0\t10\t20\t30\t0.2\n2\t1\t0\t11\t21\t31\t0.3\n", encoding="utf-8")
    rows = load_ebsd_text(path, "ctf", {"phase_id": "Phase", "x": "X", "y": "Y", "euler_1": "Euler1", "euler_2": "Euler2", "euler_3": "Euler3", "quality": "MAD"})
    assert len(rows) == 2
    assert rows[1]["euler_3"] == 31
    assert rows[1]["phase_id"] == 2


def test_ebsd_unknown_profile_fails_closed(tmp_path):
    path = tmp_path / "map.txt"
    path.write_text("x,y\n0,0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="profile"):
        load_ebsd_text(path, "guess-vendor", {"x": "x"})


def test_external_adapter_rejects_conflicting_coordinates(multimodal_sample_config):
    config = load_pipeline_config(multimodal_sample_config)
    assets = list(config.assets)
    assets[0] = assets[0].model_copy(update={"adapter_config": {**assets[0].adapter_config, "coordinate_frame": "other-camera"}})
    with pytest.raises(ValueError, match="coordinate_frame"):
        assemble_sample(config.model_copy(update={"assets": tuple(assets)}))


def test_external_ang_adapter_is_normalized_with_explicit_orientation(multimodal_sample_config, tmp_path):
    from experiment_to_cpfe.config import ExternalAssetConfig

    path = tmp_path / "map.ang"
    path.write_text("# header\n10 20 30 0 0 99 1\n11 21 31 1 0 98 2\n", encoding="utf-8")
    columns = {"euler_1": "0", "euler_2": "1", "euler_3": "2", "x": "3", "y": "4", "quality": "5", "phase_id": "6"}
    units = {"euler_1": "degree", "euler_2": "degree", "euler_3": "degree", "x": "mm", "y": "mm", "quality": "1", "phase_id": "1"}
    external = ExternalAssetConfig(asset_id="orientation", path=path, parent_asset_id=None, source_kind="measured", layer="raw", modality="orientation_map", format="ang", units=units, coordinate_frame="sample", axis_order=("point", "component"), native_layout="explicit_ang", license="synthetic", lossy_transformations=(), adapter_config={"profile": "ang", "column_map": columns, "orientation": {"representation": "euler", "convention": "fixture-declared", "angle_units": "degree", "crystal_symmetry": "cubic"}})
    config = load_pipeline_config(multimodal_sample_config)
    sample = assemble_sample(config.model_copy(update={"assets": (external,)}))
    assert sample.arrays["orientation"].tolist() == [[10, 20, 30, 0, 0, 99, 1], [11, 21, 31, 1, 0, 98, 2]]
    assert sample.assets[-1].descriptive_metadata["orientation"]["angle_units"] == "degree"
    assert sample.assets[-1].descriptive_metadata["columns"] == list(columns)
    assert sample.assets[-1].source_kind.value == "measured"


def test_vendor_hdf5_explicit_dataset_components_and_units(multimodal_sample_config, tmp_path):
    from experiment_to_cpfe.config import ExternalAssetConfig

    path = tmp_path / "vendor.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("Vendor/X", data=[0.0, 1.0])
        handle.create_dataset("Vendor/Y", data=[0.0, 0.0])
        handle.create_dataset("Vendor/U", data=[[0.1, 0.2], [0.3, 0.4]])
    dataset_map = {"x": "Vendor/X", "y": "Vendor/Y", "u": {"path": "Vendor/U", "component": 0}, "v": {"path": "Vendor/U", "component": 1}}
    units = {"x": "mm", "y": "mm", "u": "mm", "v": "mm"}
    external = ExternalAssetConfig(asset_id="vendor-field", path=path, parent_asset_id=None, source_kind="measured", layer="raw", modality="point_field", format="hdf5", units=units, coordinate_frame="sample", axis_order=("point", "component"), native_layout="vendor-explicit", license="synthetic", lossy_transformations=(), adapter_config={"layout_name": "fixture-v1", "dataset_map": dataset_map, "coordinate_columns": ["x", "y"], "field_columns": ["u", "v"]})
    config = load_pipeline_config(multimodal_sample_config)
    sample = assemble_sample(config.model_copy(update={"assets": (external,)}))
    assert sample.arrays["vendor-field"].tolist() == [[0, 0, 0.1, 0.2], [1, 0, 0.3, 0.4]]
    assert sample.assets[-1].descriptive_metadata["dataset_map"] == dataset_map
    assert next(a for a in sample.assets if a.asset_id == "vendor-field").format == "hdf5"
    assert sample.assets[-1].native_layout.startswith("fixture-v1:")
    with pytest.raises(ValueError, match="canonical"):
        read_hdf5(path)


def test_vendor_hdf5_mapping_rejects_misaligned_record_counts(tmp_path):
    from experiment_to_cpfe.adapters import hdf5_layout

    path = tmp_path / "vendor.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("x", data=[0, 1])
        handle.create_dataset("u", data=[1, 2, 3])
    assert hasattr(hdf5_layout, "load_hdf5_fields"), "explicit HDF5 semantic loader is missing"
    with pytest.raises(ValueError, match="record"):
        hdf5_layout.load_hdf5_fields(path, {"layout_name": "fixture", "dataset_map": {"x": "x", "u": "u"}})


def test_normalized_json_preserves_array_byte_order(tmp_path, make_sample):
    sample = make_sample()
    sample.arrays = {"big_endian": np.array([1, 2], dtype=">i4")}
    path = tmp_path / "sample.json"
    dump_sample_json(sample, path)
    restored = load_sample_json(path)
    assert restored.arrays["big_endian"].dtype.str == ">i4"


def test_tabular_identifiers_preserve_leading_zeroes(multimodal_sample_config, tmp_path):
    from experiment_to_cpfe.adapters.tabular import load_tabular_source

    path = tmp_path / "records.csv"
    path.write_text("id,stress\n0001,12.5\n0002,15.0\n", encoding="utf-8")
    config = load_pipeline_config(multimodal_sample_config)
    source = config.sources[0].model_copy(update={"path": path, "column_map": {"increment_id": "id", "stress_33": "stress"}})
    assert load_tabular_source(source) == [{"increment_id": "0001", "stress_33": 12.5}, {"increment_id": "0002", "stress_33": 15.0}]


def test_json_voxel_integer_cast_requires_explicit_loss_record(tmp_path):
    path = tmp_path / "voxel.json"
    path.write_text("[[1.5,2.0]]", encoding="utf-8")
    config = {"format": "json", "dtype": "uint8", "origin": [0, 0], "spacing": [1, 1], "axis_order": ["y", "x"], "units": "mm", "coordinate_frame": "scanner"}
    with pytest.raises(ValueError, match="lossy"):
        load_voxel_array(path, config)
    metadata, array = load_voxel_array(path, {**config, "lossy_transformations": ["truncate fractional voxel intensities to uint8"]})
    assert array.tolist() == [[1, 2]]
    assert metadata["lossy_transformations"] == ("truncate fractional voxel intensities to uint8",)


def test_hdf5_roundtrip_preserves_asset_order(tmp_path, make_sample):
    sample = make_sample()
    sample.assets = tuple(sample.assets[0].model_copy(update={"asset_id": name}) for name in ("z-source", "a-source"))
    path = tmp_path / "sample.h5"
    write_hdf5(sample, path)
    assert [a.asset_id for a in read_hdf5(path).assets] == ["z-source", "a-source"]


def test_hdf5_array_path_names_fail_before_creating_partial_file(tmp_path, make_sample):
    sample = make_sample()
    sample.arrays = {"nested/name": np.array([1])}
    path = tmp_path / "sample.h5"
    with pytest.raises(ValueError, match="name"):
        write_hdf5(sample, path)
    assert not path.exists()


def test_vendor_hdf5_inspection_requires_explicit_modality(tmp_path):
    from experiment_to_cpfe.adapters.hdf5_layout import inspect_hdf5_layout
    from experiment_to_cpfe.assets.models import AssetKind

    path = tmp_path / "temperature.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("Temperature", data=[300, 301])
    with pytest.raises(ValueError, match="modality_hint"):
        inspect_hdf5_layout(path, "vendor-temperature")
    assert inspect_hdf5_layout(path, "vendor-temperature", modality_hint=AssetKind.TIME_SERIES).modality is AssetKind.TIME_SERIES


def test_parsed_external_arrays_have_logical_child_lineage(multimodal_sample_config, tmp_path):
    import hashlib

    sample = assemble_sample(load_pipeline_config(multimodal_sample_config))
    for array_key in ("ct-voxels", "dic-points"):
        parent = next(asset for asset in sample.assets if asset.asset_id == array_key)
        children = [asset for asset in sample.assets if asset.parent_asset_id == parent.asset_id and asset.format == "numpy-array"]
        assert len(children) == 1
        child = children[0]
        array = sample.arrays[array_key]
        descriptor = json.dumps({"dtype": array.dtype.str, "shape": list(array.shape)}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        expected = hashlib.sha256(b"numpy-array-v1\0" + descriptor + b"\0" + array.tobytes(order="C")).hexdigest()
        assert child.sha256 == expected
        assert child.conversion.hash_scope == "logical_payload"
        assert child.conversion.source_sha256 == parent.sha256
        assert child.conversion.target_payload_sha256 == expected
        assert child.conversion.target_file_hashes == {}
        assert child.conversion.original_format == parent.format
        assert child.conversion.target_format == "numpy-array"
        assert child.source_kind == parent.source_kind
        assert child.descriptive_metadata["array_key"] == array_key
    path = tmp_path / "sample.h5"
    write_hdf5(sample, path)
    assert [asset.model_dump(mode="json") for asset in read_hdf5(path).assets] == [asset.model_dump(mode="json") for asset in sample.assets]


def test_conversion_requires_digest_matching_its_scope():
    from experiment_to_cpfe.assets.models import ConversionRecord

    common = {"original_format": "npy", "target_format": "numpy-array", "source_sha256": "1" * 64}
    logical = ConversionRecord(**common, hash_scope="logical_payload", target_payload_sha256="2" * 64)
    assert logical.target_file_hashes == {}
    with pytest.raises(ValueError):
        ConversionRecord(**common, hash_scope="logical_payload", target_file_hashes={"invented.npy": "2" * 64})
    with pytest.raises(ValueError):
        ConversionRecord(**common, target_file_hashes={})


def test_canonical_writer_rejects_changed_logical_array(multimodal_sample_config, tmp_path):
    sample = assemble_sample(load_pipeline_config(multimodal_sample_config))
    sample.arrays["ct-voxels"][0, 0, 0] = 42
    path = tmp_path / "bad.h5"
    with pytest.raises(ValueError, match="payload hash"):
        write_hdf5(sample, path)
    assert not path.exists()


def test_canonical_reader_rejects_changed_logical_array(multimodal_sample_config, tmp_path):
    sample = assemble_sample(load_pipeline_config(multimodal_sample_config))
    path = tmp_path / "bad.h5"
    write_hdf5(sample, path)
    with h5py.File(path, "r+") as handle:
        handle["derived/arrays/ct-voxels"][0, 0, 0] = 42
    with pytest.raises(ValueError, match="payload hash"):
        read_hdf5(path)


def test_vendor_column_stacking_refuses_precision_loss_for_large_identifiers(tmp_path):
    from experiment_to_cpfe.adapters.hdf5_layout import load_hdf5_fields

    path = tmp_path / "ids.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("point_id", data=np.array([9007199254740993], dtype=np.uint64))
        handle.create_dataset("u", data=np.array([0.25]))
    with pytest.raises(ValueError, match="precision"):
        load_hdf5_fields(path, {"layout_name": "fixture", "dataset_map": {"point_id": "point_id", "u": "u"}})


@pytest.mark.parametrize("shape", [(2,), (), (0, 3)])
def test_unicode_hdf5_arrays_roundtrip_dtype_shape_and_logical_hash(tmp_path, make_sample, shape):
    from experiment_to_cpfe.assets.registry import array_payload_sha256

    sample = make_sample()
    array = np.array(["grain-A", "晶粒-B"], dtype=">U12") if shape == (2,) else (
        np.array("晶粒", dtype=">U12") if shape == () else np.empty(shape, dtype=">U12"))
    sample.arrays = {"graph_node_ids": array}
    digest = array_payload_sha256(array)
    path = tmp_path / "strings.h5"
    write_hdf5(sample, path)
    restored = read_hdf5(path).arrays["graph_node_ids"]
    assert restored.dtype.str == ">U12"
    assert restored.shape == shape
    assert restored.tolist() == array.tolist()
    assert array_payload_sha256(restored) == digest


@pytest.mark.parametrize("array", [np.array([object()], dtype=object), np.array([(1,)], dtype=[("id", "i4")]), np.array(["2026-09-06"], dtype="datetime64[D]")])
def test_unsupported_hdf5_dtype_fails_before_creating_output(tmp_path, make_sample, array):
    sample = make_sample()
    sample.arrays = {"unsupported": array}
    path = tmp_path / "unsupported.h5"
    with pytest.raises(ValueError, match="dtype"):
        write_hdf5(sample, path)
    assert not path.exists()


def _vti_text(association="PointData", extent="2 3 3 4 4 5", format_name="ascii", components="1", pieces=1):
    piece = f'<Piece Extent="{extent}"><{association}><DataArray type="Int16" Name="phase" NumberOfComponents="{components}" format="{format_name}">1 2 3 4 5 6 7 8</DataArray></{association}></Piece>'
    return f'<VTKFile type="ImageData" version="0.1" byte_order="LittleEndian"><ImageData WholeExtent="{extent}" Origin="10 20 30" Spacing="0.5 1 2">{piece * pieces}</ImageData></VTKFile>'


def _vti_config(association="PointData"):
    return {"format": "vti", "array_name": "phase", "association": association,
            "units": "mm", "value_units": "1", "coordinate_frame": "scanner", "axis_order": ["z", "y", "x"]}


@pytest.mark.parametrize("association,extent,origin", [("PointData", "2 3 3 4 4 5", (38.0, 23.0, 11.0)), ("CellData", "2 4 3 5 4 6", (39.0, 23.5, 11.25))])
def test_ascii_vti_reads_selected_scalar_grid_with_explicit_geometry(tmp_path, association, extent, origin):
    path = tmp_path / "grid.vti"
    path.write_text(_vti_text(association, extent), encoding="utf-8")
    raw = path.read_bytes()
    metadata, array = load_voxel_array(path, _vti_config(association))
    assert array.shape == (2, 2, 2)
    assert array.dtype == np.int16
    assert array[0, 0].tolist() == [1, 2]
    assert array[1, 1].tolist() == [7, 8]
    assert metadata["origin"] == origin
    assert metadata["spacing"] == (2.0, 1.0, 0.5)
    assert metadata["vtk_origin_xyz"] == (10.0, 20.0, 30.0)
    assert metadata["vtk_extent"] == tuple(map(int, extent.split()))
    assert metadata["association"] == association
    assert metadata["value_units"] == "1"
    assert path.read_bytes() == raw


@pytest.mark.parametrize("changes", [{"format_name": "binary"}, {"format_name": "appended"}, {"components": "3"}, {"pieces": 2}])
def test_ascii_vti_rejects_unsupported_variants(tmp_path, changes):
    path = tmp_path / "grid.vti"
    path.write_text(_vti_text(**changes), encoding="utf-8")
    with pytest.raises(ValueError, match="VTI"):
        load_voxel_array(path, _vti_config())


@pytest.mark.parametrize("missing", ["array_name", "association", "value_units", "coordinate_frame"])
def test_ascii_vti_requires_explicit_field_contract(tmp_path, missing):
    path = tmp_path / "grid.vti"
    path.write_text(_vti_text(), encoding="utf-8")
    config = _vti_config()
    del config[missing]
    with pytest.raises(ValueError, match=missing):
        load_voxel_array(path, config)


def test_vti_assemble_hdf5_retains_grid_and_child_provenance(tmp_path, multimodal_sample_config):
    from experiment_to_cpfe.config import ExternalAssetConfig

    path = tmp_path / "grid.vti"
    path.write_text(_vti_text(), encoding="utf-8")
    external = ExternalAssetConfig(asset_id="public-grid", path=path, parent_asset_id=None, source_kind="simulated", layer="solver_output", modality="voxel_grid", format="vti", units={"spacing": "mm", "phase": "1"}, coordinate_frame="scanner", axis_order=("z", "y", "x"), native_layout="vtk_image_data", license="synthetic", lossy_transformations=(), adapter_config=_vti_config())
    config = load_pipeline_config(multimodal_sample_config).model_copy(update={"assets": (external,)})
    sample = assemble_sample(config)
    output = tmp_path / "sample.h5"
    write_hdf5(sample, output)
    restored = read_hdf5(output)
    child = next(a for a in restored.assets if a.parent_asset_id == "public-grid")
    assert child.descriptive_metadata["origin"] == [38.0, 23.0, 11.0]
    assert child.descriptive_metadata["vtk_extent"] == [2, 3, 3, 4, 4, 5]
    assert child.source_kind.value == "simulated"
    assert child.conversion.original_format == "vti"
    assert child.conversion.target_format == "numpy-array"
