import json
from pathlib import Path
import shutil
import sys
import yaml


def native_config(tmp_path, multimodal_sample_config):
    payload = yaml.safe_load(multimodal_sample_config.read_text())
    root = tmp_path / "native-source"
    (root / "Example").mkdir(parents=True)
    (root / "Input").mkdir()
    (root / "Example/main.inp").write_text("*Include, input=../Input/model.inp\n")
    replacements = payload["solver_inputs"]["inp_replacements"]
    (root / "Input/model.inp").write_text("*Heading\nsynthetic native\n" + "\n".join(
        replacements[key] for key in ("NODES", "ELEMENTS", "MATERIALS", "BOUNDARY_CONDITIONS", "OUTPUT_REQUESTS")) + "\n")
    payload["abaqus"]["template_path"] = None
    payload["abaqus"]["input_bundle"] = {
        "source_root": str(root), "entrypoint": "Example/main.inp",
        "submission_dir": "Example", "license": "synthetic",
    }
    payload["abaqus"]["command"] = [sys.executable, str(Path("tests/fixtures/fake_solver.py").resolve())]
    multimodal_sample_config.write_text(yaml.safe_dump(payload))
    return multimodal_sample_config, root


def test_native_bundle_build_stages_all_includes_and_records_assets(tmp_path, multimodal_sample_config):
    from experiment_to_cpfe import pipeline

    config, root = native_config(tmp_path, multimodal_sample_config)
    run = tmp_path / "run"
    assert pipeline.run_validate(config, run)["status"] == "completed"
    result = pipeline.run_build_inp(config, run)

    assert result["status"] == "completed"
    staged = run / "input/native_bundle"
    assert (staged / "Example/main.inp").is_file()
    assert (staged / "Input/model.inp").is_file()
    receipt = json.loads((staged / ".pipeline-bundle-manifest.json").read_text())
    assert receipt["entrypoint"] == "Example/main.inp"
    assert len(receipt["include_edges"]) == 1
    manifest = json.loads((run / "reports/run_manifest.json").read_text())
    record = next(stage for stage in manifest["stages"] if stage["stage"] == "build-inp")
    assert any(path.endswith(".pipeline-bundle-manifest.json") for path in record["artifacts"])


def test_native_bundle_runner_copies_relative_include_tree(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.bundle import stage_input_bundle
    from experiment_to_cpfe.solvers.abaqus.runner import AbaqusRunRequest, SolverStage, run_abaqus

    source = tmp_path / "source"
    (source / "Example").mkdir(parents=True)
    (source / "Input").mkdir()
    (source / "Example/main.inp").write_text("*Include, input=../Input/model.inp\n")
    (source / "Input/model.inp").write_text("*Node\n1,0,0,0\n")
    staged = tmp_path / "staged"
    bundle = stage_input_bundle(
        source / "Example/main.inp", source_root=source,
        submission_dir=source / "Example", destination=staged,
        license="synthetic",
    )
    stage_dir = tmp_path / "solver"
    result = run_abaqus(AbaqusRunRequest(
        abaqus_command=(sys.executable, str(Path("tests/fixtures/fake_solver.py").resolve())),
        job_name="native", inp_path=bundle.entrypoint,
        work_dir=stage_dir / "Example", stage=SolverStage.ANALYSIS,
        user_subroutine=None, cpus=1, timeout_seconds=10,
        input_bundle_root=staged, input_bundle_manifest=bundle.manifest_path,
    ))
    assert result.status == "completed"
    assert (stage_dir / "Example/main.inp").read_bytes() == (source / "Example/main.inp").read_bytes()
    assert (stage_dir / "Input/model.inp").read_bytes() == (source / "Input/model.inp").read_bytes()
    assert result.command[result.command.index("input=main.inp")] == "input=main.inp"


def test_native_bundle_inputs_are_locked_recursively(tmp_path, multimodal_sample_config):
    from experiment_to_cpfe import pipeline

    config, root = native_config(tmp_path, multimodal_sample_config)
    run = tmp_path / "run"
    assert pipeline.run_validate(config, run)["status"] == "completed"
    lock = json.loads((run / "input/input_lock.json").read_text())
    assert str((root / "Example/main.inp").resolve()) in lock["files"]
    assert str((root / "Input/model.inp").resolve()) in lock["files"]
    (root / "Input/model.inp").write_text("changed\n")
    assert pipeline.run_build_inp(config, run)["status"] == "blocked"


def test_stage_input_bundle_is_available_as_explicit_cli_stage(tmp_path, multimodal_sample_config):
    from experiment_to_cpfe import pipeline
    from experiment_to_cpfe.cli import main

    config, root = native_config(tmp_path, multimodal_sample_config)
    run = tmp_path / "run"
    assert pipeline.run_validate(config, run)["status"] == "completed"
    assert main(["stage-input-bundle", "--config", str(config), "--run-dir", str(run)]) == 0
    assert (run / "input/native_bundle/.pipeline-bundle-manifest.json").is_file()
    # Build-inp reuses the staged bundle instead of attempting a second copy.
    assert pipeline.run_build_inp(config, run)["status"] == "completed"


def test_native_lock_excludes_unreferenced_files(tmp_path, multimodal_sample_config):
    from experiment_to_cpfe import pipeline
    config, root = native_config(tmp_path, multimodal_sample_config)
    unrelated = root / "unrelated.txt"
    unrelated.write_text("unrelated original")
    run = tmp_path / "run"
    pipeline.run_validate(config, run)
    lock = json.loads((run / "input/input_lock.json").read_text())
    assert str(unrelated.resolve()) not in lock["files"]


def test_tampered_explicit_stage_is_not_reused(tmp_path, multimodal_sample_config):
    from experiment_to_cpfe import pipeline
    config, root = native_config(tmp_path, multimodal_sample_config)
    run = tmp_path / "run"
    pipeline.run_validate(config, run)
    pipeline.run_stage_input_bundle(config, run)
    (run / "input/native_bundle/Input/model.inp").write_text("tampered")
    assert pipeline.run_build_inp(config, run)["status"] == "blocked"


def test_native_runner_uses_deep_submission_directory(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.bundle import stage_input_bundle
    from experiment_to_cpfe.solvers.abaqus.runner import AbaqusRunRequest, SolverStage, run_abaqus
    source = tmp_path / "source"
    submit = source / "deep/Example"
    submit.mkdir(parents=True)
    (source / "mesh.inp").write_text("*Node\n1,0,0,0\n")
    (submit / "main.inp").write_text("*Include,input=../../mesh.inp\n")
    staged = tmp_path / "staged"
    bundle = stage_input_bundle(submit / "main.inp", source_root=source, submission_dir=submit, destination=staged, license="synthetic")
    request = AbaqusRunRequest((sys.executable,str(Path('tests/fixtures/fake_solver.py').resolve())),
        'nested',bundle.entrypoint,tmp_path/'solver/deep/Example',SolverStage.DATACHECK,None,1,10,
        input_bundle_root=staged,input_bundle_manifest=bundle.manifest_path)
    result = run_abaqus(request)
    assert result.status == 'completed'
    assert (tmp_path/'solver/mesh.inp').read_bytes() == (source/'mesh.inp').read_bytes()
    assert (tmp_path/'solver/deep/Example/main.inp').is_file()
