"""Explicitly mapped CSV, TXT, and JSON record ingestion."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import numpy as np

from experiment_to_cpfe.adapters.ebsd import load_ebsd_text
from experiment_to_cpfe.adapters.fields import load_point_field
from experiment_to_cpfe.adapters.hdf5_layout import load_hdf5_fields
from experiment_to_cpfe.adapters.voxel import load_voxel_array
from experiment_to_cpfe.adapters.table_blocks import read_table_block, convert_columns
from experiment_to_cpfe.assets.models import AssetRef, ConversionRecord, DataLayer, SourceKind
from experiment_to_cpfe.assets.registry import array_payload_sha256, table_payload_sha256
from experiment_to_cpfe.config import PipelineConfig, TabularSourceConfig
from experiment_to_cpfe.schema.models import OrientationSpec, SampleMetadata, SamplePackage, SourceRef
from experiment_to_cpfe.schema.validation import _unit_is_declared


def _read_records(config: TabularSourceConfig) -> list[dict[str, object]]:
    if config.format in {"csv", "txt"}:
        if not config.delimiter:
            raise ValueError(f"delimiter is required for {config.format}")
        frame = pd.read_csv(
            config.path,
            sep=config.delimiter,
            encoding=config.encoding,
            dtype={source: str for target, source in config.column_map.items() if target == "id" or target.endswith("_id")},
        )
        return frame.to_dict(orient="records")

    payload = json.loads(config.path.read_text(encoding=config.encoding))
    if not isinstance(payload, list) or not all(
        isinstance(item, dict) for item in payload
    ):
        raise ValueError("JSON tabular source must be an array of objects")
    return payload


def load_tabular_source(config: TabularSourceConfig) -> list[dict[str, object]]:
    """Read records using only the configured source-to-target column mapping."""

    if {"source_asset_id", "source_kind"}.intersection(config.column_map):
        raise ValueError("source_asset_id and source_kind are reserved row evidence fields")
    missing_units = [name for name in config.column_map if not _unit_is_declared(config.units.get(name))]
    if missing_units:
        raise ValueError(f"explicit units are required for mapped table fields: {sorted(missing_units)}")
    if config.table_name == "simulation_records" and config.source_kind != SourceKind.SIMULATED:
        raise ValueError("simulation_records requires simulated source evidence")
    if config.table_name == "measured_observations" and config.source_kind == SourceKind.SIMULATED:
        raise ValueError("simulated source evidence belongs in simulation_records")
    if config.block is not None:
        return convert_columns(read_table_block(config), config)
    if config.format == "xlsx":
        raise ValueError("XLSX requires an explicit block")
    records = _read_records(config)
    normalized: list[dict[str, object]] = []
    for index, record in enumerate(records):
        missing = [
            source_name
            for source_name in config.column_map.values()
            if source_name not in record
        ]
        if missing:
            raise ValueError(
                f"row {index} is missing mapped source columns: {sorted(missing)}"
            )
        normalized.append(
            {
                target_name: record[source_name]
                for target_name, source_name in config.column_map.items()
            }
        )
    return convert_columns(normalized, config)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assemble_sample(config: PipelineConfig) -> SamplePackage:
    """Assemble configured tabular sources into one normalized sample."""

    tables: dict[str, list[dict[str, object]]] = {}
    sources: list[SourceRef] = []
    assets: list[AssetRef] = []

    for index, source in enumerate(config.sources):
        digest = _sha256(source.path)
        rows = load_tabular_source(source)
        if _sha256(source.path) != digest:
            raise ValueError(f"source changed while being parsed: {source.path}")
        source_asset_id = f"asset-source-{index:04d}"
        rows = [{**row, "source_asset_id": source_asset_id, "source_kind": source.source_kind.value} for row in rows]
        tables.setdefault(source.table_name, []).extend(rows)
        selection_metadata = {}
        if source.block is not None:
            selection_metadata["block"] = source.block.model_dump(mode="json")
        if source.conversions:
            selection_metadata["conversions"] = {k: v.model_dump(mode="json") for k, v in source.conversions.items()}
        sources.append(
            SourceRef(
                kind=source.source_kind,
                uri=str(source.path),
                sha256=digest,
                role=source.table_name,
            )
        )
        assets.append(
            AssetRef(
                asset_id=source_asset_id,
                parent_asset_id=None,
                modality=source.modality,
                format=source.format,
                uri=str(source.path),
                source_kind=source.source_kind,
                layer=DataLayer.RAW,
                units={**source.units, **{name: conversion.source_unit for name, conversion in source.conversions.items()}},
                coordinate_frame=source.coordinate_frame,
                axis_order=source.axis_order,
                dtype="table",
                shape=(len(rows), len(source.column_map)),
                native_layout=source.native_layout,
                sha256=digest,
                license=source.license,
                lossy_transformations=(),
                descriptive_metadata={**selection_metadata, "table_name": source.table_name, "column_map": dict(source.column_map),
                    "normalized_units": dict(source.units),
                    "row_source_binding": "source_asset_id and source_kind identify each normalized row's source"},
            )
        )
        normalized_hash = table_payload_sha256(rows)
        assets.append(assets[-1].model_copy(update={
            "asset_id": f"{source_asset_id}:normalized",
            "parent_asset_id": source_asset_id,
            "format": "normalized-table-json",
            "uri": f"sample-table:{source.table_name}?source_asset_id={source_asset_id}",
            "layer": DataLayer.CURATED,
            "units": source.units,
            "native_layout": "normalized_table_explicit_columns",
            "sha256": normalized_hash,
            "shape": (len(rows), len(rows[0]) if rows else len(source.column_map) + 2),
            "descriptive_metadata": {**selection_metadata, "table_key": source.table_name, "row_source_asset_id": source_asset_id,
                "column_map": dict(source.column_map), "payload_hash_encoding": "normalized-table-json-v1",
                "transformation": "explicit block/column selection, typed parsing and recorded affine conversions; source evidence fields attached; no coordinate conversion"},
            "lossy_transformations": (
                "Only mapped source columns are normalized; unselected columns remain in the raw source",
                "Source formatting and textual numeric spelling are not retained in normalized records; raw source is preserved",
            ),
            "conversion": ConversionRecord(original_format=source.format, target_format="normalized-table-json",
                source_sha256=digest, hash_scope="logical_payload", target_payload_sha256=normalized_hash,
                source_hash_verified=True),
        }))

    arrays = {}
    for external in config.assets:
        digest = _sha256(external.path)
        dtype = "binary"
        shape: tuple[int, ...] = ()
        native_layout = external.native_layout
        losses = external.lossy_transformations
        adapter_metadata: dict[str, object] = {}
        adapter_config = {
            "format": external.format, "units": external.units,
            "coordinate_frame": external.coordinate_frame, "axis_order": external.axis_order,
            **external.adapter_config,
        }
        if external.format.lower() in {"h5", "hdf5", "dream3d"} and external.modality.value in {"orientation_map", "point_field", "field_sequence"}:
            adapter_metadata, array = load_hdf5_fields(external.path, adapter_config)
        elif external.modality.value == "orientation_map" and external.adapter_config:
            if external.format.lower() not in {"ang", "ctf", "csv", "txt"}:
                raise ValueError(f"unsupported orientation-map format: {external.format}")
            column_map = adapter_config.get("column_map")
            if not isinstance(column_map, dict) or not column_map:
                raise ValueError("explicit column_map is required for orientation text")
            rows = load_ebsd_text(external.path, str(adapter_config.get("profile", "")), column_map)
            array = np.array([[row[column] for column in column_map] for row in rows], dtype=float)
            adapter_metadata = {"columns": list(column_map), "column_map": column_map,
                "profile": adapter_config["profile"], "dtype": array.dtype.name, "shape": array.shape,
                "native_layout": f"{adapter_config['profile']}:explicit_columns",
                "lossy_transformations": tuple(adapter_config.get("lossy_transformations", ())) }
        elif external.modality.value == "point_field":
            adapter_metadata, array = load_point_field(
                external.path,
                adapter_config,
            )
        elif external.modality.value == "voxel_grid":
            adapter_metadata, array = load_voxel_array(
                external.path,
                adapter_config,
            )
        elif external.format.lower() in {"inp", "csv", "txt", "json"}:
            dtype = "text"

        if adapter_metadata:
            if _sha256(external.path) != digest:
                raise ValueError(f"source changed while being parsed: {external.path}")
            for name, declared in (("coordinate_frame", external.coordinate_frame), ("axis_order", external.axis_order)):
                actual = adapter_config.get(name)
                if name == "axis_order":
                    actual = tuple(actual or ())
                if actual != declared:
                    raise ValueError(f"asset {external.asset_id} {name} conflicts with adapter declaration")
            if external.modality.value != "voxel_grid" and adapter_config["units"] != external.units:
                raise ValueError(f"asset {external.asset_id} units conflict with adapter declaration")
            if external.modality.value == "voxel_grid" and external.units.get("spacing") != adapter_config["units"]:
                raise ValueError(f"asset {external.asset_id} spacing units conflict with adapter declaration")
            if external.format == "vti" and external.units.get(str(adapter_metadata.get("array_name"))) != adapter_metadata.get("value_units"):
                raise ValueError(f"asset {external.asset_id} VTI scalar units conflict with adapter declaration")
            if "columns" in adapter_metadata:
                columns = adapter_metadata["columns"]
                if any(column not in external.units for column in columns):
                    raise ValueError("units are required for every mapped field")
                if len(external.axis_order) != 2 or len(set(external.axis_order)) != 2:
                    raise ValueError("mapped record arrays require two unique axis_order entries")
                if external.coordinate_frame is None:
                    raise ValueError("mapped record arrays require coordinate_frame")
            if external.modality.value == "orientation_map":
                orientation = OrientationSpec.model_validate(adapter_config.get("orientation", {}))
                adapter_metadata["orientation"] = orientation.model_dump(mode="json")
            if external.modality.value == "point_field" and external.format.lower() in {"h5", "hdf5", "dream3d"}:
                coordinates = adapter_config.get("coordinate_columns")
                fields = adapter_config.get("field_columns")
                if not isinstance(coordinates, (list, tuple)) or not coordinates or not isinstance(fields, (list, tuple)) or not fields:
                    raise ValueError("HDF5 point fields require coordinate_columns and field_columns")
                selected = [*coordinates, *fields]
                if len(set(selected)) != len(selected) or set(selected) != set(adapter_metadata["columns"]):
                    raise ValueError("HDF5 point coordinate and field columns must partition dataset_map")
                adapter_metadata.update(coordinate_columns=list(coordinates), field_columns=list(fields))
            adapter_metadata.update(units=adapter_config["units"], coordinate_frame=external.coordinate_frame, axis_order=external.axis_order)
            arrays[external.asset_id] = array
            dtype = str(adapter_metadata["dtype"])
            shape = tuple(adapter_metadata["shape"])
            native_layout = str(adapter_metadata["native_layout"])
            losses = tuple(dict.fromkeys((*losses, *adapter_metadata["lossy_transformations"])))

        sources.append(
            SourceRef(
                kind=external.source_kind,
                uri=str(external.path),
                sha256=digest,
                role=external.modality.value,
            )
        )
        assets.append(
            AssetRef(
                asset_id=external.asset_id,
                parent_asset_id=external.parent_asset_id,
                modality=external.modality,
                format=external.format,
                uri=str(external.path),
                source_kind=external.source_kind,
                layer=external.layer,
                units=external.units,
                coordinate_frame=external.coordinate_frame,
                axis_order=external.axis_order,
                dtype=dtype,
                shape=shape,
                native_layout=native_layout,
                sha256=digest,
                license=external.license,
                lossy_transformations=losses,
                descriptive_metadata=adapter_metadata,
            )
        )
        if adapter_metadata:
            normalized_hash = array_payload_sha256(array)
            normalized_metadata = {**adapter_metadata, "array_key": external.asset_id,
                "payload_hash_encoding": "numpy-array-v1", "transformation": "explicit source fields to plain numeric array; no inferred unit or coordinate conversion"}
            normalized_losses = losses
            if "columns" in adapter_metadata:
                normalized_losses = tuple(dict.fromkeys((*losses, "Only explicitly mapped columns are normalized; other columns and vendor headers remain in the raw source")))
            assets.append(assets[-1].model_copy(update={
                "asset_id": f"{external.asset_id}:normalized",
                "parent_asset_id": external.asset_id,
                "format": "numpy-array", "uri": f"hdf5:/derived/arrays/{external.asset_id}",
                "layer": DataLayer.CURATED, "sha256": normalized_hash,
                "descriptive_metadata": normalized_metadata,
                "lossy_transformations": normalized_losses,
                "conversion": ConversionRecord(original_format=external.format, target_format="numpy-array",
                    source_sha256=digest, hash_scope="logical_payload", target_payload_sha256=normalized_hash,
                    source_hash_verified=True),
            }))

    from experiment_to_cpfe.adapters.native import decode_native, promote_native
    for imported in config.imports:
        draft = decode_native(imported)
        new_arrays, new_assets = promote_native(draft)
        if set(arrays).intersection(new_arrays):
            raise ValueError("native imports contain duplicate array names")
        arrays.update(new_arrays)
        assets.extend(new_assets)
        sources.extend(SourceRef(kind=source.source_kind, uri=str(source.path), sha256=draft.source_hashes[key],
                                 role=imported.modality.value) for key, source in imported.files.items())

    sample = config.sample
    metadata = SampleMetadata(
        sample_id=sample.sample_id,
        experiment_id=sample.experiment_id,
        microstructure_id=sample.microstructure_id,
        load_path_id=sample.load_path_id,
        schema_version=sample.schema_version,
        coordinate=sample.coordinate,
        unit_system=sample.unit_system,
        tensor_order=sample.tensor_order,
        orientation=sample.orientation,
        sources=tuple(sources),
    )
    return SamplePackage(
        metadata=metadata,
        tables=tables,
        arrays=arrays,
        assets=tuple(assets),
        solver_inputs=config.solver_inputs,
    )
