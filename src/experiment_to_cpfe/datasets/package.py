"""Derived NPZ/PyG exports and dataset summaries."""

import json
import io
import re
from collections import Counter
from pathlib import Path

import h5py
import numpy as np

from experiment_to_cpfe.schema.models import SamplePackage
from experiment_to_cpfe.schema.validation import _unit_is_declared
from experiment_to_cpfe.datasets.hdf5 import read_hdf5
from experiment_to_cpfe.provenance.hashing import sha256_file


def _load_source(source_hdf5: Path, expected_hash: str) -> tuple[SamplePackage, dict]:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_hash or ""):
        raise ValueError("a valid HDF5 source hash is required")
    source_hdf5 = Path(source_hdf5)
    if sha256_file(source_hdf5) != expected_hash.lower():
        raise ValueError("HDF5 source hash does not match the canonical file")
    sample = read_hdf5(source_hdf5)
    with h5py.File(source_hdf5, "r") as handle:
        provenance = json.loads(handle["provenance/source_manifest_json"].asstr()[()])
    if sha256_file(source_hdf5) != expected_hash.lower():
        raise ValueError("HDF5 source hash changed during reading")
    return sample, provenance


def _payload(sample: SamplePackage, provenance: dict, digest: str) -> dict[str, np.ndarray]:
    array_metadata = {}
    result = {}
    for name, array in sample.arrays.items():
        if name.startswith("__") or name in {"file", "allow_pickle"} or any(c in name for c in ("/", "\\", "\0")):
            raise ValueError(f"reserved or unsafe array name: {name}")
        if array.dtype.hasobject:
            raise ValueError(f"object array would require pickle: {name}")
        if array.dtype.fields is not None:
            raise ValueError(f"structured array must be normalized to tables or plain arrays: {name}")
        array_metadata[name] = {"dtype": array.dtype.str, "shape": list(array.shape),
                                "metadata": dict(array.dtype.metadata or {})}
        # NPY omits dtype metadata. Retain it explicitly, while storing the exact
        # simple dtype and bytes in the numeric/string array without warnings.
        result[name] = array.view(np.dtype(array.dtype.str)) if array.dtype.metadata else array
    result["__format_version__"] = np.asarray("experiment-to-cpfe-npz-1")
    result["__source_hdf5_sha256__"] = np.asarray(digest.lower())
    result["__sample_id__"] = np.asarray(sample.metadata.sample_id)
    result["__derivation_json__"] = np.asarray(json.dumps(_derivation(digest, "npz"), sort_keys=True))
    for key, value in {
        "sample_metadata": sample.metadata.model_dump(mode="json"),
        "tables": sample.tables, "solver_inputs": sample.solver_inputs,
        "asset_manifest": [asset.model_dump(mode="json") for asset in sample.assets],
        "source_manifest": provenance,
        "array_metadata": array_metadata,
    }.items():
        result[f"__{key}_json__"] = np.asarray(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False))
    return result


def _derivation(digest: str, target: str) -> dict:
    return {
        "parent_asset_id": "hdf5-" + digest.lower(),
        "original_format": "hdf5", "target_format": target,
        "source_file_sha256": digest.lower(),
        "preserved": "SamplePackage arrays, records, units, identities and provenance",
        "lossy_transformations": ["HDF5 storage layout, compression and unmodeled attributes are not retained"],
    }


