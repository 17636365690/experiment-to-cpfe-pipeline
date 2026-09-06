from pathlib import Path
import subprocess
import sys
import json
import shutil


def test_host_loader_preserves_declared_non_si_units(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    target = tmp_path/'bundle'
    shutil.copytree('tests/fixtures/odb_extract_fixture', target)
    data = json.loads((target/'metadata.json').read_text())
    data['sample_metadata']['unit_system'] = {'length':'mm','stress':'MPa','time':'ms'}
    data['sample_metadata']['coordinate']['units'] = 'mm'
    data['field_units'] = {'S':'MPa','LE':'1'}
    (target/'metadata.json').write_text(json.dumps(data))
    sample = load_extraction_bundle(target)
    assert sample.assets[0].units['S'] == 'MPa'
    assert sample.metadata.unit_system['time'] == 'ms'


def test_host_loader_keeps_numeric_looking_labels_as_strings(tmp_path):
    import csv
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    target=tmp_path/'bundle'
    shutil.copytree('tests/fixtures/odb_extract_fixture',target)
    with (target/'frames.csv').open() as stream:
        rows=list(csv.DictReader(stream))
    rows[0]['step']='001'
    rows[0]['component']='001'
    with (target/'frames.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    sample=load_extraction_bundle(target)
    assert sample.tables['simulation_records'][0]['step']=='001'
    assert sample.tables['simulation_records'][0]['component']=='001'


def test_extraction_command_passes_explicit_record_limit(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.extraction import ExtractionRequest, build_abaqus_extraction_command

    request=ExtractionRequest(tmp_path/'job.odb',tmp_path/'out',('U',),'native',max_records=12)
    command=build_abaqus_extraction_command(request,('abaqus',))
    assert command[command.index('--max-records')+1]=='12'


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
