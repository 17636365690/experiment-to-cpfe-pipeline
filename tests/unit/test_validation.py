import numpy as np


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


def test_complete_solver_contract_is_ready(make_sample):
    from experiment_to_cpfe.assets.models import (
        AssetKind,
        AssetRef,
        DataLayer,
        SourceKind,
    )
    from experiment_to_cpfe.schema.models import SamplePackage
    from experiment_to_cpfe.schema.validation import check_solver_readiness

    source = make_sample()
    mesh = AssetRef(
        asset_id="mesh-input",
        parent_asset_id=None,
        modality=AssetKind.MESH,
        format="inp",
        uri="synthetic/model.inp",
        source_kind=SourceKind.INPUT,
        layer=DataLayer.SOLVER_INPUT,
        units={"length": "m"},
        coordinate_frame="sample",
        axis_order=("node", "coordinate"),
        dtype="mixed",
        shape=(8, 3),
        native_layout="abaqus_keyword_mesh",
        sha256=None,
        license="synthetic",
        lossy_transformations=(),
    )
    orientation = source.assets[0].model_copy(
        update={
            "asset_id": "orientation-input",
            "modality": AssetKind.ORIENTATION_MAP,
            "source_kind": SourceKind.INPUT,
        }
    )
    sample = SamplePackage(
        metadata=source.metadata,
        tables=source.tables,
        arrays=source.arrays,
        assets=(mesh, orientation),
        solver_inputs={
            "microstructure_mapping": {"1": [1]},
            "material_model": "user_cp_model",
            "material_parameters": {"elastic_modulus": 1.0},
            "orientation_required": True,
            "boundary_conditions": ["fixed-x"],
            "load_steps": ["tension"],
            "output_variables": ["S", "LE", "PEEQ", "SDV"],
        },
    )

    assert check_solver_readiness(sample, "abaqus_cpfe").ready


def test_measured_curve_is_registered_as_calibration_target(make_sample):
    from experiment_to_cpfe.schema.calibration import make_calibration_target

    target = make_calibration_target(make_sample())

    assert target.response_kind == "stress_strain"
    assert target.observation_table == "measured_observations"
    assert target.split_role == "calibration_or_validation"
