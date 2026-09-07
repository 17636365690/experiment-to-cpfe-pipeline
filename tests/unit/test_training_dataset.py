"""Checks selection errors that otherwise silently change regression semantics."""

import copy
import json
import hashlib
from pathlib import Path

import h5py
import numpy as np
import pytest

from training_fixtures import training_collection, replace_sample


def build(config, root):
    from experiment_to_cpfe.datasets.training import build_training_dataset
    return build_training_dataset(config, base_dir=root)


@pytest.mark.parametrize("layout", ["table", "array"])
def test_columns_align_by_identity_convert_units_and_retain_sources(tmp_path, make_sample, layout):
    config, _ = training_collection(tmp_path, make_sample, layout)
    data = build(config, tmp_path)
    assert data.features[:2].tolist() == [[0., 1.], [.25, 1.]]
    assert data.targets[:5].tolist() == [0., .25, .5, .75, 1.]
    assert data.groups.tolist() == list(np.repeat(list("abcd"), 5))
    assert data.sample_ids.tolist() == data.groups.tolist()
    assert json.loads(data.row_ids[0]) == ["r0"]
    assert data.metadata["features"] == config["features"]
    source = data.metadata["sources"][0]
    assert source["sample_metadata"]["sample_id"] == "a"
    assert source["source_manifest"]["generator"] == "synthetic product"
    assert source["assets"][0]["source_kind"] == "input"
    assert source["assets"][0]["license"] == "Apache-2.0"
    assert source["columns"]["stress"]["source_rows"] == ([9, 8, 7, 6, 5] if layout == "table" else [4, 3, 2, 1, 0])
    assert source["columns"]["stress"]["selector"]["conversion"]["factor"] == 1000
    assert len(source["hdf5_sha256"]) == 64


def test_one_row_selection_applies_after_key_alignment(tmp_path, make_sample):
    config, _ = training_collection(tmp_path, make_sample)
    config["layouts"]["table"]["rows"] = {"start": 1, "stop": 5, "step": 2}
    data = build(config, tmp_path)
    assert data.features[:2, 0].tolist() == [.25, .75]
    assert data.targets[:2].tolist() == [.25, .75]
    assert data.metadata["sources"][0]["columns"]["stress"]["source_rows"] == [8, 6]


@pytest.mark.parametrize("key,value", [("version", 2), ("typo", 1), ("features", []), ("grouping_evidence", ""), ("group_by", "random")])
def test_bad_configuration_rejected(tmp_path, make_sample, key, value):
    config, _ = training_collection(tmp_path, make_sample)
    config[key] = value
    with pytest.raises(ValueError):
        build(config, tmp_path)


@pytest.mark.parametrize("mutation,match", [
    ("duplicate_sample", "duplicate.*sample"), ("expected_sample", "sample.*wrong"),
    ("group_split", "group.*train.*test"), ("root_reuse", "target.*source.*split"),
    ("declared_split", "dataset_split"), ("foreign", "canonical HDF5"),
])
def test_collection_identity_and_split_conflicts(tmp_path, make_sample, mutation, match):
    config, samples = training_collection(tmp_path, make_sample)
    if mutation == "duplicate_sample":
        config["inputs"].append(copy.deepcopy(config["inputs"][0]))
    elif mutation == "expected_sample":
        config["inputs"][0]["sample_id"] = "wrong"
    elif mutation == "group_split":
        config["group_by"] = "explicit"
        for item in config["inputs"]:
            item["group_id"] = "shared" if item["sample_id"] in "ad" else item["sample_id"]
    elif mutation == "root_reuse":
        samples[3].assets = samples[0].assets
        replace_sample(tmp_path, samples[3])
    elif mutation == "declared_split":
        samples[0].solver_inputs["dataset_split"] = "test"
        replace_sample(tmp_path, samples[0])
    else:
        with h5py.File(tmp_path / "a.h5", "w") as handle:
            handle["vendor_data"] = [1, 2]
    with pytest.raises(ValueError, match=match):
        build(config, tmp_path)


