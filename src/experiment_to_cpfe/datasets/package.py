"""Derived NPZ/PyG exports and dataset summaries."""

import json
from pathlib import Path

import numpy as np

from experiment_to_cpfe.schema.models import SamplePackage


def write_npz(
    sample: SamplePackage,
    path: Path,
    source_hdf5_sha256: str,
) -> None:
    if not source_hdf5_sha256:
        raise ValueError("a non-empty HDF5 source hash is required")
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, np.ndarray] = dict(sample.arrays)
    payload["__source_hdf5_sha256__"] = np.asarray(source_hdf5_sha256)
    payload["__sample_id__"] = np.asarray(sample.metadata.sample_id)
    payload["__asset_manifest_json__"] = np.asarray(
        json.dumps(
            [asset.model_dump(mode="json") for asset in sample.assets],
            sort_keys=True,
        )
    )
    np.savez_compressed(path, **payload)


def write_pyg(
    sample: SamplePackage,
    path: Path,
    source_hdf5_sha256: str,
) -> None:
    if not source_hdf5_sha256:
        raise ValueError("a non-empty HDF5 source hash is required")
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyG export requires the optional 'ml' dependencies") from exc
    if "graph_node_features" not in sample.arrays or "graph_edge_index" not in sample.arrays:
        raise ValueError("grain graph arrays are missing")
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    bundle = {
        "x": torch.as_tensor(sample.arrays["graph_node_features"]),
        "edge_index": torch.as_tensor(sample.arrays["graph_edge_index"], dtype=torch.long),
        "source_hdf5_sha256": source_hdf5_sha256,
        "sample_id": sample.metadata.sample_id,
    }
    torch.save(bundle, path)


def dataset_summary(sample: SamplePackage) -> dict[str, object]:
    return {
        "sample_id": sample.metadata.sample_id,
        "table_counts": {name: len(rows) for name, rows in sample.tables.items()},
        "array_shapes": {name: list(array.shape) for name, array in sample.arrays.items()},
        "asset_modalities": sorted({asset.modality.value for asset in sample.assets}),
    }
