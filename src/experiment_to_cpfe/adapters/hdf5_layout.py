"""Explicit semantic inspection for vendor and scientific HDF5 files."""

from pathlib import Path

import h5py
import numpy as np

from experiment_to_cpfe.assets.models import AssetKind
from experiment_to_cpfe.assets.registry import AssetInspection
from experiment_to_cpfe.adapters.native_numeric import reject_matlab_objects, local_hdf5_dataset


def load_hdf5_fields(path: Path, config: dict[str, object]) -> tuple[dict[str, object], np.ndarray]:
    """Read explicitly addressed one-dimensional record columns, without unit conversion.

    A mapping value is a dataset path or ``{"path": ..., "component": i}``
    selecting a column of an N-by-C dataset. No reshape, flatten, or transpose
    is inferred from a vendor group name.
    """
    layout_name = config.get("layout_name")
    mapping = config.get("dataset_map")
    if not isinstance(layout_name, str) or not layout_name.strip():
        raise ValueError("layout_name is required for HDF5 semantic mapping")
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("an explicit dataset_map is required for HDF5 semantic mapping")
    columns = []
    with h5py.File(Path(path), "r") as handle:
        reject_matlab_objects(handle)
        for field, location in mapping.items():
            component = None
            if isinstance(location, str):
                dataset_path = location
            elif isinstance(location, dict) and set(location) <= {"path", "component"}:
                dataset_path = location.get("path")
                component = location.get("component")
            else:
                raise ValueError(f"invalid HDF5 dataset_map entry for {field}")
            if not isinstance(dataset_path, str) or not dataset_path.strip():
                raise ValueError(f"dataset path is required for {field}")
            if dataset_path not in handle or not isinstance(handle[dataset_path], h5py.Dataset):
                raise ValueError(f"mapped HDF5 dataset is missing: {dataset_path}")
            values = np.asarray(local_hdf5_dataset(handle, dataset_path))
            if component is not None:
                if not isinstance(component, int) or isinstance(component, bool) or values.ndim != 2 or not 0 <= component < values.shape[1]:
                    raise ValueError(f"invalid HDF5 component selection for {field}")
                values = values[:, component]
            if values.ndim != 1 or not values.size:
                raise ValueError(f"mapped HDF5 field {field} must be nonempty 1D records")
            if values.dtype.kind not in "biuf" or not np.isfinite(values).all():
                raise ValueError(f"mapped HDF5 field {field} must be finite real numeric records")
            if columns and len(values) != len(columns[0]):
                raise ValueError("mapped HDF5 record counts differ")
            columns.append(values)
    array = np.column_stack(columns)
    if any(values.tolist() != array[:, index].tolist() for index, values in enumerate(columns)):
        raise ValueError("combining mapped HDF5 columns would lose numeric precision; normalize separate typed arrays")
    metadata = {
        "columns": list(mapping), "dataset_map": mapping, "layout_name": layout_name,
        "native_layout": f"{layout_name}:explicit_dataset_mapping", "dtype": array.dtype.name,
        "shape": array.shape, "lossy_transformations": tuple(config.get("lossy_transformations", ())),
    }
    return metadata, array


def inspect_hdf5_layout(
    path: Path,
    layout_name: str | None,
    modality_hint: AssetKind | None = None,
) -> AssetInspection:
    """Inspect HDF5 only when the caller names the expected layout profile."""

    if not layout_name:
        raise ValueError("layout_name is required for HDF5 inspection")
    if modality_hint is None:
        raise ValueError("modality_hint is required for HDF5 inspection")
    path = Path(path)
    datasets: list[tuple[str, str, tuple[int, ...]]] = []
    with h5py.File(path, "r") as handle:
        def collect(name: str, item: object) -> None:
            if isinstance(item, h5py.Dataset):
                datasets.append((name, item.dtype.name, item.shape))

        handle.visititems(collect)

    paths = [item[0] for item in datasets]
    first = datasets[0] if datasets else None
    return AssetInspection(
        path=path,
        modality=modality_hint,
        format=path.suffix.lower().lstrip("."),
        size_bytes=path.stat().st_size,
        dtype=first[1] if first else None,
        shape=first[2] if first else (),
        axis_order=(),
        units={},
        coordinate_frame=None,
        native_layout=f"{layout_name}:{'|'.join(paths)}",
        lossy_transformations=(),
        warnings=() if datasets else ("layout contains no datasets",),
    )