@pytest.mark.parametrize("mutation,match", [
    ("missing_column", "a.*stress.*load"), ("unit", "a.*stress.*unit"),
    ("missing_asset", "a.*stress.*source"), ("evidence", "a.*stress.*source_kind"),
    ("nonfinite", "a.*stress.*finite"), ("text", "a.*stress.*real"),
    ("duplicate_id", "a.*stress.*duplicate.*identity"), ("missing_id", "a.*stress.*align"),
])
def test_table_errors_identify_sample_and_field(tmp_path, make_sample, mutation, match):
    config, samples = training_collection(tmp_path, make_sample)
    rows = samples[0].tables["measured_observations"]
    row = rows[-1]
    if mutation == "missing_column": del row["load"]
    elif mutation == "unit":
        samples[0].assets = (samples[0].assets[0].model_copy(update={"units": {"eps": "1", "modulus": "Pa", "load": "Pa"}}),)
    elif mutation == "missing_asset": row["source_asset_id"] = "missing"
    elif mutation == "evidence": row["source_kind"] = "measured"
    elif mutation == "nonfinite": row["load"] = float("nan")
    elif mutation == "text": row["load"] = "0"
    elif mutation == "duplicate_id": row["increment_id"] = rows[-2]["increment_id"]
    else: rows.pop()
    replace_sample(tmp_path, samples[0])
    with pytest.raises(ValueError, match=match): build(config, tmp_path)


@pytest.mark.parametrize("mutation,match", [
    ("axis", "a.*strain.*axis"), ("component", "a.*strain.*component"),
    ("length", "a.*strain.*identity"), ("id_duplicate", "a.*stress.*duplicate.*identity"),
    ("unit_key", "a.*stress.*unit"), ("binding", "a.*strain.*array_key"),
])
def test_array_layout_errors_are_not_flattened_or_truncated(tmp_path, make_sample, mutation, match):
    config, samples = training_collection(tmp_path, make_sample, "array")
    columns = config["layouts"]["array"]["columns"]
    if mutation == "axis": columns["strain"]["row_axis"] = 3
    elif mutation == "component": columns["strain"]["component"] = [9]
    elif mutation == "length": samples[0].arrays["ids"] = np.array(["only"])
    elif mutation == "id_duplicate": samples[0].arrays["response_ids"][:] = "same"
    elif mutation == "unit_key": columns["stress"]["unit_key"] = "unknown"
    else: columns["strain"]["asset_id"] = "response"
    if mutation in {"length", "id_duplicate"}: replace_sample(tmp_path, samples[0])
    with pytest.raises(ValueError, match=match): build(config, tmp_path)


@pytest.mark.parametrize("change", [
    {"source_unit": "unknown"}, {"conversion": None},
    {"conversion": {"factor": 0, "reason": "bad"}},
    {"conversion": {"factor": float("inf"), "reason": "bad"}},
    {"conversion": {"factor": 1000, "reason": ""}},
])
def test_unresolved_or_implicit_conversion_is_rejected(tmp_path, make_sample, change):
    config, _ = training_collection(tmp_path, make_sample)
    config["layouts"]["table"]["columns"]["stress"].update(change)
    with pytest.raises(ValueError): build(config, tmp_path)


def test_experiment_grouping_allows_multiple_samples_in_one_split(tmp_path, make_sample):
    config, samples = training_collection(tmp_path, make_sample)
    config["group_by"] = "experiment_id"
    samples[1].metadata.experiment_id = "experiment-a"
    replace_sample(tmp_path, samples[1])
    data = build(config, tmp_path)
    assert data.groups[:10].tolist() == ["experiment-a"] * 10
    assert data.metadata["group_splits"] == {"experiment-a": "train", "experiment-c": "validation", "experiment-d": "test"}


