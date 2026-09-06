"""Canonical HDF5 package writer and reader."""

import json
from pathlib import Path

import h5py
import numpy as np

from experiment_to_cpfe.assets.models import AssetRef
from experiment_to_cpfe.assets.registry import array_payload_sha256, table_payload_sha256
from experiment_to_cpfe.provenance.hashing import sha256_file
from experiment_to_cpfe.schema.models import SampleMetadata, SamplePackage


CANONICAL_GROUPS = (
    "meta",
    "assets",
    "geometry",
    "mesh",
    "grains",
    "grain_boundaries",
    "load_history",
    "measured",
    "simulation",
    "macro_response",
    "derived",
    "provenance",
    "quality",
)
TABLE_GROUP = {
    "grains": "grains",
    "grain_boundaries": "grain_boundaries",
    "mesh_nodes": "mesh",
    "mesh_elements": "mesh",
    "load_history": "load_history",
    "measured_observations": "measured",
    "simulation_records": "simulation",
}
CONTAINER_FORMAT = "experiment-to-cpfe"
CONTAINER_VERSION = "1"


def _json_default(value: object) -> object:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _json_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=_json_default)


def _verify_logical_lineage(sample: SamplePackage) -> None:
    for asset in sample.assets:
        if asset.conversion is None or asset.conversion.hash_scope != "logical_payload":
            continue
        if asset.format == "numpy-array":
            array_key = asset.descriptive_metadata.get("array_key")
            if array_key not in sample.arrays:
                raise ValueError(f"logical payload hash has no supported array: {asset.asset_id}")
            if array_payload_sha256(sample.arrays[array_key]) != asset.conversion.target_payload_sha256:
                raise ValueError(f"logical array payload hash mismatch: {asset.asset_id}")
        elif asset.format == "normalized-table-json":
            table_key = asset.descriptive_metadata.get("table_key")
            source_id = asset.descriptive_metadata.get("row_source_asset_id")
            encoding = asset.descriptive_metadata.get("payload_hash_encoding")
            if not isinstance(table_key, str) or table_key not in sample.tables or source_id != asset.parent_asset_id or encoding != "normalized-table-json-v1":
                raise ValueError(f"logical table payload selector is invalid: {asset.asset_id}")
            selected = [row for row in sample.tables[table_key] if row.get("source_asset_id") == source_id]
            if table_payload_sha256(selected) != asset.conversion.target_payload_sha256:
                raise ValueError(f"logical table payload hash mismatch: {asset.asset_id}")
        else:
            raise ValueError(f"unsupported logical payload format: {asset.format}")


def _preflight_array_dtypes(arrays: dict[str, np.ndarray]) -> None:
    """Reject unsupported array types before reserving an output file."""
    for name, array in arrays.items():
        if array.dtype.fields is not None or array.dtype.kind not in "biufcSU":
            raise ValueError(f"unsupported canonical HDF5 array dtype for {name}: {array.dtype}")
        if array.dtype.kind == "U":
            for value in array.reshape(-1).tolist():
                if "\0" in value:
                    raise ValueError(f"Unicode array dtype contains unsupported embedded NUL: {name}")
                try:
                    value.encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise ValueError(f"Unicode array dtype contains invalid UTF-8 text: {name}") from exc
        else:
            try:
                h5py.h5t.py_create(array.dtype, logical=True)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"unsupported canonical HDF5 array dtype for {name}: {array.dtype}") from exc


