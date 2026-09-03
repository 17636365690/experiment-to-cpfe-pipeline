import sys
from pathlib import Path


def request(tmp_path, *, command=None, stage="analysis", user_subroutine=None):
    from experiment_to_cpfe.solvers.abaqus.runner import (
        AbaqusRunRequest,
        SolverStage,
    )

    work_dir = tmp_path / "solver"
    work_dir.mkdir()
    inp = work_dir / "model.inp"
    inp.write_text("*HEADING\n", encoding="utf-8")
    return AbaqusRunRequest(
        abaqus_command=command
        or (sys.executable, str(Path("tests/fixtures/fake_solver.py").resolve())),
        job_name="synthetic",
        inp_path=inp,
        work_dir=work_dir,
        stage=SolverStage(stage),
        user_subroutine=user_subroutine,
        cpus=1,
        timeout_seconds=10,
    )


def test_runner_records_completed_analysis_with_artifact_evidence(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.runner import run_abaqus

    result = run_abaqus(request(tmp_path))

    assert result.status == "completed"
    assert result.return_code == 0
    assert result.compile_link_status == "not_required"
    assert {path.suffix for path in result.artifacts} == {
        ".odb",
        ".sta",
        ".dat",
        ".msg",
    }


def test_runner_marks_missing_output_as_failure(tmp_path, monkeypatch):
    from experiment_to_cpfe.solvers.abaqus.runner import run_abaqus

    monkeypatch.setenv("FAKE_SOLVER_NO_OUTPUT", "1")
    result = run_abaqus(request(tmp_path))

    assert result.status == "failed"
    assert any("expected artifact" in item for item in result.limitations)


def test_runner_marks_aborted_sta_as_failure(tmp_path, monkeypatch):
    from experiment_to_cpfe.solvers.abaqus.runner import run_abaqus

    monkeypatch.setenv("FAKE_SOLVER_ABORT", "1")
    result = run_abaqus(request(tmp_path))

    assert result.status == "failed"
    assert any("STA" in item for item in result.limitations)


def test_runner_marks_missing_command_as_blocked(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.runner import run_abaqus

    result = run_abaqus(
        request(tmp_path, command=("definitely-not-an-abaqus-command",))
    )

    assert result.status == "blocked"
    assert result.return_code is None


def test_datacheck_does_not_require_odb(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.runner import run_abaqus

    result = run_abaqus(request(tmp_path, stage="datacheck"))

    assert result.status == "completed"
    assert all(path.suffix != ".odb" for path in result.artifacts)


def test_user_subroutine_requires_compile_and_link_evidence(tmp_path):
    from experiment_to_cpfe.solvers.abaqus.runner import run_abaqus

    user = tmp_path / "umat.for"
    user.write_text("C synthetic fixture\n", encoding="ascii")
    result = run_abaqus(request(tmp_path, user_subroutine=user))

    assert result.status == "failed"
    assert result.compile_link_status == "missing_evidence"


def test_user_subroutine_records_compile_and_link_success(tmp_path, monkeypatch):
    from experiment_to_cpfe.solvers.abaqus.runner import run_abaqus

    user = tmp_path / "umat.for"
    user.write_text("C synthetic fixture\n", encoding="ascii")
    monkeypatch.setenv("FAKE_SOLVER_COMPILE_SUCCESS", "1")
    result = run_abaqus(request(tmp_path, user_subroutine=user))

    assert result.status == "completed"
    assert result.compile_link_status == "completed"
