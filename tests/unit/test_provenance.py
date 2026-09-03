import json

import pytest


def test_sha256_file_matches_known_digest(tmp_path):
    from experiment_to_cpfe.provenance.hashing import sha256_file

    path = tmp_path / "input.txt"
    path.write_text("abc", encoding="utf-8")

    assert sha256_file(path) == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )


def test_run_directory_rejects_existing_nonempty_path(tmp_path):
    from experiment_to_cpfe.provenance.manifest import create_run_directory

    target = tmp_path / "synthetic-001" / "run-001"
    target.mkdir(parents=True)
    (target / "existing.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        create_run_directory(tmp_path, "synthetic-001", "run-001")


def test_run_directory_creates_fixed_stage_layout(tmp_path):
    from experiment_to_cpfe.provenance.manifest import create_run_directory

    run_dir = create_run_directory(tmp_path, "synthetic-001", "run-001")

    assert {path.name for path in run_dir.iterdir()} == {
        "input",
        "solver",
        "dataset",
        "reports",
    }


def test_manifest_records_config_and_artifact_hashes(tmp_path):
    from experiment_to_cpfe.provenance.manifest import (
        build_run_manifest,
        write_manifest,
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    config = tmp_path / "sample.yaml"
    config.write_text("sample: synthetic\n", encoding="utf-8")
    artifact = run_dir / "result.json"
    artifact.write_text("{}\n", encoding="utf-8")

    manifest = build_run_manifest(
        run_dir,
        config,
        [{"stage": "validate", "status": "completed", "artifacts": [str(artifact)]}],
    )
    output = run_dir / "manifest.json"
    write_manifest(manifest, output)
    restored = json.loads(output.read_text(encoding="utf-8"))

    assert len(restored["config_sha256"]) == 64
    assert len(restored["artifacts"][str(artifact)]["sha256"]) == 64
    assert restored["stages"][0]["status"] == "completed"
