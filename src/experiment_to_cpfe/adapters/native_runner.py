"""Offline inspection reports for partially understood native inputs."""

from datetime import datetime, timezone
import json
from pathlib import Path

import yaml

from experiment_to_cpfe.adapters.native import decode_native
from experiment_to_cpfe.adapters.native_models import NativeImportConfig
from experiment_to_cpfe.provenance.hashing import sha256_file


def run_native_adapt(config_path: Path, run_dir: Path) -> dict:
    """Evaluate each independent native import without creating a complete sample."""
    config_path, run_dir = Path(config_path).resolve(), Path(run_dir)
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid native configuration: {exc}") from exc
    if not isinstance(payload, dict) or set(payload) - {"imports"} or not payload.get("imports"):
        raise ValueError("native adapt config requires only a nonempty imports list")
    imports = [NativeImportConfig.model_validate(item) for item in payload["imports"]]
    if len({item.import_id for item in imports}) != len(imports):
        raise ValueError("native import IDs must be unique")
    run_dir.mkdir(parents=True, exist_ok=False)
    reports = []
    for item in imports:
        item = item.model_copy(update={"files": {key: source.model_copy(update={"path":
            source.path if source.path.is_absolute() else (config_path.parent / source.path).resolve()})
            for key, source in item.files.items()}})
        try:
            report = decode_native(item).report()
        except (ValueError, OSError, RuntimeError, KeyError, IndexError, TypeError) as exc:
            report = {"import_id": item.import_id, "decoding": "failed", "semantic_conversion": "blocked",
                      "blockers": [str(exc)], "complete_sample": "not_created", "solver_readiness": "not_evaluated",
                      "physical_validation": "not_performed"}
        reports.append(report)
    result = {"status": "blocked" if any(r["semantic_conversion"] == "blocked" for r in reports) else "completed",
              "scope": "native decoding and semantic eligibility only; no complete sample or solver execution",
              "utc": datetime.now(timezone.utc).isoformat(), "config_sha256": sha256_file(config_path), "imports": reports}
    target = run_dir / "reports"
    target.mkdir()
    (target / "native-adapters.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Native adapter report", "", result["scope"], ""]
    for report in reports:
        lines += [f"## {report['import_id']}", "", f"Decoding: {report['decoding']}; semantic conversion: {report['semantic_conversion']}", ""]
        lines += [f"- {issue}" for issue in report["blockers"]]
        lines.append("")
    (target / "native-adapters.md").write_text("\n".join(lines), encoding="utf-8")
    return result
