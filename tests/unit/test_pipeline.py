import json
import shutil


def test_validate_build_and_export_commands_write_stage_artifacts(
    tmp_path,
    multimodal_sample_config,
):
    from experiment_to_cpfe.cli import main

    run_dir = tmp_path / "offline-run"
    config = str(multimodal_sample_config)

    assert main(["validate", "--config", config, "--run-dir", str(run_dir)]) == 0
    assert main(["build-inp", "--config", config, "--run-dir", str(run_dir)]) == 0
    assert main(["export", "--config", config, "--run-dir", str(run_dir), "--format", "hdf5"]) == 0

    assert (run_dir / "reports" / "validation.json").exists()
    assert (run_dir / "reports" / "solver_readiness.json").exists()
    assert (run_dir / "reports" / "run_manifest.json").exists()
    assert (run_dir / "reports" / "qa_report.md").exists()
    assert (run_dir / "input" / "model.inp").exists()
    assert (run_dir / "dataset" / "sample.h5").exists()


def test_validate_refuses_to_overwrite_existing_run(
    tmp_path,
    multimodal_sample_config,
):
    from experiment_to_cpfe.cli import main

    run_dir = tmp_path / "offline-run"
    config = str(multimodal_sample_config)
    assert main(["validate", "--config", config, "--run-dir", str(run_dir)]) == 0
    manifest = (run_dir / "reports" / "run_manifest.json").read_bytes()

    assert main(["validate", "--config", config, "--run-dir", str(run_dir)]) == 1
    assert (run_dir / "reports" / "run_manifest.json").read_bytes() == manifest


def test_inspect_returns_manifest_summary(tmp_path, multimodal_sample_config, capsys):
    from experiment_to_cpfe.cli import main

    run_dir = tmp_path / "offline-run"
    config = str(multimodal_sample_config)
    assert main(["validate", "--config", config, "--run-dir", str(run_dir)]) == 0

    assert main(["inspect", "--run-dir", str(run_dir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stages"][-1]["stage"] == "validate"


def test_unknown_command_returns_usage_error():
    from experiment_to_cpfe.cli import main

    assert main(["not-a-command"]) == 2


def test_hdf5_export_merges_extracted_simulation_bundle(
    tmp_path,
    multimodal_sample_config,
):
    from experiment_to_cpfe.cli import main
    from experiment_to_cpfe.datasets.hdf5 import read_hdf5

    run_dir = tmp_path / "offline-run"
    config = str(multimodal_sample_config)
    assert main(["validate", "--config", config, "--run-dir", str(run_dir)]) == 0
    extracted = run_dir / "solver" / "extracted"
    shutil.copytree("tests/fixtures/odb_extract_fixture", extracted)

    assert main(["export", "--config", config, "--run-dir", str(run_dir), "--format", "hdf5"]) == 0
    restored = read_hdf5(run_dir / "dataset" / "sample.h5")

    assert "simulation_records" in restored.tables
    assert any(asset.source_kind.value == "simulated" for asset in restored.assets)
    assert any(source.kind.value == "simulated" for source in restored.metadata.sources)