def test_native_entity_axis_and_component_units_follow_registered_meaning(tmp_path, make_sample):
    from experiment_to_cpfe.assets.models import AssetKind
    config, samples = training_collection(tmp_path, make_sample, "array")
    for sample in samples:
        feature = sample.assets[1]
        meaning = {"quantity": "synthetic channels", "role": "features", "unit": None,
                   "component_units": {"eps": "1", "modulus": "Pa"},
                   "axes": ["component", "row"], "components": {"component": ["eps", "modulus"]},
                   "source_kind": "input", "evidence": "synthetic indexed generator",
                   "entity_ids": "ids", "entity_axis": 1, "identity_scope": "case increments"}
        ids_asset = sample.assets[2].model_copy(update={
            "asset_id": "ids-asset", "modality": AssetKind.TABLE, "shape": sample.arrays["ids"].shape,
            "units": {"ids": "1"}, "axis_order": ("row",), "coordinate_frame": None,
            "descriptive_metadata": {"array_key": "ids", "meaning": {
                "quantity": "increment identity", "role": "id", "unit": "1", "axes": ["row"],
                "identity_scope": "case increments", "source_kind": "input", "evidence": "synthetic IDs"}}})
        feature = feature.model_copy(update={"modality": AssetKind.TABLE, "coordinate_frame": None, "units": {"eps": "1", "modulus": "Pa"},
            "descriptive_metadata": {"array_key": "channels", "meaning": meaning}})
        sample.assets = (sample.assets[0], feature, sample.assets[2], ids_asset)
        replace_sample(tmp_path, sample)
    assert build(config, tmp_path).features[:2].tolist() == [[0., 1.], [.25, 1.]]
    config["layouts"]["array"]["columns"]["strain"]["unit_key"] = "modulus"
    config["layouts"]["array"]["columns"]["strain"]["source_unit"] = "Pa"
    config["features"][0]["unit"] = "Pa"
    with pytest.raises(ValueError, match="component"):
        build(config, tmp_path)


@pytest.mark.parametrize("rows", [{"start": 8}, {"stop": 8}, {"start": 2, "stop": 2}, {"step": 0}])
def test_empty_or_out_of_range_selection_is_explicit(tmp_path, make_sample, rows):
    config, _ = training_collection(tmp_path, make_sample)
    config["layouts"]["table"]["rows"] = rows
    with pytest.raises(ValueError, match="row|step"):
        build(config, tmp_path)


def test_table_uses_normalized_units_after_upstream_conversion(tmp_path, make_sample):
    config, samples = training_collection(tmp_path, make_sample)
    for sample in samples:
        asset = sample.assets[0]
        sample.assets = (asset.model_copy(update={"units": {"eps": "%", "modulus": "Pa", "load": "N"},
            "descriptive_metadata": {"normalized_units": {"eps": "1", "modulus": "Pa", "load": "kPa"}}}),)
        replace_sample(tmp_path, sample)
    assert build(config, tmp_path).targets[:2].tolist() == [0., .25]


def test_existing_target_group_and_split_cannot_be_reassigned(tmp_path, make_sample):
    config, samples = training_collection(tmp_path, make_sample, "array")
    sample = samples[0]
    asset = sample.assets[2]
    meaning = {"quantity": "response", "role": "target", "unit": "kPa", "axes": ["row"],
               "source_kind": "input", "evidence": "synthetic generator", "group_id": "a", "split": "train",
               "target_origin": "synthetic formula"}
    target = asset.model_copy(update={"coordinate_frame": None, "units": {"response": "kPa"},
        "descriptive_metadata": {"array_key": "response", "meaning": meaning}})
    sample.assets = (sample.assets[0], sample.assets[1], target)
    replace_sample(tmp_path, sample)
    config["layouts"]["array"]["columns"]["stress"]["unit_key"] = "response"
    # Reassigning just this sample must fail against its registered target meaning.
    config["inputs"][0]["split"] = "validation"
    with pytest.raises(ValueError, match="a.*target.*group/split"):
        build(config, tmp_path)


