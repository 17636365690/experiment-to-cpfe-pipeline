"""Host-side bridge for Abaqus ODB extraction bundles."""

import csv
from dataclasses import dataclass
import json
from pathlib import Path

from experiment_to_cpfe.assets.models import (
    AssetKind,
    AssetRef,
    DataLayer,
    SourceKind,
)
from experiment_to_cpfe.schema.models import SampleMetadata, SamplePackage, SourceRef


@dataclass(frozen=True)
class ExtractionRequest:
    odb_path: Path
    output_dir: Path
    fields: tuple[str, ...]
    position: str


def build_abaqus_extraction_command(
    request: ExtractionRequest,
    abaqus_command: tuple[str, ...],
) -> tuple[str, ...]:
    script = Path(__file__).resolve().parents[4] / "scripts" / "abaqus_extract_odb.py"
    return (
        *abaqus_command,
        "python",
        str(script),
        "--odb",
        str(Path(request.odb_path)),
        "--output-dir",
        str(Path(request.output_dir)),
        "--fields",
        ",".join(request.fields),
        "--position",
        request.position,
    )


def extraction_bundle_is_complete(path: Path) -> tuple[bool, tuple[str, ...]]:
    path = Path(path)
    required = ("metadata.json", "frames.csv")
    missing = tuple(name for name in required if not (path / name).is_file())
    return not missing, missing


def _coerce(value: str) -> object:
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def load_extraction_bundle(path: Path) -> SamplePackage:
    path = Path(path)
    complete, missing = extraction_bundle_is_complete(path)
    if not complete:
        raise ValueError(f"incomplete extraction bundle: {', '.join(missing)}")
    metadata_payload = json.loads(
        (path / "metadata.json").read_text(encoding="utf-8")
    )
    with (path / "frames.csv").open("r", encoding="utf-8", newline="") as stream:
        records = [
            {key: _coerce(value) for key, value in row.items()}
            for row in csv.DictReader(stream)
        ]
    odb_hash = metadata_payload["odb_sha256"]
    odb_path = metadata_payload["odb_path"]
    source = SourceRef(
        kind=SourceKind.SIMULATED,
        uri=odb_path,
        sha256=odb_hash,
        role="abaqus_odb",
    )
    sample_metadata_payload = dict(metadata_payload["sample_metadata"])
    sample_metadata_payload["sources"] = [source.model_dump(mode="json")]
    metadata = SampleMetadata.model_validate(sample_metadata_payload)
    asset = AssetRef(
        asset_id=f"asset-solver-output-{odb_hash[:16]}",
        parent_asset_id=None,
        modality=AssetKind.FIELD_SEQUENCE,
        format="odb-extraction-bundle",
        uri=str(path),
        source_kind=SourceKind.SIMULATED,
        layer=DataLayer.SOLVER_OUTPUT,
        units={"stress": "Pa", "strain": "1", "time": "s"},
        coordinate_frame=metadata.coordinate.name,
        axis_order=("frame", "location", "component"),
        dtype="mixed",
        shape=(len(records),),
        native_layout="abaqus_odb_csv_bundle_v0.1",
        sha256=odb_hash,
        license="user-generated",
        lossy_transformations=("ODB field values flattened to records",),
    )
    return SamplePackage(
        metadata=metadata,
        tables={"simulation_records": records},
        arrays={},
        assets=(asset,),
        solver_inputs={"extraction": metadata_payload},
    )
