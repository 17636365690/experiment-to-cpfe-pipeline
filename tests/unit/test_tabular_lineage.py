"""Logical table conversion receipts remain bound to their own source rows."""

import hashlib
import json
from pathlib import Path

import h5py
import pytest


@pytest.fixture
def lineage_sample():
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.config import load_pipeline_config
    return assemble_sample(load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml")))


def test_table_hash_has_documented_encoding_and_order_sensitivity():
    from experiment_to_cpfe.assets.registry import table_payload_sha256
    rows = [{"name": "晶粒", "value": 2.0}, {"name": "002", "value": 3}]
    expected = hashlib.sha256('normalized-table-json-v1\0[{"name":"晶粒","value":2.0},{"name":"002","value":3}]'.encode("utf-8")).hexdigest()
    assert table_payload_sha256(rows) == expected
    assert table_payload_sha256([{"value": 2.0, "name": "晶粒"}, {"value": 3, "name": "002"}]) == expected
    assert table_payload_sha256(list(reversed(rows))) != expected


def test_tabular_children_retain_raw_parent_hash_and_conversion_loss(lineage_sample):
    from experiment_to_cpfe.assets.registry import table_payload_sha256
    children = [asset for asset in lineage_sample.assets if asset.format == "normalized-table-json"]
    assert len(children) == 2
    for child in children:
        parent = next(asset for asset in lineage_sample.assets if asset.asset_id == child.parent_asset_id)
        selected = [row for row in lineage_sample.tables[child.descriptive_metadata["table_key"]] if row["source_asset_id"] == parent.asset_id]
        assert child.layer.value == "curated" and parent.layer.value == "raw"
        assert child.source_kind == parent.source_kind
        assert child.conversion.source_sha256 == parent.sha256
        assert child.conversion.target_file_hashes == {}
        assert child.conversion.hash_scope == "logical_payload"
        assert child.sha256 == child.conversion.target_payload_sha256 == table_payload_sha256(selected)
        assert child.descriptive_metadata["row_source_asset_id"] == parent.asset_id
        assert "table_name" not in child.descriptive_metadata
        assert child.lossy_transformations
        assert parent.lossy_transformations == ()


def test_multiple_sources_in_one_table_have_independent_child_receipts(tmp_path):
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.datasets.hdf5 import read_hdf5, write_hdf5
    config = load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml"))
    config = config.model_copy(update={"sources": (config.sources[0], config.sources[0])})
    sample = assemble_sample(config)
    children = [asset for asset in sample.assets if asset.format == "normalized-table-json"]
    assert len(children) == 2
    assert children[0].sha256 != children[1].sha256  # bound source IDs differ
    target = tmp_path / "sample.h5"
    write_hdf5(sample, target)
    restored = read_hdf5(target)
    assert restored.tables == sample.tables
    assert [asset.sha256 for asset in restored.assets] == [asset.sha256 for asset in sample.assets]


@pytest.mark.parametrize("mutation", ["value", "source_selector", "row_removed", "row_order"])
def test_hdf5_writer_rejects_changed_normalized_table_before_creating_output(lineage_sample, tmp_path, mutation):
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5
    rows = lineage_sample.tables["measured_observations"]
    if mutation == "value":
        rows[0]["stress_33"] = 999.0
    elif mutation == "source_selector":
        rows[0]["source_asset_id"] = "other-source"
    elif mutation == "row_removed":
        rows.pop()
    else:
        rows.reverse()
    output = tmp_path / "must-not-exist.h5"
    with pytest.raises(ValueError, match="table.*hash|table.*payload"):
        write_hdf5(lineage_sample, output)
    assert not output.exists()


def test_hdf5_reader_rejects_tampered_table_records(lineage_sample, tmp_path):
    from experiment_to_cpfe.datasets.hdf5 import read_hdf5, write_hdf5
    target = tmp_path / "sample.h5"
    write_hdf5(lineage_sample, target)
    with h5py.File(target, "r+") as handle:
        dataset = handle["measured/measured_observations/records_json"]
        rows = json.loads(dataset.asstr()[()])
        rows[0]["stress_33"] = 99.0
        dataset[()] = json.dumps(rows)
    with pytest.raises(ValueError, match="table.*hash|table.*payload"):
        read_hdf5(target)
