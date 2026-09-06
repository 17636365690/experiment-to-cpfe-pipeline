import os
import json
from pathlib import Path

import numpy as np
import pytest


def _require_completed_stage(stage: str, result: dict) -> None:
    details = "; ".join(result.get("limitations", ()))
    unavailable = "unavailable" in details.lower() and any(word in details.lower() for word in ("command", "license"))
    if stage in {"abaqus-datacheck", "abaqus-analysis", "extract-odb"} and result.get("status") == "blocked" and unavailable:
        pytest.skip(f"{stage} unavailable: {details}")
    assert result.get("status") == "completed", f"{stage} {result.get('status')}: {details}"


def _run_real_roundtrip(config_path: Path, run_dir: Path) -> None:
    from experiment_to_cpfe import pipeline
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.datasets.hdf5 import read_hdf5
    from experiment_to_cpfe.provenance.hashing import sha256_file
    from experiment_to_cpfe.schema.solver_contract import inspect_mesh, parse_keyword_blocks
    from experiment_to_cpfe.solvers.abaqus.bundle import snapshot_input_bundle

    config_path, run_dir = Path(config_path).resolve(), Path(run_dir).resolve()
    assert not run_dir.exists(), "real integration requires a fresh, nonexistent run directory"
    config = load_pipeline_config(config_path)
    assert config.abaqus.cpus == 1, "real integration is restricted to one CPU"
    assert config.abaqus.timeout_seconds <= 600, "real integration requires an explicit timeout <= 600 seconds per stage"
    assert config.abaqus.required_fields, "real integration requires explicit nonempty requested fields"
    _require_completed_stage("validate", pipeline.run_validate(config_path, run_dir))
    _require_completed_stage("build-inp", pipeline.run_build_inp(config_path, run_dir))
    submission_relative = Path()
    if config.abaqus.input_bundle is None:
        deck = (run_dir / "input/model.inp").read_text(encoding="utf-8")
    else:
        report = json.loads((run_dir / "reports/native_bundle.json").read_text(encoding="utf-8"))
        snapshot = snapshot_input_bundle(Path(report["entrypoint"]), source_root=Path(report["bundle_root"]), submission_dir=Path(report["submission_dir"]))
        deck = snapshot.expanded_text()
        submission_relative = config.abaqus.input_bundle.submission_dir.relative_to(config.abaqus.input_bundle.source_root)
    nodes, elements, _, _, errors = inspect_mesh(parse_keyword_blocks(deck))
    assert not errors, errors
    assert 0 < len(elements) <= 1000 and 0 < len(nodes) <= 10000, "real integration requires a tiny model (<= 1000 elements, <= 10000 nodes)"
    for stage in ("datacheck", "analysis"):
        _require_completed_stage(f"abaqus-{stage}", pipeline.run_abaqus_stage(config_path, run_dir, stage))
    odb = run_dir / "solver/analysis" / submission_relative / f"{config.abaqus.job_name}.odb"
    assert odb.is_file() and odb.stat().st_size > 0, "analysis must produce a nonempty ODB"
    odb_hash = sha256_file(odb)
    _require_completed_stage("extract-odb", pipeline.run_extract_odb(config_path, run_dir))
    assert sha256_file(odb) == odb_hash, "ODB changed during read-only extraction"
    for format_name in ("hdf5", "npz"):
        _require_completed_stage(f"export-{format_name}", pipeline.run_export(config_path, run_dir, format_name))
    hdf5 = run_dir / "dataset/sample.h5"
    sample = read_hdf5(hdf5)
    records = sample.tables.get("simulation_records", [])
    assert records, "canonical HDF5 must contain extracted simulated records"
    assert any(asset.source_kind.value == "simulated" and asset.format == "odb-extraction-bundle" for asset in sample.assets)
    assert any(asset.format == "odb" and asset.sha256 == odb_hash for asset in sample.assets)
    assert all(np.isfinite(float(row["value"])) and row.get("unit") for row in records)
    with np.load(run_dir / "dataset/sample.npz", allow_pickle=False) as npz:
        assert npz["__source_hdf5_sha256__"].item() == sha256_file(hdf5)
        assert json.loads(npz["__tables_json__"].item())["simulation_records"] == records
    reports = run_dir / "reports"
    for name in ("run_manifest.json", "validation.json", "solver_readiness.json", "qa_report.md"):
        assert (reports / name).is_file(), f"missing required report {name}"
    manifest = json.loads((reports / "run_manifest.json").read_text(encoding="utf-8"))
    expected = ("validate", "build-inp", "abaqus-datacheck", "abaqus-analysis", "extract-odb", "export-hdf5", "export-npz")
    assert tuple(stage["stage"] for stage in manifest["stages"]) == expected
    for stage in manifest["stages"]:
        assert stage["status"] == "completed" and stage.get("started_at") and stage.get("finished_at")
        assert stage.get("artifacts"), f"stage {stage['stage']} has no artifact receipt"
    for name, receipt in manifest["artifacts"].items():
        assert sha256_file(Path(name)) == receipt["sha256"], f"artifact hash mismatch: {name}"


@pytest.mark.skipif(
    os.environ.get("EXP2CPFE_RUN_ABAQUS") != "1",
    reason="real Abaqus integration is opt-in via EXP2CPFE_RUN_ABAQUS=1",
)
def test_user_supplied_real_abaqus_roundtrip():
    config = os.environ.get("EXP2CPFE_ABAQUS_CONFIG")
    run_dir = os.environ.get("EXP2CPFE_ABAQUS_RUN_DIR")
    if not config or not run_dir:
        pytest.skip("EXP2CPFE_ABAQUS_CONFIG and EXP2CPFE_ABAQUS_RUN_DIR are required")

    _run_real_roundtrip(Path(config), Path(run_dir))
