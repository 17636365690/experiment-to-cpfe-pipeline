import numpy as np
import pytest


def test_synthetic_sample_passes_validation(make_sample, validation_policy):
    from experiment_to_cpfe.schema.validation import validate_sample

    report = validate_sample(make_sample(), validation_policy)

    assert report.passed
    assert report.errors == ()


def test_missing_units_is_an_error(make_sample, validation_policy):
    from experiment_to_cpfe.schema.validation import validate_sample

    sample = make_sample()
    sample.metadata = sample.metadata.model_copy(update={"unit_system": {}})

    report = validate_sample(sample, validation_policy)

    assert not report.passed
    assert any(issue.code == "MISSING_UNIT" for issue in report.errors)


def test_placeholder_unit_is_a_validation_error(make_sample, validation_policy):
    from experiment_to_cpfe.schema.validation import validate_sample

    sample = make_sample()
    sample.metadata.unit_system["stress"] = "unknown"
    report = validate_sample(sample, validation_policy)
    assert not report.passed
    assert any(issue.code == "MISSING_UNIT" for issue in report.errors)


def test_multiple_field_locations_in_one_increment_are_not_duplicate_increments(make_sample, validation_policy):
    from experiment_to_cpfe.schema.validation import validate_sample

    sample=make_sample()
    sample.tables['simulation_records']=[
        {'increment_id':'i0','field':'S','component':'S11','element_label':1,'value':3.0},
        {'increment_id':'i0','field':'S','component':'S11','element_label':2,'value':4.0},
    ]
    assert validate_sample(sample,validation_policy).passed


def test_duplicate_field_location_component_is_rejected(make_sample, validation_policy):
    from experiment_to_cpfe.schema.validation import validate_sample

    sample=make_sample()
    sample.tables['simulation_records']=[{'increment_id':'i0','field':'S','component':'S11','element_label':1,'value':3.0}]*2
    assert any(i.code=='DUPLICATE_FIELD_RECORD' for i in validate_sample(sample,validation_policy).errors)


def test_nonfinite_array_is_an_error(make_sample, validation_policy):
    from experiment_to_cpfe.schema.validation import validate_sample

    sample = make_sample()
    sample.arrays["demo"] = np.array([1.0, np.nan])

    report = validate_sample(sample, validation_policy)

    assert any(issue.code == "NONFINITE_VALUE" for issue in report.errors)


def test_grain_to_mesh_mapping_rejects_unknown_grain(make_sample, validation_policy):
    from experiment_to_cpfe.schema.validation import validate_sample

    sample = make_sample()
    sample.tables["grains"] = [{"grain_id": 1}]
    sample.tables["mesh_elements"] = [{"element_id": 10, "grain_id": 2}]

    report = validate_sample(sample, validation_policy)

    assert any(issue.code == "UNKNOWN_GRAIN_ID" for issue in report.errors)


def test_coordinate_mismatch_requires_recorded_transform(make_sample, validation_policy):
    from experiment_to_cpfe.assets.models import AssetRef
    from experiment_to_cpfe.schema.validation import validate_sample

    sample = make_sample()
    asset = sample.assets[0].model_copy(
        update={"coordinate_frame": "dic-camera"}
    )
    sample.assets = (AssetRef.model_validate(asset),)

    report = validate_sample(sample, validation_policy)

    assert any(issue.code == "REGISTRATION_REQUIRED" for issue in report.errors)


def test_curve_only_sample_is_not_solver_ready(make_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness

    readiness = check_solver_readiness(make_sample(), "abaqus_cpfe")

    assert not readiness.ready
    assert any("geometry" in item for item in readiness.missing)
    assert any("material" in item for item in readiness.missing)


@pytest.fixture
def solver_ready_sample(multimodal_sample_config):
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.config import load_pipeline_config

    return assemble_sample(load_pipeline_config(multimodal_sample_config))


def test_complete_solver_contract_is_ready(solver_ready_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness

    assert check_solver_readiness(solver_ready_sample, "abaqus_cpfe").ready


@pytest.mark.parametrize("units", [
    {}, {"length": "m", "time": "s"},
    {"length": "m", "stress": "unknown", "time": "s"},
    {"length": "m", "stress": "Pa", "time": "TBD"},
    {"length": "native units", "stress": "Pa", "time": "s"},
])
def test_readiness_rejects_missing_or_unresolved_units(solver_ready_sample, units):
    from experiment_to_cpfe.schema.validation import check_solver_readiness

    solver_ready_sample.metadata.unit_system = units
    report = check_solver_readiness(solver_ready_sample, "abaqus_cpfe")
    assert not report.ready
    assert any("unit" in item.lower() for item in report.missing)


def test_readiness_rejects_coordinate_length_unit_disagreement(solver_ready_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness

    solver_ready_sample.metadata.coordinate = solver_ready_sample.metadata.coordinate.model_copy(update={"units": "mm"})
    report = check_solver_readiness(solver_ready_sample, "abaqus_cpfe")
    assert not report.ready
    assert any("coordinate" in item.lower() for item in report.missing)


def test_missing_units_block_inp_even_with_replacements(solver_ready_sample, tmp_path):
    from experiment_to_cpfe.solvers.abaqus.inp import build_solver_input

    template = tmp_path / "template.inp"
    template.write_text('*Heading\n{{HEADING}}\n')
    solver_ready_sample.solver_inputs["inp_replacements"] = {"HEADING": "synthetic"}
    solver_ready_sample.metadata.unit_system = {}
    with pytest.raises(ValueError, match="unit"):
        build_solver_input(solver_ready_sample, template, tmp_path / "model.inp")
    assert not (tmp_path / "model.inp").exists()


def test_measured_curve_is_registered_as_calibration_target(make_sample):
    from experiment_to_cpfe.schema.calibration import make_calibration_target

    target = make_calibration_target(make_sample())

    assert target.response_kind == "stress_strain"
    assert target.observation_table == "measured_observations"
    assert target.split_role == "calibration_or_validation"
