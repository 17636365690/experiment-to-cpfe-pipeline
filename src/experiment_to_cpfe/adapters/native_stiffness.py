"""Explicit voxel/CSV correspondence with pinned loader evidence; no label scaling."""

import csv
from pathlib import PurePosixPath
from string import Formatter

import numpy as np

from experiment_to_cpfe.adapters.native_numeric import read_numeric


def _template(template, field, value):
    if not isinstance(template, str) or not template:
        raise ValueError("pairing requires explicit templates")
    if any(name != field or spec or conversion for _, name, spec, conversion in Formatter().parse(template) if name is not None):
        raise ValueError("pairing template has unsupported fields/format specifiers")
    return template.format(**{field: value})


def read_stiffness(files, options):
    if set(options) - {"voxel_file", "labels_file", "columns", "pairing", "max_bytes"}:
        raise ValueError("unknown stiffness options")
    voxel_key, labels_key = options.get("voxel_file"), options.get("labels_file")
    if voxel_key not in files or labels_key not in files:
        raise ValueError("voxel_file and labels_file must be declared")
    limit = options.get("max_bytes", 64 * 1024 * 1024)
    if type(limit) is not int or limit <= 0 or files[labels_key].path.stat().st_size > limit:
        raise ValueError("label file exceeds byte limit")
    with files[labels_key].path.open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        rows = list(reader)
    columns = options.get("columns")
    if (not isinstance(columns, (list, tuple)) or not columns or len(set(columns)) != len(columns)
            or len(set(header)) != len(header) or not set(columns) <= set(header)):
        raise ValueError("explicit unique stiffness columns must exist in header")
    if not rows or any(len(row) != len(header) for row in rows):
        raise ValueError("malformed or empty stiffness table")
    column_indices = [header.index(c) for c in columns]
    labels = np.array([[float(row[i]) for i in column_indices] for row in rows])
    if not np.isfinite(labels).all():
        raise ValueError("stiffness labels must be finite")
    voxel, voxel_meta = read_numeric(files[voxel_key].path, {"format": "npy", "max_bytes": limit})
    arrays = {"voxel_channels": voxel, "stiffness_labels": labels}
    descriptions = {"voxel_channels": {**voxel_meta, "parent_file": voxel_key},
                    "stiffness_labels": {"parent_file": labels_key, "columns": list(columns),
                        "source_row_count": len(rows), "unit_conversion": "none",
                        "losses": ["explicit label column selection; no implicit tensor reorder or shear scaling"]}}
    pairing = options.get("pairing")
    blockers = []
    if pairing is None:
        blockers.append("row-to-voxel pairing is unresolved; no sample IDs assigned")
    else:
        required = {"row_index", "index_base", "sample_template", "relative_path_template", "expected_rows", "loader_file", "evidence"}
        if not isinstance(pairing, dict) or set(pairing) != required:
            raise ValueError("pairing requires explicit row, index base, templates, count and loader evidence")
        row, base = pairing["row_index"], pairing["index_base"]
        if (type(row) is not int or not 0 <= row < len(rows) or type(base) is not int
                or pairing["expected_rows"] != len(rows) or pairing["loader_file"] not in files
                or not isinstance(pairing["evidence"], str) or not pairing["evidence"].strip()):
            raise ValueError("invalid pairing row/count/loader evidence")
        sample_id = _template(pairing["sample_template"], "index", row + base)
        relative = PurePosixPath(_template(pairing["relative_path_template"], "sample", sample_id))
        if relative.is_absolute() or not relative.parts or any(p in {".", ".."} for p in relative.parts) or "\\" in str(relative):
            raise ValueError("pairing relative_path_template must be a safe relative path")
        actual = files[voxel_key].path.parts
        if tuple(actual[-len(relative.parts):]) != relative.parts:
            raise ValueError("voxel filename does not match the declared source-row pairing")
        arrays["stiffness_labels"] = labels[row:row + 1]
        arrays["sample_ids"] = np.array([sample_id])
        descriptions["stiffness_labels"].update(source_data_row=row, pairing=pairing)
        descriptions["sample_ids"] = {"parent_file": labels_key, "pairing": pairing, "losses": []}
    return arrays, descriptions, blockers
