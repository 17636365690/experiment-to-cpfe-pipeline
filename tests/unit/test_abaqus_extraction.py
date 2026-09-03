from pathlib import Path
import subprocess
import sys


def test_extraction_command_preserves_paths(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.extraction import (
        ExtractionRequest,
        build_abaqus_extraction_command,
    )

    request = ExtractionRequest(
        odb_path=tmp_path / "job.odb",
        output_dir=tmp_path / "extracted",
        fields=("S", "LE", "SDV"),
        position="integration_point",
    )
    command = build_abaqus_extraction_command(request, ("abaqus.bat",))
    text = " ".join(command)

    assert "job.odb" in text
    assert "extracted" in text
    assert "S,LE,SDV" in text


def test_host_loader_reports_missing_field_without_zero_fill():
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    sample = load_extraction_bundle(Path("tests/fixtures/odb_extract_fixture"))

    extraction = sample.solver_inputs["extraction"]
    assert extraction["missing_fields"] == ["STATEV"]
    assert "STATEV" not in sample.arrays
    assert sample.tables["simulation_records"][0]["field"] == "S"


def test_extraction_bundle_completeness_lists_missing_files(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.extraction import (
        extraction_bundle_is_complete,
    )

    complete, missing = extraction_bundle_is_complete(tmp_path)

    assert not complete
    assert set(missing) == {"metadata.json", "frames.csv"}


def test_abaqus_script_help_runs_without_odbaccess():
    completed = subprocess.run(
        [sys.executable, "scripts/abaqus_extract_odb.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--odb" in completed.stdout
