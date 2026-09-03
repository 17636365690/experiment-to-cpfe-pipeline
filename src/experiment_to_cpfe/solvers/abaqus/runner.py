"""Staged Abaqus execution with artifact and status-file evidence."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import shutil
import subprocess


class SolverStage(str, Enum):
    DATACHECK = "datacheck"
    ANALYSIS = "analysis"


@dataclass(frozen=True)
class AbaqusRunRequest:
    abaqus_command: tuple[str, ...]
    job_name: str
    inp_path: Path
    work_dir: Path
    stage: SolverStage
    user_subroutine: Path | None
    cpus: int
    timeout_seconds: int


@dataclass(frozen=True)
class SolverRunResult:
    stage: SolverStage
    status: str
    command: tuple[str, ...]
    return_code: int | None
    stdout_path: Path
    stderr_path: Path
    artifacts: tuple[Path, ...]
    compile_link_status: str
    limitations: tuple[str, ...]


def expected_artifacts(job_name: str, stage: SolverStage) -> tuple[str, ...]:
    if stage is SolverStage.DATACHECK:
        return (f"{job_name}.dat", f"{job_name}.msg")
    return (
        f"{job_name}.odb",
        f"{job_name}.sta",
        f"{job_name}.dat",
        f"{job_name}.msg",
    )


def _is_ascii_path(path: Path) -> bool:
    try:
        str(path.resolve()).encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _command(request: AbaqusRunRequest, staged_inp: Path) -> tuple[str, ...]:
    base = request.abaqus_command
    if base[0].lower().endswith((".bat", ".cmd")):
        base = ("cmd.exe", "/d", "/c", *base)
    arguments = [
        f"job={request.job_name}",
        f"input={staged_inp.name}",
        f"cpus={request.cpus}",
        "interactive",
    ]
    if request.stage is SolverStage.DATACHECK:
        arguments.append("datacheck")
    if request.user_subroutine is not None:
        arguments.append(f"user={request.user_subroutine}")
    return (*base, *arguments)


def run_abaqus(request: AbaqusRunRequest) -> SolverRunResult:
    work_dir = Path(request.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = work_dir / f"{request.job_name}.{request.stage.value}.stdout.txt"
    stderr_path = work_dir / f"{request.job_name}.{request.stage.value}.stderr.txt"
    compile_status = (
        "not_required" if request.user_subroutine is None else "unverified"
    )

    if not request.abaqus_command:
        return SolverRunResult(
            request.stage,
            "blocked",
            (),
            None,
            stdout_path,
            stderr_path,
            (),
            compile_status,
            ("Abaqus command is not configured",),
        )
    if not _is_ascii_path(work_dir):
        return SolverRunResult(
            request.stage,
            "blocked",
            request.abaqus_command,
            None,
            stdout_path,
            stderr_path,
            (),
            compile_status,
            ("solver work directory must be ASCII-only",),
        )

    inp_path = Path(request.inp_path).resolve()
    staged_inp = work_dir / inp_path.name
    if inp_path != staged_inp.resolve():
        if staged_inp.exists():
            return SolverRunResult(
                request.stage,
                "blocked",
                request.abaqus_command,
                None,
                stdout_path,
                stderr_path,
                (),
                compile_status,
                (f"staged input already exists: {staged_inp}",),
            )
        shutil.copy2(inp_path, staged_inp)
    command = _command(request, staged_inp)

    try:
        completed = subprocess.run(
            command,
            cwd=work_dir,
            capture_output=True,
            text=True,
            timeout=request.timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        return SolverRunResult(
            request.stage,
            "blocked",
            command,
            None,
            stdout_path,
            stderr_path,
            (),
            compile_status,
            (f"solver command is unavailable: {exc}",),
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        return SolverRunResult(
            request.stage,
            "failed",
            command,
            None,
            stdout_path,
            stderr_path,
            (),
            compile_status,
            (f"solver timeout after {request.timeout_seconds} seconds",),
        )

    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    expected = tuple(work_dir / name for name in expected_artifacts(
        request.job_name,
        request.stage,
    ))
    artifacts = tuple(path for path in expected if path.is_file())
    limitations: list[str] = []
    missing = [path.name for path in expected if not path.is_file()]
    if missing:
        limitations.append(f"expected artifact is missing: {', '.join(missing)}")
    if completed.returncode != 0:
        limitations.append(f"solver process returned {completed.returncode}")

    if request.user_subroutine is not None:
        process_evidence = (completed.stdout + "\n" + completed.stderr).upper()
        if (
            "FORTRAN COMPILE SUCCESS" in process_evidence
            and "FORTRAN LINK SUCCESS" in process_evidence
        ):
            compile_status = "completed"
        else:
            compile_status = "missing_evidence"
            limitations.append(
                "Fortran compile/link success evidence is missing"
            )

    if request.stage is SolverStage.ANALYSIS:
        sta_path = work_dir / f"{request.job_name}.sta"
        if sta_path.is_file():
            sta = sta_path.read_text(encoding="utf-8", errors="replace").upper()
            if "ABORTED" in sta or "COMPLETED SUCCESSFULLY" not in sta:
                limitations.append("STA does not confirm successful analysis completion")

    status = "completed" if not limitations else "failed"
    return SolverRunResult(
        request.stage,
        status,
        command,
        completed.returncode,
        stdout_path,
        stderr_path,
        artifacts,
        compile_status,
        tuple(limitations),
    )