def write_hdf5(
    sample: SamplePackage,
    path: Path,
    source_manifest: dict[str, object] | None = None,
) -> str:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    _preflight_array_dtypes(sample.arrays)
    _verify_logical_lineage(sample)
    for name in (*sample.arrays, *(asset.asset_id for asset in sample.assets)):
        if not isinstance(name, str) or name in {"", ".", ".."} or "/" in name or "\\" in name or "\x00" in name:
            raise ValueError(f"HDF5 array and asset names must be single path components: {name!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    string_type = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "x") as handle:
        handle.attrs["container_format"] = CONTAINER_FORMAT
        handle.attrs["container_version"] = CONTAINER_VERSION
        for group_name in CANONICAL_GROUPS:
            handle.create_group(group_name, track_order=True)
        handle["meta"].create_dataset(
            "sample_metadata_json",
            data=_json_text(sample.metadata.model_dump(mode="json")),
            dtype=string_type,
        )
        handle["meta"].attrs["schema_version"] = sample.metadata.schema_version
        handle["meta"].create_dataset(
            "solver_inputs_json",
            data=_json_text(sample.solver_inputs),
            dtype=string_type,
        )

        for asset in sample.assets:
            group = handle["assets"].create_group(asset.asset_id)
            group.attrs["metadata_json"] = _json_text(asset.model_dump(mode="json"))

        for table_name, rows in sample.tables.items():
            parent = handle[TABLE_GROUP[table_name]]
            table_group = parent.create_group(table_name)
            table_group.create_dataset(
                "records_json",
                data=_json_text(rows),
                dtype=string_type,
            )
            if rows:
                common_columns = set(rows[0]).intersection(*(set(row) for row in rows[1:]))
                columns_group = table_group.create_group("columns")
                for column in sorted(common_columns):
                    values = [row[column] for row in rows]
                    if all(isinstance(value, (int, float, np.number)) for value in values):
                        columns_group.create_dataset(column, data=np.asarray(values))

        arrays_group = handle["derived"].create_group("arrays")
        for name, array in sample.arrays.items():
            options = {"compression": "gzip", "shuffle": True} if array.size and array.ndim else {}
            if array.dtype.kind == "U":
                dataset = arrays_group.create_dataset(name, data=array.astype(object), dtype=string_type, **options)
                dataset.attrs["storage_encoding"] = "utf-8"
            else:
                dataset = arrays_group.create_dataset(name, data=array, **options)
            dataset.attrs["dtype"] = array.dtype.name
            dataset.attrs["dtype_descriptor"] = array.dtype.str
            dataset.attrs["shape"] = array.shape

        handle["provenance"].create_dataset(
            "source_manifest_json",
            data=_json_text(source_manifest or {}),
            dtype=string_type,
        )
        handle["quality"].attrs["missing_values_filled"] = False
    return sha256_file(path)


def _decode(dataset: h5py.Dataset) -> str:
    value = dataset[()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def read_hdf5(path: Path) -> SamplePackage:
    with h5py.File(Path(path), "r") as handle:
        if handle.attrs.get("container_format") != CONTAINER_FORMAT:
            raise ValueError("not an experiment-to-cpfe canonical HDF5 container")
        if handle.attrs.get("container_version") != CONTAINER_VERSION:
            raise ValueError("unsupported canonical HDF5 container version")
        metadata = SampleMetadata.model_validate(
            json.loads(_decode(handle["meta/sample_metadata_json"]))
        )
        solver_inputs = json.loads(_decode(handle["meta/solver_inputs_json"]))
        assets = tuple(
            AssetRef.model_validate(json.loads(group.attrs["metadata_json"]))
            for group in handle["assets"].values()
        )
        tables: dict[str, list[dict[str, object]]] = {}
        for table_name, group_name in TABLE_GROUP.items():
            location = f"{group_name}/{table_name}/records_json"
            if location in handle:
                tables[table_name] = json.loads(_decode(handle[location]))
        arrays = {}
        for name, dataset in handle["derived/arrays"].items():
            if dataset.attrs.get("storage_encoding") == "utf-8":
                dtype = np.dtype(dataset.attrs["dtype_descriptor"])
                if dtype.kind != "U":
                    raise ValueError(f"invalid Unicode storage dtype for {name}")
                arrays[name] = np.asarray(dataset.asstr()[()], dtype=dtype)
            else:
                arrays[name] = np.asarray(dataset)
            if arrays[name].shape != tuple(dataset.attrs["shape"]):
                raise ValueError(f"stored array shape disagrees with metadata for {name}")
    sample = SamplePackage(metadata, tables, arrays, assets, solver_inputs)
    _verify_logical_lineage(sample)
    return sample
