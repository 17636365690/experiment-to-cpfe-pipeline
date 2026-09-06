def test_static_check_accepts_minimal_fixture():
    from pathlib import Path

    from experiment_to_cpfe.solvers.abaqus.static_check import static_check_inp

    report = static_check_inp(Path("configs/templates/minimal_abaqus.inp"))

    assert report.errors == ()
    assert report.counts["nodes"] == 8
    assert report.counts["elements"] == 1
    assert report.counts["steps"] == 1


def test_static_check_rejects_empty_nodes(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.static_check import static_check_inp

    path = tmp_path / "empty.inp"
    path.write_text(
        "*NODE\n*ELEMENT, TYPE=C3D8\n1, 1,2,3,4,5,6,7,8\n",
        encoding="utf-8",
    )

    report = static_check_inp(path)

    assert any("empty node block" in error for error in report.errors)


def test_static_check_rejects_duplicate_node_labels(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.static_check import static_check_inp

    path = tmp_path / "duplicate.inp"
    path.write_text(
        "*NODE\n1,0,0,0\n1,1,0,0\n*ELEMENT, TYPE=C3D8\n"
        "1,1,1,1,1,1,1,1,1\n*STEP\n*END STEP\n",
        encoding="utf-8",
    )

    report = static_check_inp(path)

    assert any("duplicate node label" in error for error in report.errors)


def test_static_check_rejects_unknown_connectivity(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.static_check import static_check_inp
    path = tmp_path / "bad.inp"
    path.write_text("*NODE\n1,0,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n*ELEMENT,TYPE=C3D4\n1,1,2,3,99\n*STEP\n*END STEP\n")
    assert any("unknown node" in error for error in static_check_inp(path).errors)


def test_static_check_rejects_nonfinite_coordinates(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.static_check import static_check_inp
    path = tmp_path / "bad.inp"
    path.write_text("*NODE\n1,nan,0,0\n2,1,0,0\n3,0,1,0\n4,0,0,1\n*ELEMENT,TYPE=C3D4\n1,1,2,3,4\n*STEP\n*END STEP\n")
    assert any("finite" in error for error in static_check_inp(path).errors)
