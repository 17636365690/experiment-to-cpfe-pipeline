import json
from pathlib import Path


def test_tabular_adapter_does_not_guess_units():
    from experiment_to_cpfe.adapters.tabular import load_tabular_source
    from experiment_to_cpfe.config import load_pipeline_config

    config = load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml"))
    rows = load_tabular_source(config.sources[0])

    assert rows[0]["increment_id"] == "i0"
    assert rows[0]["stress_33"] == 0.0
    assert "unit" not in rows[0]


def test_assemble_sample_preserves_tables_and_evidence():
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.assets.models import SourceKind
    from experiment_to_cpfe.config import load_pipeline_config

    config = load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml"))
    sample = assemble_sample(config)

    assert set(sample.tables) == {"measured_observations", "grains"}
    assert sample.metadata.sources[0].kind is SourceKind.MEASURED
    tabular_assets = [
        asset for asset in sample.assets if asset.asset_id.startswith("asset-source-")
    ]
    assert {asset.source_kind for asset in tabular_assets} == {SourceKind.MEASURED}
    assert any(asset.source_kind is SourceKind.INPUT for asset in sample.assets)


def test_txt_adapter_uses_explicit_delimiter_and_column_map(tmp_path):
    from experiment_to_cpfe.assets.models import AssetKind, SourceKind
    from experiment_to_cpfe.config import TabularSourceConfig
    from experiment_to_cpfe.adapters.tabular import load_tabular_source

    path = tmp_path / "curve.txt"
    path.write_text("step;load\ni0;1.5\n", encoding="utf-8")
    config = TabularSourceConfig(
        path=path,
        table_name="load_history",
        source_kind=SourceKind.MEASURED,
        modality=AssetKind.TIME_SERIES,
        format="txt",
        delimiter=";",
        encoding="utf-8",
        column_map={"increment_id": "step", "force": "load"},
        units={"force": "N", "increment_id": "1"},
        coordinate_frame="sample",
        axis_order=("time",),
        native_layout="semicolon_columns",
        license="synthetic",
    )

    assert load_tabular_source(config) == [
        {"increment_id": "i0", "force": 1.5}
    ]


def test_json_adapter_reads_record_array(tmp_path):
    from experiment_to_cpfe.assets.models import AssetKind, SourceKind
    from experiment_to_cpfe.config import TabularSourceConfig
    from experiment_to_cpfe.adapters.tabular import load_tabular_source

    path = tmp_path / "curve.json"
    path.write_text(
        json.dumps([{"step": "i0", "temperature": 293.15}]),
        encoding="utf-8",
    )
    config = TabularSourceConfig(
        path=path,
        table_name="load_history",
        source_kind=SourceKind.INPUT,
        modality=AssetKind.TIME_SERIES,
        format="json",
        delimiter=None,
        encoding="utf-8",
        column_map={"increment_id": "step", "temperature": "temperature"},
        units={"increment_id": "1", "temperature": "K"},
        coordinate_frame="sample",
        axis_order=("time",),
        native_layout="json_records",
        license="synthetic",
    )

    assert load_tabular_source(config) == [
        {"increment_id": "i0", "temperature": 293.15}
    ]
