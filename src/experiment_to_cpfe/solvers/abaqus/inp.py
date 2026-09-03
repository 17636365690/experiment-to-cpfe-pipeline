"""Template-driven Abaqus INP generation guarded by solver readiness."""

from dataclasses import dataclass
from pathlib import Path
import re

from experiment_to_cpfe.provenance.hashing import sha256_file
from experiment_to_cpfe.schema.models import SamplePackage
from experiment_to_cpfe.schema.validation import check_solver_readiness


KNOWN_MARKERS = frozenset(
    {
        "HEADING",
        "NODES",
        "ELEMENTS",
        "MATERIALS",
        "BOUNDARY_CONDITIONS",
        "OUTPUT_REQUESTS",
    }
)
MARKER_PATTERN = re.compile(r"\{\{([A-Z_]+)\}\}")


@dataclass(frozen=True)
class SolverInputRequest:
    template_path: Path
    output_path: Path
    replacements: dict[str, str]


@dataclass(frozen=True)
class InpBuildResult:
    output_path: Path
    sha256: str
    replacements: tuple[str, ...]


def build_inp(request: SolverInputRequest) -> InpBuildResult:
    output_path = Path(request.output_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    template = Path(request.template_path).read_text(encoding="utf-8")
    if "\x00" in template:
        raise ValueError("INP template contains a null byte")

    markers = set(MARKER_PATTERN.findall(template))
    unknown = markers - KNOWN_MARKERS
    if unknown:
        raise ValueError(f"unknown INP template markers: {sorted(unknown)}")
    missing = markers - set(request.replacements)
    if missing:
        raise ValueError(f"missing INP replacements: {sorted(missing)}")

    rendered = template
    for marker in markers:
        value = request.replacements[marker]
        if not value or "\x00" in value:
            raise ValueError(f"replacement {marker} is empty or invalid")
        rendered = rendered.replace(f"{{{{{marker}}}}}", value)
    if MARKER_PATTERN.search(rendered):
        raise ValueError("unresolved INP template marker")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8", newline="\n")
    return InpBuildResult(
        output_path=output_path,
        sha256=sha256_file(output_path),
        replacements=tuple(sorted(markers)),
    )


def build_solver_input(
    sample: SamplePackage,
    template_path: Path,
    output_path: Path,
) -> InpBuildResult:
    readiness = check_solver_readiness(sample, "abaqus_cpfe")
    if not readiness.ready:
        raise ValueError("; ".join(readiness.missing))
    replacements = sample.solver_inputs.get("inp_replacements")
    if not isinstance(replacements, dict):
        raise ValueError("MISSING_SOLVER_INPUT: inp_replacements")
    return build_inp(
        SolverInputRequest(
            template_path=Path(template_path),
            output_path=Path(output_path),
            replacements={str(key): str(value) for key, value in replacements.items()},
        )
    )