def write_npz(
    source_hdf5: Path,
    path: Path,
    source_hdf5_sha256: str,
) -> None:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    sample, provenance = _load_source(source_hdf5, source_hdf5_sha256)
    payload = _payload(sample, provenance, source_hdf5_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        np.savez_compressed(stream, **payload)


def _graph_arrays(sample: SamplePackage) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    arrays = sample.arrays
    required = {"graph_node_features", "graph_edge_index", "graph_node_ids"}
    if not required <= arrays.keys():
        raise ValueError("graph arrays and explicit graph_node_ids are required")
    x, edges, ids = (arrays[name] for name in ("graph_node_features", "graph_edge_index", "graph_node_ids"))
    if x.ndim != 2 or x.shape[0] == 0 or x.dtype.kind not in "biuf" or not np.isfinite(x).all():
        raise ValueError("graph node features must be a finite real [N,F] array")
    if ids.ndim != 1 or len(ids) != len(x) or ids.dtype.kind not in "iuSU" or len(np.unique(ids)) != len(ids):
        raise ValueError("graph node IDs must be explicit, unique and aligned with features")
    if ids.dtype.kind in "SU" and any(not value.strip() for value in ids):
        raise ValueError("graph node IDs must not be blank")
    if edges.ndim != 2 or edges.shape[0] != 2 or edges.dtype.kind not in "iu":
        raise ValueError("graph edge_index must be integer [2,E], without implicit casting")
    if edges.size and (edges.min() < 0 or edges.max() >= len(x)):
        raise ValueError("graph edge index is outside the node range")
    contract = sample.solver_inputs.get("graph_contract", {})
    if not isinstance(contract, dict) or type(contract.get("directed")) is not bool:
        raise ValueError("graph_contract must explicitly declare directed")

    def feature_contract(prefix: str, width: int) -> None:
        names, units = contract.get(prefix + "_feature_names"), contract.get(prefix + "_feature_units")
        if not isinstance(names, list) or not isinstance(units, list) or len(names) != width or len(units) != width:
            raise ValueError(f"graph {prefix} feature names and units must match feature columns")
        if not all(isinstance(n, str) and n.strip() for n in names) or len(set(names)) != len(names) or not all(_unit_is_declared(u) for u in units):
            raise ValueError(f"graph {prefix} feature names or units are unresolved")

    feature_contract("node", x.shape[1])
    edge_attr = arrays.get("graph_edge_features")
    if edge_attr is not None:
        if edge_attr.ndim != 2 or edge_attr.shape[0] != edges.shape[1] or edge_attr.dtype.kind not in "biuf" or not np.isfinite(edge_attr).all():
            raise ValueError("graph edge features must be finite and align with edges")
        feature_contract("edge", edge_attr.shape[1])
    if not contract["directed"]:
        counts = Counter(map(tuple, edges.T.tolist()))
        if any(counts[(b, a)] != count for (a, b), count in counts.items()):
            raise ValueError("undirected graph must explicitly include matching reverse edges")
    return x, edges, edge_attr


def write_pyg(
    source_hdf5: Path,
    path: Path,
    source_hdf5_sha256: str,
) -> None:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    sample, provenance = _load_source(source_hdf5, source_hdf5_sha256)
    payload = _payload(sample, provenance, source_hdf5_sha256)
    x, edges, edge_attr = _graph_arrays(sample)
    try:
        import torch
        from torch_geometric.data import Data
    except ImportError as exc:
        raise RuntimeError("PyG export requires the optional 'ml' dependencies") from exc
    portable = io.BytesIO()
    np.savez_compressed(portable, **payload)
    data = Data(x=torch.as_tensor(x.copy()), edge_index=torch.as_tensor(edges.copy(), dtype=torch.long),
                edge_attr=None if edge_attr is None else torch.as_tensor(edge_attr.copy()), num_nodes=len(x))
    data.source_hdf5_sha256 = source_hdf5_sha256.lower()
    data.derivation_json = json.dumps(_derivation(source_hdf5_sha256, "pyg"), sort_keys=True)
    data.sample_id = sample.metadata.sample_id
    # Preserve unaligned fields, observations, IDs, units and non-graph arrays.
    # Do not invent y labels or node/field registration.
    data.package_npz = portable.getvalue()
    data.validate(raise_on_error=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        torch.save(data, stream)


def dataset_summary(sample: SamplePackage) -> dict[str, object]:
    return {
        "sample_id": sample.metadata.sample_id,
        "table_counts": {name: len(rows) for name, rows in sample.tables.items()},
        "array_shapes": {name: list(array.shape) for name, array in sample.arrays.items()},
        "asset_modalities": sorted({asset.modality.value for asset in sample.assets}),
    }
