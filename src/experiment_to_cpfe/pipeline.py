"""Callable orchestration for each pipeline stage."""

import json
import os
from pathlib import Path
import shlex
import subprocess

from experiment_to_cpfe.adapters.tabular import assemble_sample
from experiment_to_cpfe.config import load_pipeline_config
from experiment_to_cpfe.datasets.hdf5 import write_hdf5
from experiment_to_cpfe.datasets.package import write_npz, write_pyg
from experiment_to_cpfe.provenance.hashing import sha256_file
from experiment_to_cpfe.provenance.manifest import build_run_manifest, write_manifest
from experiment_to_cpfe.schema.io import dump_sample_json
from experiment_to_cpfe.schema.models import SamplePackage
from experiment_to_cpfe.schema.validation import (
    check_solver_readiness,
    load_validation_policy,
    validate_sample,
    write_validation_report,
)
from experiment_to_cpfe.solvers.abaqus.extraction import (
    ExtractionRequest,
    build_abaqus_extraction_command,
    extraction_bundle_is_complete,
    load_extraction_bundle,
)
from experiment_to_cpfe.solvers.abaqus.inp import build_solver_input
from experiment_to_cpfe.solvers.abaqus.runner import (
    AbaqusRunRequest,
    SolverStage,
    run_abaqus,
)
from experiment_to_cpfe.solvers.abaqus.static_check import static_check_inp


RUN_SUBDIRECTORIES = ("input", "solver", "dataset", "reports")


def _create_new_run(run_dir: Path) -> None:
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"run directory is non-empty: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in RUN_SUBDIRECTORIES:
        (run_dir / name).mkdir()


def _require_validated_run(run_dir: Path) -> None:
    required = (
        run_dir / "reports" / "validation.json",
        run_dir / "reports" / "solver_readiness.json",
        run_dir / "reports" / "qa_report.md",
        run_dir / "reports" / "run_manifest.json",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "run must be validated first; missing: " + ", ".join(missing)
        )


def _stage_records(run_dir: Path) -> list[dict[str, object]]:
    path = run_dir / "reports" / "run_manifest.json"
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")).get("stages", []))


def _record_stage(
    run_dir: Path,
    config_path: Path,
    record: dict[str, object],
) -> dict[str, object]:
    stages = _stage_records(run_dir)
    if any(
        stage.get("stage") == record.get("stage")
        and stage.get("status") == "completed"
        for stage in stages
    ):
        raise FileExistsError(
            f"completed stage already exists: {record.get('stage')}"
        )
    stages.append(record)
    manifest = build_run_manifest(run_dir, config_path, stages)
    write_manifest(manifest, run_dir / "reports" / "run_manifest.json")
    return record


def _default_policy_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs" / "validation_policy.yaml"


