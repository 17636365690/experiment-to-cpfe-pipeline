"""DIC/DVC point-field and regular-grid adapters."""

from pathlib import Path

import numpy as np
import pandas as pd


def _required(config: dict[str, object], name: str) -> object:
    value = config.get(name)
    if value is None or value == {} or value == [] or value == "":
        raise ValueError(f"{name} is required")
    return value


def load_point_field(
    path: Path,
    config: dict[str, object],
) -> tuple[dict[str, object], np.ndarray]:
    """Load an irregular point field with explicit coordinates and units."""

    format_name = str(_required(config, "format"))
    coordinate_columns = tuple(_required(config, "coordinate_columns"))
    field_columns = tuple(_required(config, "field_columns"))
    units = dict(_required(config, "units"))
    coordinate_frame = str(_required(config, "coordinate_frame"))
    axis_order = tuple(_required(config, "axis_order"))
    columns = coordinate_columns + field_columns
    if len(set(columns)) != len(columns):
        raise ValueError("coordinate and field columns must be unique and disjoint")
    if len(axis_order) != 2 or len(set(axis_order)) != 2:
        raise ValueError("point-field axis_order must describe two unique array axes")
    missing_units = sorted(set(columns) - set(units))
    if missing_units:
        raise ValueError(f"units are missing for columns: {missing_units}")
    if any(not str(units[column]).strip() for column in columns):
        raise ValueError("point-field units must be nonempty")

    if format_name not in {"csv", "txt"}:
        raise ValueError(f"unsupported point-field format: {format_name}")
    delimiter = str(_required(config, "delimiter"))
    frame = pd.read_csv(Path(path), sep=delimiter, encoding="utf-8")
    missing_columns = sorted(set(columns) - set(frame.columns))
    if missing_columns:
        raise ValueError(f"point-field columns are missing: {missing_columns}")
    values = frame.loc[:, list(columns)].to_numpy(dtype=float)
    if not values.size or not np.isfinite(values).all():
        raise ValueError("point-field values must be nonempty and finite")
    metadata = {
        "columns": columns,
        "units": units,
        "coordinate_frame": coordinate_frame,
        "axis_order": axis_order,
        "dtype": values.dtype.name,
        "shape": values.shape,
        "native_layout": "delimited_point_records",
        "lossy_transformations": tuple(config.get("lossy_transformations", ())),
    }
    return metadata, values
