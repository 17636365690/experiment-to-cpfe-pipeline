"""Text EBSD adapter with explicit semantic column mapping."""

from pathlib import Path
from io import StringIO

import numpy as np
import pandas as pd


def load_ebsd_text(
    path: Path,
    profile: str,
    column_map: dict[str, str],
) -> list[dict[str, object]]:
    """Load configured EBSD columns without assuming a vendor convention."""

    if not column_map:
        raise ValueError("explicit column mapping is required for EBSD text")
    if not profile:
        raise ValueError("an EBSD text profile is required")

    if profile == "ang":
        if any(not str(source).isdigit() for source in column_map.values()):
            raise ValueError("ANG profile requires explicit zero-based column indices")
        frame = pd.read_csv(Path(path), sep=r"\s+", header=None, comment="#", encoding="utf-8")
        frame.columns = [str(column) for column in frame.columns]
    elif profile == "ctf":
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
        mapped = set(column_map.values())
        headers = [index for index, line in enumerate(lines) if mapped <= set(line.split())]
        if len(headers) != 1:
            raise ValueError("CTF profile requires one unambiguous mapped data header")
        frame = pd.read_csv(StringIO("\n".join(lines[headers[0]:])), sep=r"\s+")
    elif profile == "generic":
        frame = pd.read_csv(Path(path), sep=None, engine="python", comment="#", encoding="utf-8")
    else:
        raise ValueError(f"unsupported EBSD text profile: {profile}")
    missing = sorted(set(column_map.values()) - set(frame.columns))
    if missing:
        raise ValueError(f"mapped EBSD columns are missing: {missing}")
    values = frame.loc[:, list(column_map.values())].to_numpy(dtype=float)
    if not values.size or not np.isfinite(values).all():
        raise ValueError("EBSD values must be nonempty and finite")
    return [
        {
            target: row[source]
            for target, source in column_map.items()
        }
        for row in frame.to_dict(orient="records")
    ]
