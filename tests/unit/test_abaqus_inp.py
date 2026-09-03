import pytest


def replacements():
    return {
        "HEADING": "Synthetic two-element model",
        "NODES": "*NODE\n1, 0, 0, 0\n2, 1, 0, 0\n3, 1, 1, 0\n4, 0, 1, 0\n5, 0, 0, 1\n6, 1, 0, 1\n7, 1, 1, 1\n8, 0, 1, 1",
        "ELEMENTS": "*ELEMENT, TYPE=C3D8, ELSET=ALL\n1, 1,2,3,4,5,6,7,8",
        "MATERIALS": "*MATERIAL, NAME=SYNTHETIC\n*ELASTIC\n1.0, 0.3",
        "BOUNDARY_CONDITIONS": "*BOUNDARY\n1, 1, 3, 0.0",
        "OUTPUT_REQUESTS": "*STEP\n*STATIC\n0.1, 1.0\n*OUTPUT, FIELD\n*ELEMENT OUTPUT\nS, LE, PEEQ\n*END STEP",
    }


def test_build_inp_replaces_all_known_markers(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.inp import SolverInputRequest, build_inp

    template = tmp_path / "template.inp"
    output = tmp_path / "model.inp"
    template.write_text(
        "*HEADING\n{{HEADING}}\n{{NODES}}\n{{ELEMENTS}}\n"
        "{{MATERIALS}}\n{{BOUNDARY_CONDITIONS}}\n{{OUTPUT_REQUESTS}}\n",
        encoding="utf-8",
    )
    result = build_inp(
        SolverInputRequest(template, output, replacements())
    )

    assert result.output_path == output
    assert "{{" not in output.read_text(encoding="utf-8")
    assert len(result.sha256) == 64


def test_build_inp_rejects_existing_output(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.inp import SolverInputRequest, build_inp

    template = tmp_path / "template.inp"
    template.write_text("{{HEADING}}", encoding="utf-8")
    output = tmp_path / "model.inp"
    output.write_text("keep", encoding="utf-8")

    with pytest.raises(FileExistsError):
        build_inp(SolverInputRequest(template, output, replacements()))

    assert output.read_text(encoding="utf-8") == "keep"


def test_build_solver_input_rejects_curve_only_sample(tmp_path, make_sample):
    from experiment_to_cpfe.solvers.abaqus.inp import build_solver_input

    with pytest.raises(ValueError, match="MISSING_SOLVER_INPUT"):
        build_solver_input(
            make_sample(),
            tmp_path / "unused-template.inp",
            tmp_path / "should-not-exist.inp",
        )

    assert not (tmp_path / "should-not-exist.inp").exists()