def test_existing_odb_extraction_tables_use_explicit_asset_binding(tmp_path):
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle
    metadata = json.loads(Path("tests/fixtures/odb_extract_fixture/metadata.json").read_text())
    config = {"version": 1, "features": [{"name": "strain", "unit": "1"}],
              "target": {"name": "stress", "unit": "MPa"}, "group_by": "sample_id",
              "grouping_evidence": "independent synthetic extraction fixtures", "inputs": [], "layouts": {}}
    for name, split in zip("abc", ("train", "validation", "test")):
        folder = tmp_path / name
        folder.mkdir()
        metadata["sample_metadata"]["sample_id"] = name
        metadata["odb_path"] = str(folder / "synthetic-unavailable.odb")
        metadata["odb_sha256"] = hashlib.sha256(name.encode()).hexdigest()
        metadata["field_units"] = {"E": "1", "S": "MPa"}
        (folder / "metadata.json").write_text(json.dumps(metadata))
        (folder / "frames.csv").write_text(
            "step,frame,frame_time,increment_id,field,element_label,integration_point,component,value\n"
            "Step-1,0,0,i0,E,1,1,E11,0\nStep-1,1,1,i1,E,1,1,E11,0.001\n"
            "Step-1,1,1,i1,S,1,1,S11,1\nStep-1,0,0,i0,S,1,1,S11,0\n")
        sample = load_extraction_bundle(folder)
        write_hdf5(sample, tmp_path / f"{name}.h5")
        asset = next(asset for asset in sample.assets if asset.format == "odb-extraction-bundle")
        config["layouts"][name] = {"alignment_evidence": "same field location in each frame", "columns": {
            key: {"kind": "table", "table": "simulation_records", "column": "value", "asset_id": asset.asset_id,
                  "id_columns": ["step", "frame", "element_label", "integration_point"], "source_unit": unit,
                  "where": {"field": field, "component": field + "11"}}
            for key, field, unit in (("strain", "E", "1"), ("stress", "S", "MPa"))}}
        config["inputs"].append({"path": f"{name}.h5", "sample_id": name, "layout": name, "split": split})
    data = build(config, tmp_path)
    assert data.features[:2].tolist() == [[0.], [.001]]
    assert data.targets[:2].tolist() == [0., 1.]
    assert data.metadata["sources"][0]["columns"]["stress"]["source_rows"] == [3, 2]


def test_multiple_layouts_can_share_one_quantity_contract(tmp_path, make_sample):
    table, _ = training_collection(tmp_path / "table", make_sample)
    array, _ = training_collection(tmp_path / "array", make_sample, "array")
    table["layouts"].update(array["layouts"])
    table["inputs"] = [dict(item, path="table/"+item["path"]) for item in table["inputs"][:2]] + [
        dict(item, path="array/"+item["path"]) for item in array["inputs"][2:]]
    data = build(table, tmp_path)
    assert data.targets[10:15].tolist() == [0., .375, .75, 1.125, 1.5]


@pytest.mark.parametrize("without_digest", [0, 3])
def test_target_source_uri_matches_across_partial_hash_records(tmp_path, make_sample, without_digest):
    config, samples = training_collection(tmp_path, make_sample)
    source = samples[0].assets[0]
    samples[3].assets = (source,)
    samples[without_digest].assets = (source.model_copy(update={"sha256": None}),)
    replace_sample(tmp_path, samples[0])
    replace_sample(tmp_path, samples[3])
    with pytest.raises(ValueError, match="target source.*splits"):
        build(config, tmp_path)


def test_table_can_explicitly_bind_a_renamed_column_to_its_unit_key(tmp_path, make_sample):
    config, samples = training_collection(tmp_path, make_sample)
    for sample in samples:
        for row in sample.tables["measured_observations"]:
            row["response"] = row.pop("load")
        replace_sample(tmp_path, sample)
    config["layouts"]["table"]["columns"]["stress"].update(column="response", unit_key="load")
    data = build(config, tmp_path)
    assert data.targets[:2].tolist() == [0., .25]
    assert data.metadata["sources"][0]["columns"]["stress"]["selector"]["unit_key"] == "load"


def test_unit_alias_cannot_override_the_selected_columns_existing_unit(tmp_path, make_sample):
    config, samples = training_collection(tmp_path, make_sample)
    sample = samples[0]
    units = dict(sample.assets[0].units, misleading="Pa")
    sample.assets = (sample.assets[0].model_copy(update={"units": units}),)
    replace_sample(tmp_path, sample)
    config["layouts"]["table"]["columns"]["stress"].update(unit_key="misleading", source_unit="Pa", conversion=None)
    with pytest.raises(ValueError, match="a.*stress.*unit"):
        build(config, tmp_path)
