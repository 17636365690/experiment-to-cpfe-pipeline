"""Regular voxel-array adapter with explicit spatial metadata."""

from pathlib import Path
import json

import h5py
import numpy as np


def _required(config: dict[str, object], name: str) -> object:
    value = config.get(name)
    if value is None or value == [] or value == "":
        raise ValueError(f"{name} is required")
    return value


def load_voxel_array(
    path: Path,
    config: dict[str, object],
) -> tuple[dict[str, object], np.ndarray]:
    """Load NPY or an explicitly addressed HDF5 voxel dataset."""

    path = Path(path)
    format_name = str(_required(config, "format"))
    if format_name == "npy":
        array = np.load(path, allow_pickle=False)
        native_layout = "numpy_c_order" if array.flags.c_contiguous else "numpy_array"
    elif format_name in {"h5", "hdf5"}:
        dataset_path = str(_required(config, "dataset_path"))
        with h5py.File(path, "r") as handle:
            array = np.asarray(handle[dataset_path])
        native_layout = f"hdf5_dataset:{dataset_path}"
    elif format_name == "json":
        dtype = str(_required(config, "dtype"))
        array = np.asarray(
            json.loads(path.read_text(encoding="utf-8")),
            dtype=dtype,
        )
        native_layout = "json_nested_array"
    else:
        raise ValueError(f"unsupported voxel format: {format_name}")

    origin = tuple(float(value) for value in _required(config, "origin"))
    spacing = tuple(float(value) for value in _required(config, "spacing"))
    axis_order = tuple(str(value) for value in _required(config, "axis_order"))
    if not (len(origin) == len(spacing) == len(axis_order) == array.ndim):
        raise ValueError("origin, spacing, axis_order, and array rank must match")
    if any(value <= 0 for value in spacing):
        raise ValueError("voxel spacing must be positive")

    metadata = {
        "origin": origin,
        "spacing": spacing,
        "axis_order": axis_order,
        "units": str(_required(config, "units")),
        "coordinate_frame": str(_required(config, "coordinate_frame")),
        "dtype": array.dtype.name,
        "shape": array.shape,
        "native_layout": native_layout,
        "lossy_transformations": tuple(config.get("lossy_transformations", ())),
    }
    return metadata, array
