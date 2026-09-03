"""JSON serialization for small normalized sample packages."""

import json
from pathlib import Path

import numpy as np

from experiment_to_cpfe.assets.models import AssetRef
from experiment_to_cpfe.schema.models import SampleMetadata, SamplePackage


def dump_sample_json(sample: SamplePackage, path: Path) -> None:
    """Write a deterministic JSON representation of a small sample package."""

    arrays = {
        name: {
            "dtype": array.dtype.name,
            "shape": list(array.shape),
            "data": array.tolist(),
        }
        for name, array in sample.arrays.items()
    }
    payload = {
        "metadata": sample.metadata.model_dump(mode="json"),
        "tables": sample.tables,
        "arrays": arrays,
        "assets": [asset.model_dump(mode="json") for asset in sample.assets],
        "solver_inputs": sample.solver_inputs,
    }

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_sample_json(path: Path) -> SamplePackage:
    """Load and validate a sample package written by :func:`dump_sample_json`."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    arrays: dict[str, np.ndarray] = {}
    for name, encoded in payload["arrays"].items():
        array = np.asarray(encoded["data"], dtype=encoded["dtype"])
        expected_shape = tuple(encoded["shape"])
        if array.shape != expected_shape:
            raise ValueError(
                f"array {name!r} shape {array.shape} does not match "
                f"declared shape {expected_shape}"
            )
        arrays[name] = array

    return SamplePackage(
        metadata=SampleMetadata.model_validate(payload["metadata"]),
        tables=payload["tables"],
        arrays=arrays,
        assets=tuple(AssetRef.model_validate(item) for item in payload["assets"]),
        solver_inputs=payload.get("solver_inputs", {}),
    )