def run_validate(config_path: Path, run_dir: Path) -> dict[str, object]:
    config_path = Path(config_path).resolve()
    run_dir = Path(run_dir).resolve()
    _create_new_run(run_dir)
    config = load_pipeline_config(config_path)
    sample = assemble_sample(config)
    normalized_path = run_dir / "input" / "normalized_sample.json"
    dump_sample_json(sample, normalized_path)

    policy = load_validation_policy(_default_policy_path())
    report = validate_sample(sample, policy)
    readiness = check_solver_readiness(sample, "abaqus_cpfe")
    validation_path = run_dir / "reports" / "validation.json"
    qa_path = run_dir / "reports" / "qa_report.md"
    write_validation_report(report, validation_path, qa_path)
    readiness_path = run_dir / "reports" / "solver_readiness.json"
    readiness_path.write_text(
        json.dumps(readiness.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    status = "completed" if report.passed and readiness.ready else "failed"
    record = {
        "stage": "validate",
        "status": status,
        "artifacts": [
            str(normalized_path),
            str(validation_path),
            str(readiness_path),
            str(qa_path),
        ],
        "limitations": list(readiness.missing),
    }
    return _record_stage(run_dir, config_path, record)


def run_build_inp(config_path: Path, run_dir: Path) -> dict[str, object]:
    config_path = Path(config_path).resolve()
    run_dir = Path(run_dir).resolve()
    _require_validated_run(run_dir)
    config = load_pipeline_config(config_path)
    sample = assemble_sample(config)
    if config.abaqus.template_path is None:
        raise ValueError("MISSING_SOLVER_INPUT: Abaqus template_path")
    output = run_dir / "input" / "model.inp"
    result = build_solver_input(sample, config.abaqus.template_path, output)
    static_report = static_check_inp(output)
    static_path = run_dir / "reports" / "inp_static_check.json"
    static_path.write_text(
        json.dumps(
            {
                "errors": list(static_report.errors),
                "warnings": list(static_report.warnings),
                "counts": static_report.counts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    record = {
        "stage": "build-inp",
        "status": "completed" if not static_report.errors else "failed",
        "artifacts": [str(result.output_path), str(static_path)],
        "limitations": list(static_report.errors),
        "input_sha256": result.sha256,
    }
    return _record_stage(run_dir, config_path, record)


def run_abaqus_stage(
    config_path: Path,
    run_dir: Path,
    stage: str,
) -> dict[str, object]:
    config_path = Path(config_path).resolve()
    run_dir = Path(run_dir).resolve()
    _require_validated_run(run_dir)
    config = load_pipeline_config(config_path)
    command = config.abaqus.command
    environment_command = os.environ.get("EXP2CPFE_ABAQUS_COMMAND")
    if environment_command:
        command = tuple(shlex.split(environment_command))
    result = run_abaqus(
        AbaqusRunRequest(
            abaqus_command=command,
            job_name=config.abaqus.job_name,
            inp_path=run_dir / "input" / "model.inp",
            work_dir=run_dir / "solver",
            stage=SolverStage(stage),
            user_subroutine=config.abaqus.user_subroutine,
            cpus=config.abaqus.cpus,
            timeout_seconds=config.abaqus.timeout_seconds,
        )
    )
    record = {
        "stage": f"abaqus-{stage}",
        "status": result.status,
        "command": list(result.command),
        "return_code": result.return_code,
        "compile_link_status": result.compile_link_status,
        "artifacts": [str(path) for path in result.artifacts],
        "limitations": list(result.limitations),
    }
    return _record_stage(run_dir, config_path, record)


def run_extract_odb(config_path: Path, run_dir: Path) -> dict[str, object]:
    config_path = Path(config_path).resolve()
    run_dir = Path(run_dir).resolve()
    _require_validated_run(run_dir)
    config = load_pipeline_config(config_path)
    odb_path = run_dir / "solver" / f"{config.abaqus.job_name}.odb"
    output_dir = run_dir / "solver" / "extracted"
    if not odb_path.is_file():
        return _record_stage(
            run_dir,
            config_path,
            {
                "stage": "extract-odb",
                "status": "blocked",
                "artifacts": [],
                "limitations": [f"real ODB is missing: {odb_path}"],
            },
        )
    request = ExtractionRequest(
        odb_path=odb_path,
        output_dir=output_dir,
        fields=config.abaqus.required_fields,
        position="integration_point",
    )
    command = build_abaqus_extraction_command(request, config.abaqus.command)
    if command[0].lower().endswith((".bat", ".cmd")):
        command = ("cmd.exe", "/d", "/c", *command)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=config.abaqus.timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        return _record_stage(
            run_dir,
            config_path,
            {
                "stage": "extract-odb",
                "status": "blocked",
                "command": list(command),
                "artifacts": [],
                "limitations": [f"Abaqus extraction command unavailable: {exc}"],
            },
        )
    complete, missing = extraction_bundle_is_complete(output_dir)
    if complete:
        metadata_path = output_dir / "metadata.json"
        extraction_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        sample = assemble_sample(config)
        extraction_metadata["sample_metadata"] = sample.metadata.model_dump(mode="json")
        metadata_path.write_text(
            json.dumps(extraction_metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    status = "completed" if completed.returncode == 0 and complete else "failed"
    artifacts = [str(path) for path in output_dir.iterdir()] if output_dir.exists() else []
    return _record_stage(
        run_dir,
        config_path,
        {
            "stage": "extract-odb",
            "status": status,
            "command": list(command),
            "return_code": completed.returncode,
            "artifacts": artifacts,
            "limitations": [f"missing extraction file: {name}" for name in missing],
        },
    )


def run_export(
    config_path: Path,
    run_dir: Path,
    format_name: str,
) -> dict[str, object]:
    config_path = Path(config_path).resolve()
    run_dir = Path(run_dir).resolve()
    _require_validated_run(run_dir)
    config = load_pipeline_config(config_path)
    sample = assemble_sample(config)
    extracted_dir = run_dir / "solver" / "extracted"
    complete, _ = extraction_bundle_is_complete(extracted_dir)
    if complete:
        extracted = load_extraction_bundle(extracted_dir)
        sample = SamplePackage(
            metadata=sample.metadata.model_copy(
                update={
                    "sources": (
                        *sample.metadata.sources,
                        *extracted.metadata.sources,
                    )
                }
            ),
            tables={**sample.tables, **extracted.tables},
            arrays={**sample.arrays, **extracted.arrays},
            assets=(*sample.assets, *extracted.assets),
            solver_inputs={
                **sample.solver_inputs,
                "extraction": extracted.solver_inputs["extraction"],
            },
        )
    artifacts: list[str] = []
    if format_name == "hdf5":
        output = run_dir / "dataset" / "sample.h5"
        digest = write_hdf5(
            sample,
            output,
            json.loads((run_dir / "reports" / "run_manifest.json").read_text(encoding="utf-8")),
        )
        artifacts.append(str(output))
    elif format_name in {"npz", "pyg"}:
        hdf5_path = run_dir / "dataset" / "sample.h5"
        if not hdf5_path.is_file():
            raise FileNotFoundError("canonical HDF5 export must exist first")
        digest = sha256_file(hdf5_path)
        if format_name == "npz":
            output = run_dir / "dataset" / "sample.npz"
            write_npz(sample, output, digest)
        else:
            output = run_dir / "dataset" / "sample.pt"
            write_pyg(sample, output, digest)
        artifacts.append(str(output))
    else:
        raise ValueError(f"unsupported export format: {format_name}")
    return _record_stage(
        run_dir,
        config_path,
        {
            "stage": f"export-{format_name}",
            "status": "completed",
            "artifacts": artifacts,
            "source_hdf5_sha256": digest,
            "limitations": [],
        },
    )


def inspect_run(run_dir: Path) -> dict[str, object]:
    path = Path(run_dir) / "reports" / "run_manifest.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))
