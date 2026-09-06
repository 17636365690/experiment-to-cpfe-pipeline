"""Versioned ODB field-record contract shared with standalone Abaqus Python.

Keep this module dependency-free and compatible with older Python syntax.
Native string identifiers retain their spelling; only named numeric columns
are parsed. Empty location/time columns denote not-applicable values.
"""

import math


FIELD_CONTRACT_VERSION = "1.0"

CSV_COLUMNS = (
    "step", "frame", "increment_number", "frame_value", "domain", "frame_time",
    "increment_id", "load_case", "field", "position", "instance", "element_label",
    "node_label", "integration_point", "section_point", "section_description",
    "face", "precision", "local_coord_system", "component", "value",
)

INTEGER_COLUMNS = frozenset((
    "frame", "increment_number", "element_label", "node_label",
    "integration_point", "section_point",
))
FLOAT_COLUMNS = frozenset(("frame_value", "frame_time", "value"))
NUMERIC_COLUMNS = INTEGER_COLUMNS | FLOAT_COLUMNS
OPTIONAL_NUMERIC_COLUMNS = frozenset((
    "frame_time", "element_label", "node_label", "integration_point", "section_point",
))

RECORD_IDENTITY_COLUMNS = (
    "step", "frame", "increment_id", "load_case", "field", "position",
    "instance", "element_label", "node_label", "integration_point",
    "section_point", "face", "component",
)


def parse_record(row):
    """Parse one CSV record, rejecting invalid/nonfinite numeric values."""
    record = dict(row)
    for name in NUMERIC_COLUMNS.intersection(row):
        value = row[name]
        if value == "" and name in OPTIONAL_NUMERIC_COLUMNS:
            continue
        try:
            if value is None or isinstance(value, bool):
                raise ValueError("missing numeric value")
            if name in INTEGER_COLUMNS:
                # Parsing int directly rejects fractional CSV labels, instead
                # of truncating them or quietly passing them on as strings.
                parsed = int(value)
                if not isinstance(value, str) and parsed != value:
                    raise ValueError("fractional integer value")
            else:
                parsed = float(value)
                if math.isnan(parsed) or math.isinf(parsed):
                    raise ValueError("nonfinite numeric value")
            record[name] = parsed
        except (ValueError, TypeError, OverflowError):
            raise ValueError("invalid numeric field column: " + name)
    return record


def record_identity(row):
    """Return the stored location/component identity independently of value."""
    return tuple(row.get(name) for name in RECORD_IDENTITY_COLUMNS)
