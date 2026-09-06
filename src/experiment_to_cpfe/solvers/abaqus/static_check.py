"""Conservative static checks for generated Abaqus keyword input."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StaticCheckReport:
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    counts: dict[str, int]


def _keyword(line: str) -> str:
    return line.split(",", 1)[0].strip().upper()


def static_check_inp(path: Path) -> StaticCheckReport:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    errors: list[str] = []
    warnings: list[str] = []
    counts = {
        "nodes": 0,
        "elements": 0,
        "sets": 0,
        "materials": 0,
        "steps": 0,
        "outputs": 0,
    }
    node_labels: set[int] = set()
    element_labels: set[int] = set()
    block: str | None = None
    node_blocks: list[int] = []
    element_blocks: list[int] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            keyword = _keyword(line)
            block = None
            if keyword == "*NODE":
                block = "node"
                node_blocks.append(0)
            elif keyword == "*ELEMENT":
                block = "element"
                element_blocks.append(0)
            elif keyword in {"*NSET", "*ELSET"}:
                counts["sets"] += 1
            elif keyword == "*MATERIAL":
                counts["materials"] += 1
            elif keyword == "*STEP":
                counts["steps"] += 1
            elif keyword == "*OUTPUT":
                counts["outputs"] += 1
            continue

        if block == "node":
            node_blocks[-1] += 1
            counts["nodes"] += 1
            try:
                label = int(line.split(",", 1)[0])
            except ValueError:
                errors.append(f"invalid node label: {line}")
                continue
            if label in node_labels:
                errors.append(f"duplicate node label {label}")
            node_labels.add(label)
        elif block == "element":
            element_blocks[-1] += 1
            counts["elements"] += 1
            try:
                label = int(line.split(",", 1)[0])
            except ValueError:
                errors.append(f"invalid element label: {line}")
                continue
            if label in element_labels:
                errors.append(f"duplicate element label {label}")
            element_labels.add(label)

    if not node_blocks or any(count == 0 for count in node_blocks):
        errors.append("empty node block or missing *NODE keyword")
    if not element_blocks or any(count == 0 for count in element_blocks):
        errors.append("empty element block or missing *ELEMENT keyword")
    if counts["steps"] == 0:
        errors.append("missing analysis step")
    if counts["outputs"] == 0:
        warnings.append("no explicit output request")
    from experiment_to_cpfe.schema.solver_contract import inspect_mesh, parse_keyword_blocks
    try:
        blocks = parse_keyword_blocks("\n".join(lines))
        errors.extend(inspect_mesh(blocks)[-1])
    except ValueError as exc:
        errors.append(str(exc))
    return StaticCheckReport(tuple(dict.fromkeys(errors)), tuple(warnings), counts)
