"""Regression gates: data validity and recorded extraction cannot be downgraded."""
import json
import shutil

import pytest
import yaml


@pytest.mark.parametrize("format_name", ["hdf5", "npz", "pyg"])
def test_invalid_data_cannot_be_formally_exported(tmp_path, multimodal_sample_config, format_name):
    from experiment_to_cpfe import pipeline
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5

    config = multimodal_sample_config
    with (config.parent / "orientations.csv").open("a") as stream:
        stream.write("1,1,1,0,0,0\n")
    run = tmp_path / "invalid-run"
    pipeline.run_validate(config, run)
    before = (run / "reports/validation.json").read_bytes()
    assert not json.loads(before)["passed"]
    if format_name != "hdf5":
        # Model a legacy HDF5 that the old invalid-data gate incorrectly allowed.
        source = run / "dataset/sample.h5"
        write_hdf5(pipeline.load_sample_json(run / "input/normalized_sample.json"), source)
        pipeline._record_stage(run, config, {"stage": "export-hdf5", "status": "completed",
                                             "artifacts": [str(source)], "limitations": []})
    result = pipeline.run_export(config, run, format_name)
    assert result["status"] == "blocked"
    assert any("validation" in message.lower() for message in result["limitations"])
    suffix = {"hdf5": "h5", "npz": "npz", "pyg": "pt"}[format_name]
    assert not (run / f"dataset/sample.{suffix}").exists()
    assert (run / "reports/validation.json").read_bytes() == before
    manifest = json.loads((run / "reports/run_manifest.json").read_text())
    assert manifest["stages"][-1]["status"] == "blocked"


@pytest.mark.parametrize("status", ["completed", "failed", "blocked"])
@pytest.mark.parametrize("format_name", ["hdf5", "npz", "pyg"])
def test_recorded_extraction_cannot_disappear_from_export_requirements(tmp_path, multimodal_sample_config, status, format_name):
    from experiment_to_cpfe import pipeline

    config = multimodal_sample_config
    run = tmp_path / "missing-run"
    pipeline.run_validate(config, run)
    if format_name != "hdf5":
        pipeline.run_export(config, run, "hdf5")
    extracted = run / "solver/extracted"
    shutil.copytree("tests/fixtures/odb_extract_fixture", extracted)
    pipeline._record_stage(run, config, {"stage": "extract-odb", "status": status,
        "artifacts": [str(extracted / "metadata.json"), str(extracted / "frames.csv")],
        "limitations": ["synthetic audit ledger, not a real solve"]})
    before = json.loads((run / "reports/run_manifest.json").read_text())
    parked = run / "solver/parked-extracted"
    assert extracted.resolve().is_relative_to(tmp_path.resolve())
    assert parked.resolve().is_relative_to(tmp_path.resolve())
    extracted.rename(parked)
    result = pipeline.run_export(config, run, format_name)
    assert result["status"] == "blocked"
    suffix = {"hdf5": "h5", "npz": "npz", "pyg": "pt"}[format_name]
    assert not (run / f"dataset/sample.{suffix}").exists()
    after = json.loads((run / "reports/run_manifest.json").read_text())
    assert all(after["artifacts"][p] == entry for p, entry in before["artifacts"].items())
    assert (parked / "frames.csv").is_file()


def test_valid_curve_only_data_remain_exportable_without_solver_readiness(tmp_path, multimodal_sample_config):
    from experiment_to_cpfe import pipeline
    from experiment_to_cpfe.datasets.hdf5 import read_hdf5

    config = multimodal_sample_config
    payload = yaml.safe_load(config.read_text())
    payload["sources"] = [s for s in payload["sources"] if s["table_name"] == "measured_observations"]
    payload["assets"] = []
    payload["solver_inputs"] = {}
    config.write_text(yaml.safe_dump(payload))
    run = tmp_path / "curve-only"
    pipeline.run_validate(config, run)
    assert json.loads((run / "reports/validation.json").read_text())["passed"] is True
    assert json.loads((run / "reports/solver_readiness.json").read_text())["ready"] is False
    assert pipeline.run_export(config, run, "hdf5")["status"] == "completed"
    assert pipeline.run_export(config, run, "npz")["status"] == "completed"
    sample = read_hdf5(run / "dataset/sample.h5")
    assert sample.tables["measured_observations"]
    assert "simulation_records" not in sample.tables
    assert not (run / "input/model.inp").exists()
