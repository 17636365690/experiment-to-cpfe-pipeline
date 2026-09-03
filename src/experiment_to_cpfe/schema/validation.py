"""Pure validation and solver-readiness gates."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Literal

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, Field

from experiment_to_cpfe.assets.models import AssetKind, AssetManifest
from experiment_to_cpfe.schema.models import SamplePackage


Severity = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    location: str


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")

    @property
    def passed(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "issues": [
                {
                    "code": issue.code,
                    "severity": issue.severity,
                    "message": issue.message,
                    "location": issue.location,
                }
                for issue in self.issues
            ],
        }


class ValidationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quaternion_tolerance: float = Field(default=1.0e-6, gt=0)
    require_finite: bool = True
    missing_units_severity: Severity = "error"
    required_tables_by_profile: dict[str, tuple[str, ...]] = {}
    required_assets_by_solver: dict[str, tuple[str, ...]] = {}


@dataclass(frozen=True)
class SolverReadinessReport:
    missing: tuple[str, ...]
    warnings: tuple[str, ...]
    ready: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "missing": list(self.missing),
            "warnings": list(self.warnings),
        }


def load_validation_policy(path: Path) -> ValidationPolicy:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ValidationPolicy.model_validate(payload)


def _issue(
    code: str,
    message: str,
    location: str,
    severity: Severity = "error",
) -> ValidationIssue:
    return ValidationIssue(code, severity, message, location)


def validate_asset_links(
    sample: SamplePackage,
    policy: ValidationPolicy,
) -> tuple[ValidationIssue, ...]:
    del policy
    issues: list[ValidationIssue] = []
    try:
        AssetManifest(assets=sample.assets)
    except ValueError as exc:
        issues.append(_issue("INVALID_ASSET_LINK", str(exc), "assets"))

    sample_frame = sample.metadata.coordinate.name
    for asset in sample.assets:
        if (
            asset.coordinate_frame
            and asset.coordinate_frame != sample_frame
            and not any(
                "coordinate" in transformation.lower()
                or "registration" in transformation.lower()
                for transformation in asset.lossy_transformations
            )
        ):
            issues.append(
                _issue(
                    "REGISTRATION_REQUIRED",
                    f"asset frame {asset.coordinate_frame!r} is not registered "
                    f"to sample frame {sample_frame!r}",
                    f"assets.{asset.asset_id}.coordinate_frame",
                )
            )
    return tuple(issues)


def validate_sample(
    sample: SamplePackage,
    policy: ValidationPolicy,
) -> ValidationReport:
    issues: list[ValidationIssue] = list(validate_asset_links(sample, policy))
    if not sample.metadata.unit_system:
        issues.append(
            _issue(
                "MISSING_UNIT",
                "sample unit_system is empty",
                "metadata.unit_system",
                policy.missing_units_severity,
            )
        )

    if policy.require_finite:
        for name, array in sample.arrays.items():
            if np.issubdtype(array.dtype, np.number) and not np.isfinite(array).all():
                issues.append(
                    _issue(
                        "NONFINITE_VALUE",
                        f"array {name!r} contains NaN or infinity",
                        f"arrays.{name}",
                    )
                )

    grains = sample.tables.get("grains", [])
    grain_ids = {row.get("grain_id") for row in grains if "grain_id" in row}
    if len(grain_ids) != len([row for row in grains if "grain_id" in row]):
        issues.append(
            _issue("DUPLICATE_GRAIN_ID", "grain IDs must be unique", "tables.grains")
        )
    for index, row in enumerate(sample.tables.get("mesh_elements", [])):
        if "grain_id" in row and row["grain_id"] not in grain_ids:
            issues.append(
                _issue(
                    "UNKNOWN_GRAIN_ID",
                    f"element references unknown grain {row['grain_id']!r}",
                    f"tables.mesh_elements[{index}].grain_id",
                )
            )

    for index, row in enumerate(grains):
        quaternion_keys = ("q0", "q1", "q2", "q3")
        if all(key in row for key in quaternion_keys):
            norm = math.sqrt(sum(float(row[key]) ** 2 for key in quaternion_keys))
            if abs(norm - 1.0) > policy.quaternion_tolerance:
                issues.append(
                    _issue(
                        "INVALID_QUATERNION",
                        f"quaternion norm is {norm}",
                        f"tables.grains[{index}]",
                    )
                )

    for table_name in ("load_history", "measured_observations", "simulation_records"):
        rows = sample.tables.get(table_name, [])
        increments = [row.get("increment_id") for row in rows if "increment_id" in row]
        if len(increments) != len(set(increments)):
            issues.append(
                _issue(
                    "DUPLICATE_INCREMENT",
                    f"{table_name} contains duplicate increment IDs",
                    f"tables.{table_name}",
                )
            )
    return ValidationReport(tuple(issues))


def check_solver_readiness(
    sample: SamplePackage,
    solver_name: str,
) -> SolverReadinessReport:
    if solver_name != "abaqus_cpfe":
        return SolverReadinessReport(
            missing=(f"unsupported solver profile: {solver_name}",),
            warnings=(),
            ready=False,
        )

    modalities = {asset.modality for asset in sample.assets}
    inputs = sample.solver_inputs
    missing: list[str] = []
    if AssetKind.MESH not in modalities:
        missing.append("geometry/mesh asset")
    if not inputs.get("microstructure_mapping"):
        missing.append("microstructure-to-mesh mapping")
    if not inputs.get("material_model"):
        missing.append("material model")
    if not (
        inputs.get("material_parameters") or inputs.get("calibration_result")
    ):
        missing.append("material parameters or explicit calibration result")
    if inputs.get("orientation_required", True) and AssetKind.ORIENTATION_MAP not in modalities:
        missing.append("orientation data")
    if not inputs.get("boundary_conditions"):
        missing.append("boundary conditions")
    if not inputs.get("load_steps"):
        missing.append("loading definition")
    if not inputs.get("output_variables"):
        missing.append("output-variable contract")
    missing_tuple = tuple(f"MISSING_SOLVER_INPUT: {item}" for item in missing)
    return SolverReadinessReport(
        missing=missing_tuple,
        warnings=(),
        ready=not missing_tuple,
    )


def write_validation_report(
    report: ValidationReport,
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path = Path(json_path)
    markdown_path = Path(markdown_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = ["# Validation Report", "", f"Passed: `{report.passed}`", ""]
    for issue in report.issues:
        lines.append(
            f"- **{issue.severity.upper()} {issue.code}** "
            f"at `{issue.location}`: {issue.message}"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
