"""Non-destructive inspection and registration of data assets."""

from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np

from experiment_to_cpfe.assets.models import (
    AssetKind,
    AssetRef,
    DataLayer,
    SourceKind,
)


@dataclass(frozen=True)
class AssetInspection:
    path: Path
    modality: AssetKind
    format: str
    size_bytes: int
    dtype: str | None
    shape: tuple[int, ...]
    axis_order: tuple[str, ...]
    units: dict[str, str]
    coordinate_frame: str | None
    native_layout: str
    lossy_transformations: tuple[str, ...]
    warnings: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_asset(
    path: Path,
    modality_hint: AssetKind | None = None,
) -> AssetInspection:
    """Inspect cheap file metadata without interpreting vendor semantics."""

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower().lstrip(".") or "unknown"
    modality = modality_hint
    if modality is None:
        if suffix in {"csv", "txt", "json"}:
            modality = AssetKind.TABLE
        elif suffix == "npy":
            modality = AssetKind.VOXEL_GRID
        elif suffix == "inp":
            modality = AssetKind.MESH
        else:
            raise ValueError("modality_hint is required for ambiguous formats")

    dtype: str | None = None
    shape: tuple[int, ...] = ()
    native_layout = f"uninspected_{suffix}"
    warnings: tuple[str, ...] = ()
    if suffix == "npy":
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        dtype = array.dtype.name
        shape = array.shape
        native_layout = "numpy_c_order" if array.flags.c_contiguous else "numpy_array"
    elif suffix in {"h5", "hdf5", "dream3d"}:
        native_layout = "uninspected_hdf5"
        warnings = ("HDF5 semantic layout requires an explicit profile",)

    return AssetInspection(
        path=path,
        modality=modality,
        format=suffix,
        size_bytes=path.stat().st_size,
        dtype=dtype,
        shape=shape,
        axis_order=(),
        units={},
        coordinate_frame=None,
        native_layout=native_layout,
        lossy_transformations=(),
        warnings=warnings,
    )


def register_asset(
    path: Path,
    inspection: AssetInspection,
    source_kind: SourceKind,
    layer: DataLayer,
    parent_asset_id: str | None,
    license: str | None,
) -> AssetRef:
    """Register metadata and hashes without modifying the source file."""

    path = Path(path)
    digest = _sha256(path)
    return AssetRef(
        asset_id=f"asset-{layer.value}-{digest[:16]}",
        parent_asset_id=parent_asset_id,
        modality=inspection.modality,
        format=inspection.format,
        uri=str(path),
        source_kind=source_kind,
        layer=layer,
        units=inspection.units,
        coordinate_frame=inspection.coordinate_frame,
        axis_order=inspection.axis_order,
        dtype=inspection.dtype,
        shape=inspection.shape,
        native_layout=inspection.native_layout,
        sha256=digest,
        license=license,
        lossy_transformations=inspection.lossy_transformations,
    )
