import h5py
import numpy as np
import pytest


def test_ebsd_text_requires_explicit_column_mapping(tmp_path):
    from experiment_to_cpfe.adapters.ebsd import load_ebsd_text

    path = tmp_path / "map.ang"
    path.write_text("x,y,p,e1,e2,e3,iq\n1,2,1,0,0,0,100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="column mapping"):
        load_ebsd_text(path, profile="generic", column_map={})


def test_ebsd_text_preserves_coordinates_phase_orientation_and_quality(tmp_path):
    from experiment_to_cpfe.adapters.ebsd import load_ebsd_text

    path = tmp_path / "map.ang"
    path.write_text(
        "x,y,p,e1,e2,e3,iq\n0,0,1,0.1,0.2,0.3,95\n1,0,2,0.4,0.5,0.6,88\n",
        encoding="utf-8",
    )
    rows = load_ebsd_text(
        path,
        profile="generic",
        column_map={
            "x": "x",
            "y": "y",
            "phase_id": "p",
            "euler_1": "e1",
            "euler_2": "e2",
            "euler_3": "e3",
            "image_quality": "iq",
        },
    )

    assert rows[1] == {
        "x": 1,
        "y": 0,
        "phase_id": 2,
        "euler_1": 0.4,
        "euler_2": 0.5,
        "euler_3": 0.6,
        "image_quality": 88,
    }


def test_vendor_hdf5_requires_explicit_layout(tmp_path):
    from experiment_to_cpfe.adapters.hdf5_layout import inspect_hdf5_layout

    path = tmp_path / "vendor.h5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("Scan 1/EBSD/Data/Euler", data=np.zeros((2, 3)))

    with pytest.raises(ValueError, match="layout_name"):
        inspect_hdf5_layout(path, layout_name=None)

    inspection = inspect_hdf5_layout(path, layout_name="vendor-demo")
    assert inspection.native_layout.startswith("vendor-demo:")
    assert "Scan 1/EBSD/Data/Euler" in inspection.native_layout


def test_point_field_preserves_coordinates_units_and_components(tmp_path):
    from experiment_to_cpfe.adapters.fields import load_point_field

    path = tmp_path / "dic.csv"
    path.write_text("x,y,u,v\n0,0,0.1,0.2\n1,0,0.3,0.4\n", encoding="utf-8")
    metadata, values = load_point_field(
        path,
        {
            "format": "csv",
            "delimiter": ",",
            "coordinate_columns": ["x", "y"],
            "field_columns": ["u", "v"],
            "units": {"x": "mm", "y": "mm", "u": "mm", "v": "mm"},
            "coordinate_frame": "dic-camera",
            "axis_order": ["point", "component"],
        },
    )

    assert metadata["coordinate_frame"] == "dic-camera"
    assert metadata["units"]["u"] == "mm"
    assert metadata["columns"] == ("x", "y", "u", "v")
    assert values.shape == (2, 4)
    assert values[1].tolist() == [1.0, 0.0, 0.3, 0.4]


def test_point_field_rejects_missing_units(tmp_path):
    from experiment_to_cpfe.adapters.fields import load_point_field

    path = tmp_path / "dic.csv"
    path.write_text("x,y,u\n0,0,0.1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="units"):
        load_point_field(
            path,
            {
                "format": "csv",
                "delimiter": ",",
                "coordinate_columns": ["x", "y"],
                "field_columns": ["u"],
                "coordinate_frame": "dic-camera",
                "axis_order": ["point", "component"],
            },
        )


def test_voxel_array_preserves_origin_spacing_axis_dtype_and_shape(tmp_path):
    from experiment_to_cpfe.adapters.voxel import load_voxel_array

    path = tmp_path / "ct.npy"
    source = np.arange(8, dtype=np.uint16).reshape(2, 2, 2)
    np.save(path, source)
    metadata, restored = load_voxel_array(
        path,
        {
            "format": "npy",
            "origin": [10.0, 20.0, 30.0],
            "spacing": [0.5, 0.5, 1.0],
            "axis_order": ["z", "y", "x"],
            "units": "um",
            "coordinate_frame": "ct-scanner",
        },
    )

    assert metadata == {
        "origin": (10.0, 20.0, 30.0),
        "spacing": (0.5, 0.5, 1.0),
        "axis_order": ("z", "y", "x"),
        "units": "um",
        "coordinate_frame": "ct-scanner",
        "dtype": "uint16",
        "shape": (2, 2, 2),
        "native_layout": "numpy_c_order",
        "lossy_transformations": (),
    }
    assert restored.dtype == np.uint16
    assert restored.shape == (2, 2, 2)


def test_voxel_json_supports_text_only_synthetic_fixture(tmp_path):
    import json

    from experiment_to_cpfe.adapters.voxel import load_voxel_array

    path = tmp_path / "voxel.json"
    path.write_text(json.dumps([[[0, 1], [2, 3]], [[4, 5], [6, 7]]]), encoding="utf-8")
    metadata, restored = load_voxel_array(
        path,
        {
            "format": "json",
            "dtype": "uint8",
            "origin": [0, 0, 0],
            "spacing": [1, 1, 1],
            "axis_order": ["z", "y", "x"],
            "units": "m",
            "coordinate_frame": "sample",
        },
    )

    assert metadata["native_layout"] == "json_nested_array"
    assert restored.dtype == np.uint8
    assert restored.shape == (2, 2, 2)
