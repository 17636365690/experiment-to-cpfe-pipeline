"""Explicit semantic inspection for vendor and scientific HDF5 files."""

from pathlib import Path

import h5py

from experiment_to_cpfe.assets.models import AssetKind
from experiment_to_cpfe.assets.registry import AssetInspection


def inspect_hdf5_layout(
    path: Path,
    layout_name: str | None,
) -> AssetInspection:
    """Inspect HDF5 only when the caller names the expected layout profile."""

    if not layout_name:
        raise ValueError("layout_name is required for HDF5 inspection")
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
        modality=AssetKind.ORIENTATION_MAP,
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
