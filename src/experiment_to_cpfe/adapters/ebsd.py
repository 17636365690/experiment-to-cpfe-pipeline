"""Text EBSD adapter with explicit semantic column mapping."""

from pathlib import Path

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

    frame = pd.read_csv(
        Path(path),
        sep=None,
        engine="python",
        comment="#",
        encoding="utf-8",
    )
    missing = sorted(set(column_map.values()) - set(frame.columns))
    if missing:
        raise ValueError(f"mapped EBSD columns are missing: {missing}")
    return [
        {
            target: row[source]
            for target, source in column_map.items()
        }
        for row in frame.to_dict(orient="records")
    ]
