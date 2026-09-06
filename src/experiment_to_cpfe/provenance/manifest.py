"""Run-directory creation and deterministic provenance manifests."""

from datetime import datetime, timezone
import json
from pathlib import Path

from experiment_to_cpfe.provenance.hashing import sha256_file


STAGE_DIRECTORIES = ("input", "solver", "dataset", "reports")


def create_run_directory(root: Path, sample_id: str, run_id: str) -> Path:
    target = Path(root) / sample_id / run_id
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"run directory is non-empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    for name in STAGE_DIRECTORIES:
        (target / name).mkdir()
    return target


def build_run_manifest(
    run_dir: Path,
    config_path: Path,
    stage_records: list[dict[str, object]],
) -> dict[str, object]:
    artifacts: dict[str, dict[str, object]] = {}
    for stage in stage_records:
        for raw_path in stage.get("artifacts", []):
            path = Path(str(raw_path))
            if path.is_file():
                artifacts[str(path)] = {
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
    return {
        "schema_version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(Path(run_dir)),
        "config_path": str(Path(config_path)),
        "config_sha256": sha256_file(config_path) if Path(config_path).is_file() else None,
        "stages": stage_records,
        "artifacts": artifacts,
        "limitations": [
            limitation
            for stage in stage_records
            for limitation in stage.get("limitations", [])
        ],
    }


def write_manifest(manifest: dict[str, object], path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
