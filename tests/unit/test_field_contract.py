"""Behavioral tests for the shared ODB CSV record contract."""

import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def test_record_parser_types_positions_without_coercing_string_identifiers():
    from experiment_to_cpfe._resources.field_contract import parse_record
    row = parse_record({"step": "001", "component": "001", "instance": "009",
                        "frame": "0", "increment_number": "2", "frame_value": "0.5",
                        "frame_time": "", "element_label": "017", "node_label": "",
                        "integration_point": "3", "section_point": "2", "value": "1.25"})
    assert row["step"] == "001" and row["component"] == "001" and row["instance"] == "009"
    assert row["frame"] == 0 and type(row["frame"]) is int
    assert row["element_label"] == 17 and type(row["element_label"]) is int
    assert row["frame_value"] == 0.5 and type(row["frame_value"]) is float
    assert row["frame_time"] == "" and row["node_label"] == ""
    assert row["value"] == 1.25


@pytest.mark.parametrize("column,value", [("node_label", "1.5"), ("frame", "abc"), ("value", "bad"), ("value", "nan"), ("frame_time", "inf"), ("value", ""), ("frame", "")])
def test_record_parser_rejects_invalid_numeric_columns(column, value):
    from experiment_to_cpfe._resources.field_contract import parse_record
    with pytest.raises(ValueError, match=column):
        parse_record({column: value})


@pytest.mark.parametrize("key", ["step", "frame", "increment_id", "load_case", "field", "position", "instance", "element_label", "node_label", "integration_point", "section_point", "face", "component"])
def test_record_identity_preserves_each_location_dimension(key):
    from experiment_to_cpfe._resources.field_contract import record_identity
    first = {"step": "001", "frame": 0, "increment_id": "001:0", "load_case": "LC",
             "field": "S", "position": "ELEMENT_FACE", "instance": "PART-1",
             "element_label": 1, "node_label": "", "integration_point": "",
             "section_point": 1, "face": "FACE1", "component": "S11"}
    second = {**first, key: "different"}
    assert record_identity(first) != record_identity(second)
    assert record_identity(first) == record_identity({**first, "value": 999.0})


@pytest.mark.parametrize("column,value", [("element_label", "1.5"), ("value", "NaN"), ("frame_time", "Inf")])
def test_host_loader_rejects_invalid_numeric_values(tmp_path, column, value):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle
    target = tmp_path / "bundle"
    shutil.copytree("tests/fixtures/odb_extract_fixture", target)
    with (target / "frames.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    rows[0][column] = value
    with (target / "frames.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match=column):
        load_extraction_bundle(target)


def test_host_loader_rejects_unknown_explicit_field_contract(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle
    target = tmp_path / "bundle"
    shutil.copytree("tests/fixtures/odb_extract_fixture", target)
    metadata = json.loads((target / "metadata.json").read_text())
    metadata["field_contract_version"] = "999.0"
    (target / "metadata.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="field contract"):
        load_extraction_bundle(target)


def test_resource_script_help_works_without_site_packages(tmp_path):
    from experiment_to_cpfe import _resources
    source = Path(_resources.__file__).parent
    isolated = tmp_path / "resources"
    shutil.copytree(source, isolated, ignore=shutil.ignore_patterns("__pycache__"))
    result = subprocess.run([sys.executable, "-S", str(isolated / "abaqus_extract_odb.py"), "--help"], cwd=tmp_path, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "--max-records" in result.stdout
