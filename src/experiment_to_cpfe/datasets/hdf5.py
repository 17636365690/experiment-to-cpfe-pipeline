"""Canonical HDF5 package writer and reader."""

import json
from pathlib import Path

import h5py
import numpy as np

from experiment_to_cpfe.assets.models import AssetRef
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


def write_hdf5(
    sample: SamplePackage,
    path: Path,
    source_manifest: dict[str, object] | None = None,
) -> str:
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    string_type = h5py.string_dtype(encoding="utf-8")
    with h5py.File(path, "x") as handle:
        for group_name in CANONICAL_GROUPS:
            handle.require_group(group_name)
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
            options = {"compression": "gzip", "shuffle": True} if array.size else {}
            dataset = arrays_group.create_dataset(name, data=array, **options)
            dataset.attrs["dtype"] = array.dtype.name
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
        arrays = {
            name: np.asarray(dataset)
            for name, dataset in handle["derived/arrays"].items()
        }
    return SamplePackage(metadata, tables, arrays, assets, solver_inputs)
