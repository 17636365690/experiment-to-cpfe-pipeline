"""Offline checks that the opt-in real-solver harness cannot claim false success."""

import importlib.util
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def harness():
    path = Path("tests/integration/test_abaqus_optional.py")
    spec = importlib.util.spec_from_file_location("optional_abaqus_harness", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("reason", ["solver command is unavailable", "Abaqus license is unavailable"])
def test_optional_harness_marks_unavailable_solver_as_skip(harness, reason):
    assert hasattr(harness, "_require_completed_stage"), "optional test must classify failed/blocked stages"
    with pytest.raises(pytest.skip.Exception, match="unavailable"):
        harness._require_completed_stage("abaqus-datacheck", {"status": "blocked", "limitations": [reason]})


@pytest.mark.parametrize("stage,status,reason", [
    ("abaqus-analysis", "failed", "analysis divergence"),
    ("extract-odb", "failed", "missing required field"),
    ("export-hdf5", "blocked", "data validation failed"),
    ("abaqus-datacheck", "blocked", "MISSING_SOLVER_INPUT: units"),
])
def test_optional_harness_does_not_skip_contract_or_solver_failures(harness, stage, status, reason):
    assert hasattr(harness, "_require_completed_stage"), "optional test must classify failed/blocked stages"
    with pytest.raises(AssertionError, match=stage):
        harness._require_completed_stage(stage, {"status": status, "limitations": [reason]})


def test_optional_harness_uses_fresh_pipeline_and_stops_on_unavailable_license(harness, multimodal_sample_config, tmp_path, monkeypatch):
    from experiment_to_cpfe import pipeline

    config = yaml.safe_load(multimodal_sample_config.read_text())
    config["abaqus"]["timeout_seconds"] = 120
    multimodal_sample_config.write_text(yaml.safe_dump(config))
    run_dir = tmp_path / "fresh-run"
    assert hasattr(harness, "_run_real_roundtrip"), "optional test must orchestrate the full fresh pipeline"
    def unavailable(config_path, run, stage):
        assert stage == "datacheck", "analysis must not follow an unavailable datacheck"
        assert (run / "input/model.inp").is_file(), "real validation/build must occur before launching"
        return {"status": "blocked", "limitations": ["Abaqus license is unavailable"]}
    monkeypatch.setattr(pipeline, "run_abaqus_stage", unavailable)
    with pytest.raises(pytest.skip.Exception, match="unavailable"):
        harness._run_real_roundtrip(multimodal_sample_config, run_dir)
