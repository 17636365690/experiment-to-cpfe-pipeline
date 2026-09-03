"""Explicitly mapped CSV, TXT, and JSON record ingestion."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from experiment_to_cpfe.adapters.fields import load_point_field
from experiment_to_cpfe.adapters.voxel import load_voxel_array
from experiment_to_cpfe.assets.models import AssetRef, DataLayer
from experiment_to_cpfe.config import PipelineConfig, TabularSourceConfig
from experiment_to_cpfe.schema.models import SampleMetadata, SamplePackage, SourceRef


def _read_records(config: TabularSourceConfig) -> list[dict[str, object]]:
    if config.format in {"csv", "txt"}:
        if not config.delimiter:
            raise ValueError(f"delimiter is required for {config.format}")
        frame = pd.read_csv(
            config.path,
            sep=config.delimiter,
            encoding=config.encoding,
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
    return normalized


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
        rows = load_tabular_source(source)
        tables.setdefault(source.table_name, []).extend(rows)
        digest = _sha256(source.path)
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
                asset_id=f"asset-source-{index:04d}",
                parent_asset_id=None,
                modality=source.modality,
                format=source.format,
                uri=str(source.path),
                source_kind=source.source_kind,
                layer=DataLayer.RAW,
                units=source.units,
                coordinate_frame=source.coordinate_frame,
                axis_order=source.axis_order,
                dtype="table",
                shape=(len(rows), len(source.column_map)),
                native_layout=source.native_layout,
                sha256=digest,
                license=source.license,
                lossy_transformations=(),
            )
        )

    arrays = {}
    for external in config.assets:
        digest = _sha256(external.path)
        dtype = "binary"
        shape: tuple[int, ...] = ()
        native_layout = external.native_layout
        losses = external.lossy_transformations
        if external.modality.value == "point_field":
            adapter_metadata, array = load_point_field(
                external.path,
                external.adapter_config,
            )
            arrays[external.asset_id] = array
            dtype = str(adapter_metadata["dtype"])
            shape = tuple(adapter_metadata["shape"])
            native_layout = str(adapter_metadata["native_layout"])
            losses = tuple(adapter_metadata["lossy_transformations"])
        elif external.modality.value == "voxel_grid":
            adapter_metadata, array = load_voxel_array(
                external.path,
                external.adapter_config,
            )
            arrays[external.asset_id] = array
            dtype = str(adapter_metadata["dtype"])
            shape = tuple(adapter_metadata["shape"])
            native_layout = str(adapter_metadata["native_layout"])
            losses = tuple(adapter_metadata["lossy_transformations"])
        elif external.format.lower() in {"inp", "csv", "txt", "json"}:
            dtype = "text"

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
            )
        )

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
