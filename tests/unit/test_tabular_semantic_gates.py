from pathlib import Path

import pytest

from experiment_to_cpfe.assets.models import SourceKind


@pytest.fixture
def tabular_config():
    from experiment_to_cpfe.config import load_pipeline_config
    return load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml"))


@pytest.mark.parametrize("units", [{"time": "s"}, {"increment_id": "1", "time": "s", "stress_33": "unknown", "strain_33": "1"}])
def test_all_mapped_table_fields_need_declared_units(tabular_config, units):
    from experiment_to_cpfe.adapters.tabular import load_tabular_source
    source = tabular_config.sources[0].model_copy(update={"units": units})
    with pytest.raises(ValueError, match="unit"):
        load_tabular_source(source)


@pytest.mark.parametrize("evidence", [SourceKind.MEASURED, SourceKind.INPUT, SourceKind.INFERRED])
def test_nonsimulated_table_cannot_enter_simulation_records(tabular_config, evidence):
    from experiment_to_cpfe.adapters.tabular import load_tabular_source
    source = tabular_config.sources[0].model_copy(update={"source_kind": evidence, "table_name": "simulation_records"})
    with pytest.raises(ValueError, match="simulated"):
        load_tabular_source(source)


def test_simulated_table_cannot_enter_measured_observations(tabular_config):
    from experiment_to_cpfe.adapters.tabular import load_tabular_source
    source = tabular_config.sources[0].model_copy(update={"source_kind": SourceKind.SIMULATED})
    with pytest.raises(ValueError, match="simulated"):
        load_tabular_source(source)


def test_input_observations_keep_explicit_row_source_and_survive_hdf5(tabular_config, tmp_path, validation_policy):
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.datasets.hdf5 import read_hdf5, write_hdf5
    from experiment_to_cpfe.schema.validation import validate_sample
    sample = assemble_sample(tabular_config)
    row = sample.tables["measured_observations"][0]
    source = next(asset for asset in sample.assets if asset.asset_id == row["source_asset_id"])
    assert row["source_kind"] == "input" == source.source_kind.value
    assert source.units["stress_33"] == "Pa"
    assert source.descriptive_metadata["table_name"] == "measured_observations"
    assert validate_sample(sample, validation_policy).passed
    output = tmp_path / "sample.h5"
    write_hdf5(sample, output)
    assert read_hdf5(output).tables == sample.tables


@pytest.mark.parametrize("mutation", ["wrong_kind", "unknown_source", "source_units", "source_table"])
def test_validation_rejects_broken_tabular_source_binding(tabular_config, validation_policy, mutation):
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.schema.validation import validate_sample
    sample = assemble_sample(tabular_config)
    row = sample.tables["measured_observations"][0]
    if mutation == "wrong_kind":
        row["source_kind"] = "simulated"
    elif mutation == "unknown_source":
        row["source_asset_id"] = "not-registered"
    elif mutation == "source_units":
        sample.assets = (sample.assets[0].model_copy(update={"units": {"time": "s"}}), *sample.assets[1:])
    else:
        sample.tables["simulation_records"] = sample.tables.pop("measured_observations")
    assert not validate_sample(sample, validation_policy).passed


def test_reserved_evidence_columns_cannot_override_binding(tabular_config):
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    original = tabular_config.sources[0]
    source = original.model_copy(update={"column_map": {**original.column_map, "source_asset_id": "increment"}, "units": {**original.units, "source_asset_id": "1"}})
    with pytest.raises(ValueError, match="reserved"):
        assemble_sample(tabular_config.model_copy(update={"sources": (source,)}))


def test_independent_observation_sources_keep_separate_time_and_increment_ids(tabular_config, validation_policy):
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.schema.validation import validate_sample
    source = tabular_config.sources[0]
    config = tabular_config.model_copy(update={"sources": (source, source)})
    sample = assemble_sample(config)
    assert validate_sample(sample, validation_policy).passed
    rows = sample.tables["measured_observations"]
    assert rows[0]["source_asset_id"] != rows[len(rows) // 2]["source_asset_id"]
