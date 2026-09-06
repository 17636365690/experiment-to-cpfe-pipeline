"""Regular voxel-array adapter with explicit spatial metadata."""

from pathlib import Path
import json

import h5py
import numpy as np

from experiment_to_cpfe.adapters.vti import load_vti_scalar


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
    source_metadata: dict[str, object] = {}
    if format_name == "vti":
        source_metadata, array = load_vti_scalar(path, config)
        config = {**config, "origin": source_metadata["origin"], "spacing": source_metadata["spacing"]}
        native_layout = source_metadata["native_layout"]
    elif format_name == "npy":
        array = np.load(path, allow_pickle=False)
        native_layout = "numpy_c_order" if array.flags.c_contiguous else "numpy_array"
    elif format_name in {"h5", "hdf5"}:
        dataset_path = str(_required(config, "dataset_path"))
        with h5py.File(path, "r") as handle:
            array = np.asarray(handle[dataset_path])
        native_layout = f"hdf5_dataset:{dataset_path}"
    elif format_name == "json":
        dtype = str(_required(config, "dtype"))
        original = np.asarray(json.loads(path.read_text(encoding="utf-8")))
        array = np.asarray(original, dtype=dtype)
        if not np.array_equal(original, array) and not config.get("lossy_transformations"):
            raise ValueError("lossy JSON dtype conversion requires an explicit lossy_transformations record")
        native_layout = "json_nested_array"
    else:
        raise ValueError(f"unsupported voxel format: {format_name}")

    origin = tuple(float(value) for value in _required(config, "origin"))
    spacing = tuple(float(value) for value in _required(config, "spacing"))
    axis_order = tuple(str(value) for value in _required(config, "axis_order"))
    if not (len(origin) == len(spacing) == len(axis_order) == array.ndim):
        raise ValueError("origin, spacing, axis_order, and array rank must match")
    if array.ndim == 0 or not array.size:
        raise ValueError("voxel grid must have nonempty spatial dimensions")
    if len(set(axis_order)) != len(axis_order) or any(not axis.strip() for axis in axis_order):
        raise ValueError("voxel axis_order must contain unique, nonempty axes")
    if not np.isfinite(origin).all() or not np.isfinite(spacing).all():
        raise ValueError("voxel origin and spacing must be finite")
    if array.dtype.kind not in "biuf" or not np.isfinite(array).all():
        raise ValueError("voxel values must be real numeric and finite")
    if any(value <= 0 for value in spacing):
        raise ValueError("voxel spacing must be positive")

    metadata = {
        **source_metadata,
        "origin": origin,
        "spacing": spacing,
        "axis_order": axis_order,
        "units": str(_required(config, "units")),
        "coordinate_frame": str(_required(config, "coordinate_frame")),
        "dtype": array.dtype.name,
        "shape": array.shape,
        "native_layout": native_layout,
        "lossy_transformations": tuple(source_metadata.get("lossy_transformations", config.get("lossy_transformations", ()))),
    }
    return metadata, array
