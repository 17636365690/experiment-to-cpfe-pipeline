"""Scientific-input gates must inspect the declared and actual model."""

from copy import deepcopy

import pytest


@pytest.fixture
def contract_sample(multimodal_sample_config):
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.config import load_pipeline_config
    return assemble_sample(load_pipeline_config(multimodal_sample_config))


def test_valid_explicit_elastic_contract_is_ready(contract_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    assert check_solver_readiness(contract_sample, "abaqus_cpfe").ready


@pytest.mark.parametrize("key,value", [
    ("microstructure_mapping", {"999": [1]}),
    ("microstructure_mapping", {"1": [1], "2": [1]}),
    ("microstructure_mapping", {"1": [999]}),
    ("material_model", "unverified_cp_model"),
    ("material_parameters", {"E": 999.0, "nu": 0.3}),
    ("material_parameters", {"E": float("nan"), "nu": 0.3}),
    ("boundary_conditions", ["fixed"]),
    ("boundary_conditions", [{"target": "1", "first_dof": 1, "last_dof": 3, "value": 5.0}]),
    ("load_steps", ["tension"]),
    ("output_variables", ["S", "SDV"]),
    ("orientation_required", True),
])
def test_truthy_but_inconsistent_contract_is_not_ready(contract_sample, key, value):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    contract_sample.solver_inputs[key] = value
    assert not check_solver_readiness(contract_sample, "abaqus_cpfe").ready


@pytest.mark.parametrize("key,replacement", [
    ("NODES", "*NODE\n1,0,0,0"),
    ("ELEMENTS", "*ELEMENT, TYPE=C3D8, ELSET=ALL\n1,1,2,3,4,5,6,7,999"),
    ("MATERIALS", "*MATERIAL, NAME=SYNTHETIC\n*ELASTIC\n1.0,0.3"),
    ("BOUNDARY_CONDITIONS", "** boundary omitted"),
    ("OUTPUT_REQUESTS", "*STEP, NAME=SMOKE\n*STATIC\n0.1,1\n*END STEP"),
])
def test_incomplete_actual_keyword_input_is_not_ready(contract_sample, key, replacement):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    contract_sample.solver_inputs["inp_replacements"][key] = replacement
    assert not check_solver_readiness(contract_sample, "abaqus_cpfe").ready


def test_mesh_table_must_match_actual_input_connectivity(contract_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    contract_sample.tables["mesh_elements"] = [{"element_id": 1, "grain_id": 1, "connectivity": [8, 7, 6, 5, 4, 3, 2, 1]}]
    assert not check_solver_readiness(contract_sample, "abaqus_cpfe").ready


def test_template_omitting_mesh_is_blocked_before_creating_inp(contract_sample, tmp_path):
    from experiment_to_cpfe.solvers.abaqus.inp import build_solver_input
    template = tmp_path / "incomplete.inp"
    template.write_text("*HEADING\n{{HEADING}}\n{{MATERIALS}}\n{{BOUNDARY_CONDITIONS}}\n{{OUTPUT_REQUESTS}}\n")
    output = tmp_path / "model.inp"
    with pytest.raises(ValueError, match="node|mesh|element"):
        build_solver_input(contract_sample, template, output)
    assert not output.exists()


def test_native_deck_contract_can_be_checked_without_template(contract_sample):
    from experiment_to_cpfe.schema.validation import check_deck_readiness
    deck = "*HEADING\n" + "\n".join(contract_sample.solver_inputs.pop("inp_replacements").values())
    assert check_deck_readiness(contract_sample, deck).ready


def test_umat_constants_and_state_count_match_actual_keywords(contract_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    contract_sample.solver_inputs.update(material_model="umat", material_parameters={"constants": [3.0, 0.2], "constant_units": ["Pa", "1"], "depvar": 2})
    contract_sample.solver_inputs["inp_replacements"]["MATERIALS"] = "*MATERIAL, NAME=SYNTHETIC\n*USER MATERIAL, CONSTANTS=2\n3.0,0.2\n*DEPVAR\n2\n*SOLID SECTION, ELSET=ALL, MATERIAL=SYNTHETIC"
    assert check_solver_readiness(contract_sample, "abaqus_cpfe").ready
    contract_sample.solver_inputs["material_parameters"]["constants"][0] = 4.0
    assert not check_solver_readiness(contract_sample, "abaqus_cpfe").ready


def test_loss_description_is_not_coordinate_registration(make_sample, validation_policy):
    from experiment_to_cpfe.schema.validation import validate_sample
    sample = make_sample()
    sample.assets = (sample.assets[0].model_copy(update={"coordinate_frame": "camera", "lossy_transformations": ("coordinate registration pending",)}),)
    assert any(issue.code == "REGISTRATION_REQUIRED" for issue in validate_sample(sample, validation_policy).errors)


@pytest.mark.parametrize("rows", [[{"time": 1.0, "value": float("nan")}], [{"time": 2.0}, {"time": 1.0}]])
def test_bad_table_values_or_reversed_time_are_invalid(make_sample, validation_policy, rows):
    from experiment_to_cpfe.schema.validation import validate_sample
    sample = make_sample()
    sample.tables["load_history"] = deepcopy(rows)
    assert not validate_sample(sample, validation_policy).passed


@pytest.mark.parametrize("mutation", ["step_order", "unknown_option", "unknown_unit", "wrong_tensor", "unconstrained", "zero_load", "unknown_output"])
def test_unsupported_or_incomplete_physics_contract_fails_closed(contract_sample, mutation):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    replacements = contract_sample.solver_inputs["inp_replacements"]
    if mutation == "step_order":
        replacements["OUTPUT_REQUESTS"] = replacements["OUTPUT_REQUESTS"].replace("*STATIC\n0.1,1", "").replace("*END STEP", "*END STEP\n*STATIC\n0.1,1")
    elif mutation == "unknown_option":
        replacements["ELEMENTS"] = replacements["ELEMENTS"].replace("TYPE=C3D8", "TYPE=C3D8, INPUT=other.inp")
    elif mutation == "unknown_unit":
        contract_sample.metadata.unit_system["stress"] = "bananas"
    elif mutation == "wrong_tensor":
        contract_sample.metadata.tensor_order = ("11", "22", "33", "12", "23", "13")
    elif mutation == "unconstrained":
        replacements["BOUNDARY_CONDITIONS"] = "*BOUNDARY\n1,1,3,0\n5,3,3,0.001"
        contract_sample.solver_inputs["boundary_conditions"] = [{"target":"1","first_dof":1,"last_dof":3,"value":0.0}, {"target":"5","first_dof":3,"last_dof":3,"value":0.001}]
    elif mutation == "zero_load":
        replacements["BOUNDARY_CONDITIONS"] = replacements["BOUNDARY_CONDITIONS"].replace("0.001", "0")
        replacements["OUTPUT_REQUESTS"] = replacements["OUTPUT_REQUESTS"].replace("0.001", "0")
        for boundary in contract_sample.solver_inputs["boundary_conditions"]:
            boundary["value"] = 0.0
    else:
        replacements["OUTPUT_REQUESTS"] = replacements["OUTPUT_REQUESTS"].replace("S,LE", "S,LE,BOGUS")
        contract_sample.solver_inputs["output_variables"] = ["S", "LE", "BOGUS"]
    assert not check_solver_readiness(contract_sample, "abaqus_cpfe").ready


def test_source_ids_with_leading_zeroes_are_not_collapsed(contract_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    contract_sample.tables["grains"] = [{**contract_sample.tables["grains"][0], "grain_id": "001"}, {**contract_sample.tables["grains"][1], "grain_id": "1"}]
    contract_sample.solver_inputs["microstructure_mapping"] = {"001": [1]}
    assert check_solver_readiness(contract_sample, "abaqus_cpfe").ready


def test_nonfinite_quaternion_reports_error_instead_of_raising(make_sample, validation_policy):
    from experiment_to_cpfe.schema.validation import validate_sample
    sample = make_sample()
    sample.tables["grains"] = [{"grain_id":"1", "q0":"bad", "q1":0, "q2":0, "q3":0}]
    assert not validate_sample(sample, validation_policy).passed


@pytest.fixture
def oriented_umat_sample(contract_sample):
    contract_sample.solver_inputs.update(
        material_model="umat", orientation_required=True,
        material_parameters={"constants": [3.0, 0.2], "constant_units": ["Pa", "1"], "depvar": 4},
        orientation_state_variables={"columns": ["q0", "q1", "q2", "q3"], "indices": [1, 2, 3, 4]},
    )
    contract_sample.solver_inputs["inp_replacements"]["MATERIALS"] = "*MATERIAL, NAME=SYNTHETIC\n*USER MATERIAL, CONSTANTS=2\n3.0,0.2\n*DEPVAR\n4\n*SOLID SECTION, ELSET=ALL, MATERIAL=SYNTHETIC\n*INITIAL CONDITIONS, TYPE=SOLUTION\nALL,1,0,0,0"
    return contract_sample


def replace_fixture_grain_rows(sample, rows, units):
    """Declare a different synthetic orientation source for representation tests."""
    source = next(asset for asset in sample.assets if asset.descriptive_metadata.get("table_name") == "grains")
    sample.tables["grains"] = [{**row, "source_asset_id": source.asset_id, "source_kind": source.source_kind.value} for row in rows]
    changed = source.model_copy(update={"units": units,
        "descriptive_metadata": {"table_name": "grains", "column_map": {name: name for name in units}}})
    sample.assets = tuple(changed if asset.asset_id == source.asset_id else asset for asset in sample.assets)


def test_explicit_umat_orientation_state_values_make_native_deck_ready(oriented_umat_sample):
    from experiment_to_cpfe.schema.validation import check_deck_readiness
    deck = "*HEADING\n" + "\n".join(oriented_umat_sample.solver_inputs.pop("inp_replacements").values())
    assert check_deck_readiness(oriented_umat_sample, deck).ready


@pytest.mark.parametrize("mutation", ["missing_layout", "wrong_values", "unknown_target", "duplicate_target", "partial_state", "nonfinite_state", "duplicate_indices", "index_outside_depvar", "wrong_column_count", "missing_column", "placeholder_convention", "placeholder_symmetry", "user_subroutine_init", "initial_inside_step"])
def test_orientation_mapping_rejects_unproven_or_ambiguous_state_assignment(oriented_umat_sample, mutation):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    inputs = oriented_umat_sample.solver_inputs
    material = inputs["inp_replacements"]["MATERIALS"]
    if mutation == "missing_layout":
        inputs.pop("orientation_state_variables")
    elif mutation == "wrong_values":
        material = material.replace("ALL,1,0,0,0", "ALL,0,1,0,0")
    elif mutation == "unknown_target":
        material = material.replace("ALL,1,0,0,0", "MISSING,1,0,0,0")
    elif mutation == "duplicate_target":
        material += "\n1,1,0,0,0"
    elif mutation == "partial_state":
        material = material.replace("ALL,1,0,0,0", "ALL,1,0,0")
    elif mutation == "nonfinite_state":
        material = material.replace("ALL,1,0,0,0", "ALL,1,0,0,nan")
    elif mutation == "duplicate_indices":
        inputs["orientation_state_variables"]["indices"] = [1, 1, 3, 4]
    elif mutation == "index_outside_depvar":
        inputs["orientation_state_variables"]["indices"] = [1, 2, 3, 5]
    elif mutation == "wrong_column_count":
        inputs["orientation_state_variables"]["columns"] = ["q0", "q1", "q2"]
    elif mutation == "missing_column":
        inputs["orientation_state_variables"]["columns"][0] = "not_present"
    elif mutation == "placeholder_convention":
        oriented_umat_sample.metadata.orientation = oriented_umat_sample.metadata.orientation.model_copy(update={"convention": "unknown"})
    elif mutation == "placeholder_symmetry":
        oriented_umat_sample.metadata.orientation = oriented_umat_sample.metadata.orientation.model_copy(update={"crystal_symmetry": "TBD"})
    elif mutation == "user_subroutine_init":
        material = material.replace("TYPE=SOLUTION", "TYPE=SOLUTION, USER")
    else:
        initial = "*INITIAL CONDITIONS, TYPE=SOLUTION\nALL,1,0,0,0"
        material = material.replace(initial, "")
        inputs["inp_replacements"]["OUTPUT_REQUESTS"] = inputs["inp_replacements"]["OUTPUT_REQUESTS"].replace("*END STEP", initial + "\n*END STEP")
    inputs["inp_replacements"]["MATERIALS"] = material
    assert not check_solver_readiness(oriented_umat_sample, "abaqus_cpfe").ready


def test_euler_orientation_mapping_keeps_declared_degrees_and_state_indices(oriented_umat_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    sample = oriented_umat_sample
    sample.metadata.orientation = sample.metadata.orientation.model_copy(update={"representation": "euler", "convention": "Bunge ZXZ", "angle_units": "degree"})
    replace_fixture_grain_rows(sample, [{"grain_id": "1", "phi1": 30.0, "Phi": 15.0, "phi2": 10.0}], {"grain_id": "1", "phi1": "degree", "Phi": "degree", "phi2": "degree"})
    sample.solver_inputs["orientation_state_variables"] = {"columns": ["phi1", "Phi", "phi2"], "indices": [2, 3, 4]}
    sample.solver_inputs["inp_replacements"]["MATERIALS"] = sample.solver_inputs["inp_replacements"]["MATERIALS"].replace("ALL,1,0,0,0", "1,9,30,15,10")
    assert check_solver_readiness(sample, "abaqus_cpfe").ready
    sample.metadata.orientation = sample.metadata.orientation.model_copy(update={"angle_units": None})
    assert not check_solver_readiness(sample, "abaqus_cpfe").ready


def test_rotation_matrix_orientation_reads_full_depvar_continuation(oriented_umat_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    sample = oriented_umat_sample
    columns = ["r11", "r12", "r13", "r21", "r22", "r23", "r31", "r32", "r33"]
    sample.metadata.orientation = sample.metadata.orientation.model_copy(update={"representation": "rotation_matrix", "convention": "row_major_sample_to_crystal"})
    replace_fixture_grain_rows(sample, [{"grain_id": "1", **dict(zip(columns, [1, 0, 0, 0, 1, 0, 0, 0, 1]))}], {"grain_id": "1", **{column: "1" for column in columns}})
    sample.solver_inputs["material_parameters"]["depvar"] = 10
    sample.solver_inputs["orientation_state_variables"] = {"columns": columns, "indices": list(range(2, 11))}
    sample.solver_inputs["inp_replacements"]["MATERIALS"] = sample.solver_inputs["inp_replacements"]["MATERIALS"].replace("*DEPVAR\n4", "*DEPVAR\n10").replace("ALL,1,0,0,0", "ALL,9,1,0,0,0,1,0\n0,0,1")
    assert check_solver_readiness(sample, "abaqus_cpfe").ready
    sample.solver_inputs["inp_replacements"]["MATERIALS"] = sample.solver_inputs["inp_replacements"]["MATERIALS"].replace("\n0,0,1", "\n0,1")
    assert not check_solver_readiness(sample, "abaqus_cpfe").ready


def test_initial_orientation_state_is_model_data_not_post_step_data(oriented_umat_sample):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    replacements = oriented_umat_sample.solver_inputs["inp_replacements"]
    initial = "*INITIAL CONDITIONS, TYPE=SOLUTION\nALL,1,0,0,0"
    replacements["MATERIALS"] = replacements["MATERIALS"].replace(initial, "")
    replacements["OUTPUT_REQUESTS"] += "\n" + initial
    assert not check_solver_readiness(oriented_umat_sample, "abaqus_cpfe").ready
