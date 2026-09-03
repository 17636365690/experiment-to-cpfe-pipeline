import json


def test_sample_json_round_trip(tmp_path, make_sample):
    from experiment_to_cpfe.schema.io import dump_sample_json, load_sample_json

    source = make_sample()
    output = tmp_path / "sample.json"

    dump_sample_json(source, output)
    restored = load_sample_json(output)

    assert restored.metadata.sample_id == source.metadata.sample_id
    assert restored.metadata.tensor_order == source.metadata.tensor_order
    assert restored.tables == source.tables
    assert restored.arrays["demo"].tolist() == [1.0, 2.0]


def test_sample_json_round_trip_preserves_dtype_and_evidence_kind(
    tmp_path,
    make_sample,
):
    from experiment_to_cpfe.assets.models import SourceKind
    from experiment_to_cpfe.schema.io import dump_sample_json, load_sample_json

    output = tmp_path / "sample.json"
    dump_sample_json(make_sample(), output)

    restored = load_sample_json(output)

    assert restored.arrays["demo"].dtype.name == "float64"
    assert restored.metadata.sources[0].kind is SourceKind.MEASURED
    assert restored.assets[0].source_kind is SourceKind.MEASURED


def test_sample_json_uses_explicit_array_shape(tmp_path, make_sample):
    from experiment_to_cpfe.schema.io import dump_sample_json

    output = tmp_path / "sample.json"
    dump_sample_json(make_sample(), output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["arrays"]["demo"]["shape"] == [2]
    assert payload["arrays"]["demo"]["dtype"] == "float64"


def test_sample_json_round_trip_preserves_solver_inputs(tmp_path, make_sample):
    from experiment_to_cpfe.schema.io import dump_sample_json, load_sample_json
    from experiment_to_cpfe.schema.models import SamplePackage

    source = make_sample()
    source = SamplePackage(
        metadata=source.metadata,
        tables=source.tables,
        arrays=source.arrays,
        assets=source.assets,
        solver_inputs={"material_model": "synthetic_cp"},
    )
    output = tmp_path / "sample.json"

    dump_sample_json(source, output)
    restored = load_sample_json(output)

    assert restored.solver_inputs == {"material_model": "synthetic_cp"}
