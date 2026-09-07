"""Extract scalar columns with explicit identity, unit and asset bindings."""

from dataclasses import dataclass
import json

import numpy as np

from experiment_to_cpfe.datasets.training_config import ArrayColumn, TableColumn


@dataclass
class SelectedColumn:
    values: np.ndarray
    ids: list[str]
    source_rows: list[int]
    asset_ids: list[str]


def _identity(parts) -> str:
    normalized = []
    for part in parts:
        if isinstance(part, np.generic):
            part = part.item()
        if isinstance(part, bytes):
            part = part.decode("utf-8")
        if type(part) not in (int, str) or (isinstance(part, str) and not part.strip()):
            raise ValueError("row identity requires integer or nonblank string components")
        normalized.append(part)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _table(sample, selector: TableColumn) -> SelectedColumn:
    if selector.table not in sample.tables:
        raise ValueError(f"missing table {selector.table!r}")
    assets = {asset.asset_id: asset for asset in sample.assets}
    values, ids, positions, asset_ids = [], [], [], []
    for index, row in enumerate(sample.tables[selector.table]):
        missing = set(selector.where) - row.keys()
        if missing:
            raise ValueError(f"row {index}: missing filter fields {sorted(missing)}")
        if any(row[key] != value for key, value in selector.where.items()):
            continue
        required = {selector.column, *selector.id_columns}
        if required - row.keys():
            raise ValueError(f"row {index}: missing fields {sorted(required - row.keys())}")
        source_id = row.get("source_asset_id", selector.asset_id)
        if selector.asset_id is not None and source_id != selector.asset_id:
            raise ValueError(f"row {index}: configured source asset conflicts with row binding")
        asset = assets.get(source_id)
        if asset is None:
            raise ValueError(f"row {index}: missing source asset {source_id!r}; supply row binding or asset_id")
        if ("source_kind" in row or "source_asset_id" in row) and row.get("source_kind") != asset.source_kind.value:
            raise ValueError(f"row {index}: source_kind conflicts with asset {asset.asset_id!r}")
        bound_table = asset.descriptive_metadata.get("table_name", asset.descriptive_metadata.get("table_key"))
        if bound_table is not None and bound_table != selector.table:
            raise ValueError(f"row {index}: source asset is bound to table {bound_table!r}")
        unit_key = selector.unit_key or selector.column
        units = asset.descriptive_metadata.get("normalized_units", asset.units)
        if selector.column == "value" and "field" in row:
            unit_key = row["field"]
            if selector.unit_key is not None and selector.unit_key != unit_key:
                raise ValueError(f"row {index}: unit_key differs from field {unit_key!r}")
            if row.get("unit") != selector.source_unit:
                raise ValueError(f"row {index}: field unit conflicts with source_unit")
        elif isinstance(units, dict) and selector.column in units and units[selector.column] != selector.source_unit:
            raise ValueError(f"row {index}: source column unit conflicts with source_unit")
        if not isinstance(units, dict) or units.get(unit_key) != selector.source_unit:
            raise ValueError(f"row {index}: unit for {unit_key!r} disagrees with source_unit {selector.source_unit!r}")
        value = row[selector.column]
        if type(value) not in (int, float):
            raise ValueError(f"row {index}: {selector.column!r} must be a real number")
        values.append(value)
        ids.append(_identity([row[key] for key in selector.id_columns]))
        positions.append(index)
        asset_ids.append(asset.asset_id)
    return SelectedColumn(np.asarray(values, dtype=float), ids, positions, asset_ids)


def _array(sample, selector: ArrayColumn) -> SelectedColumn:
    assets = {asset.asset_id: asset for asset in sample.assets}
    asset = assets.get(selector.asset_id)
    if asset is None or asset.descriptive_metadata.get("array_key") != selector.array:
        raise ValueError(f"source asset {selector.asset_id!r} must bind array_key {selector.array!r}")
    if selector.array not in sample.arrays or selector.ids not in sample.arrays:
        raise ValueError(f"missing array or identity array: {selector.array!r}, {selector.ids!r}")
    array = sample.arrays[selector.array]
    if selector.row_axis >= array.ndim:
        raise ValueError("row axis is outside array dimensions")
    other_axes = [axis for axis in range(array.ndim) if axis != selector.row_axis]
    if len(selector.component) != len(other_axes) or any(index >= array.shape[axis] for axis, index in zip(other_axes, selector.component)):
        raise ValueError("component indices must select exactly one scalar per row")
    indexer = [slice(None) if axis == selector.row_axis else selector.component[other_axes.index(axis)] for axis in range(array.ndim)]
    values = array[tuple(indexer)]
    if values.dtype.kind not in "iuf":
        raise ValueError("array values must have a real numeric dtype")
    identities = sample.arrays[selector.ids]
    if identities.ndim != 1 or len(identities) != len(values):
        raise ValueError("identity array length must match selected row axis")
    meaning = asset.descriptive_metadata.get("meaning", {})
    if meaning.get("entity_ids") and (meaning["entity_ids"] != selector.ids or meaning.get("entity_axis") != selector.row_axis):
        raise ValueError("identity selection conflicts with declared entity axis/IDs")
    unit_key = selector.unit_key or selector.array
    for axis_name, components in meaning.get("components", {}).items():
        axis = asset.axis_order.index(axis_name)
        if axis not in other_axes or unit_key != components[selector.component[other_axes.index(axis)]]:
            if not meaning.get("unit"):
                raise ValueError("unit_key conflicts with selected component semantics")
    if asset.units.get(unit_key) != selector.source_unit:
        raise ValueError(f"unit for {unit_key!r} disagrees with source_unit {selector.source_unit!r}")
    return SelectedColumn(values.astype(float), [_identity([value]) for value in identities],
                          list(range(len(values))), [asset.asset_id] * len(values))


def select_column(sample, selector) -> SelectedColumn:
    selected = _table(sample, selector) if isinstance(selector, TableColumn) else _array(sample, selector)
    if not selected.ids:
        raise ValueError("column selection is empty")
    if len(set(selected.ids)) != len(selected.ids):
        raise ValueError("duplicate row identity; select a complete compound identity or filter")
    if not np.isfinite(selected.values).all():
        raise ValueError("column requires finite values")
    if selector.conversion:
        with np.errstate(over="ignore", invalid="ignore"):
            selected.values = selected.values * selector.conversion.factor + selector.conversion.offset
        if not np.isfinite(selected.values).all():
            raise ValueError("conversion produced nonfinite values")
    return selected
