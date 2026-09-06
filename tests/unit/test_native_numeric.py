"""Native numerical selection must preserve dimensions, masks and source identity."""

import io
import numpy as np
import h5py
import pytest
from scipy.io import savemat


def read(filename, **selector):
    from experiment_to_cpfe.adapters.native_numeric import read_numeric
    return read_numeric(filename, selector)


def test_mat_struct_cells_and_fortran_reshape_remain_explicit(tmp_path):
    cells = np.empty((1, 2), dtype=object)
    cells[0, 0] = np.array([[10, 20, 30], [40, 50, 60]], dtype=np.int64)
    cells[0, 1] = np.array([[70, 80, 90]], dtype=np.int64)
    path = tmp_path / "states.mat"
    savemat(path, {"states": cells, "Stress": {"S11": np.array([[1., np.nan]])}})
    a, meta = read(path, format="mat5", path="states", steps=[{"index": [0, 0]}])
    b, _ = read(path, format="mat5", path="states", steps=[{"index": [0, 1]}])
    assert a.tolist() == [[10, 20, 30], [40, 50, 60]]
    assert b.shape == (1, 3)  # no equal-length padding or cross-state ID assumption
    s, _ = read(path, format="mat5", path="Stress", steps=[{"index": [0, 0]}, {"field": "S11"}])
    assert s.shape == (1, 2) and np.isnan(s[0, 1])
    r, meta = read(path, format="mat5", path="states", steps=[{"index": [0, 0]}],
                   reshape=[3, 2], reshape_order="F")
    assert r.tolist() == [[10, 50], [40, 30], [20, 60]]
    assert meta["selector"]["reshape_order"] == "F"


def test_unselected_mat_cell_cannot_be_normalized_as_numeric(tmp_path):
    path = tmp_path / "cell.mat"
    cells = np.empty((1, 1), object)
    cells[0, 0] = np.ones((2, 3))
    savemat(path, {"cell": cells})
    with pytest.raises(ValueError, match="numeric|object|cell"):
        read(path, format="mat5", path="cell")


def test_hdf5_flat_fields_select_small_slice_before_allocation(tmp_path):
    path = tmp_path / "flat.h5"
    with h5py.File(path, "w") as h:
        ds = h.create_dataset("train_images", shape=(10000, 2, 3, 4), dtype="f4", chunks=(1, 2, 3, 4))
        ds[7] = np.arange(24).reshape(2, 3, 4)
        h["train_masks"] = np.ones((2, 3, 4), dtype=np.uint8)
    a, meta = read(path, format="hdf5", path="train_images", slices=[[7, 8], None, None, None], max_bytes=100)
    assert a.shape == (1, 2, 3, 4) and a[0, 1, 2, 3] == 23
    assert meta["source_shape"] == [10000, 2, 3, 4]
    with pytest.raises(ValueError, match="byte|limit"):
        read(path, format="hdf5", path="train_images", max_bytes=100)


@pytest.mark.parametrize("format_name", ["hdf5", "mat73"])
def test_matlab_class_storage_is_never_numeric_field_data(tmp_path, format_name):
    path = tmp_path / "object.mat"
    with h5py.File(path, "w") as h:
        h["obj"] = np.arange(6, dtype="u4").reshape(1, 6)
        h["obj"].attrs["MATLAB_class"] = np.bytes_("DICInstance")
    with pytest.raises(ValueError, match="MATLAB|class|native"):
        read(path, format=format_name, path="obj")


def test_legacy_hdf5_mapping_also_rejects_class_payload(tmp_path):
    from experiment_to_cpfe.adapters.hdf5_layout import load_hdf5_fields
    path = tmp_path / "object.h5"
    with h5py.File(path, "w") as h:
        h["obj"] = np.arange(6, dtype="u4")
        h["obj"].attrs["MATLAB_class"] = np.bytes_("DICInstance")
    with pytest.raises(ValueError, match="MATLAB|class|native"):
        load_hdf5_fields(path, {"layout_name": "object", "dataset_map": {"v": "obj"}})


def test_fortran_header_inspection_never_needs_full_payload(tmp_path):
    from experiment_to_cpfe.adapters.native_numeric import inspect_npy_header
    path = tmp_path / "volume.npy"
    stream = io.BytesIO()
    np.lib.format.write_array_header_1_0(stream, {"shape": (152, 17, 12), "fortran_order": True, "descr": "|u1"})
    path.write_bytes(stream.getvalue())
    meta = inspect_npy_header(path)
    assert meta["fortran_order"] is True and meta["shape"] == [152, 17, 12]
    assert meta["payload_complete"] is False
    with pytest.raises(ValueError, match="incomplete|payload"):
        read(path, format="npy")


def test_npy_component_axis_and_fortran_order_are_not_transposed(tmp_path):
    path = tmp_path / "channels.npy"
    np.save(path, np.asfortranarray(np.arange(48).reshape(2, 3, 2, 4)))
    a, meta = read(path, format="npy")
    assert a.shape == (2, 3, 2, 4) and a[1, 2, 1, 3] == 47
    assert meta["fortran_order"] is True


@pytest.mark.parametrize("selector", [
    {"slices": [[0, 99], None]}, {"slices": [[0, 2, 0], None]},
    {"transpose": [0, 0]}, {"reshape": [3, 2]}, {"unknown_option": 1},
])
def test_invalid_selection_never_silently_clips_or_guesses(tmp_path, selector):
    path = tmp_path / "a.npy"
    np.save(path, np.arange(6).reshape(2, 3))
    with pytest.raises(ValueError):
        read(path, format="npy", **selector)


@pytest.mark.parametrize("storage", ["link", "virtual", "external"])
def test_hdf5_unregistered_file_dependencies_are_rejected(tmp_path, storage):
    parent = tmp_path / "parent.h5"
    remote = tmp_path / "other.h5"
    with h5py.File(remote, "w") as h:
        h["v"] = np.array([1., 2.])
    with h5py.File(parent, "w") as h:
        if storage == "link":
            h["v"] = h5py.ExternalLink(str(remote), "v")
        elif storage == "virtual":
            layout = h5py.VirtualLayout(shape=(2,), dtype="f8")
            layout[:] = h5py.VirtualSource(str(remote), "v", shape=(2,))
            h.create_virtual_dataset("v", layout)
        else:
            h.create_dataset("v", shape=(2,), dtype="f8", external=[(str(tmp_path / "external.bin"), 0, 16)])
    with pytest.raises(ValueError, match="external|virtual|dependency"):
        read(parent, format="hdf5", path="v")


def test_legacy_voxel_adapter_also_rejects_matlab_objects(tmp_path):
    from experiment_to_cpfe.adapters.voxel import load_voxel_array
    path = tmp_path / "class.h5"
    with h5py.File(path, "w") as h:
        h["obj"] = np.ones((2, 2))
        h["obj"].attrs["MATLAB_class"] = np.bytes_("DICInstance")
    with pytest.raises(ValueError, match="MATLAB|class"):
        load_voxel_array(path, dict(format="hdf5", dataset_path="obj", origin=[0, 0], spacing=[1, 1],
                                   axis_order=["x", "y"], units="mm", coordinate_frame="sample"))
