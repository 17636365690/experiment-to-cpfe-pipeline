"""Conservative target lineage checks with explicit native-table specimen scopes."""

from dataclasses import dataclass, field

from experiment_to_cpfe.datasets.training_config import TableColumn


def _overlap(left, right):
    if left is None or right is None:
        return True
    return left["specimen"] == right["specimen"] or bool(
        {tuple(row) for row in left["records"]} & {tuple(row) for row in right["records"]})


@dataclass
class TargetSourceIndex:
    by_digest: dict = field(default_factory=dict)
    by_uri: dict = field(default_factory=dict)

    def register(self, asset, split, sample_id, partition=None):
        digest = asset.sha256.lower() if asset.sha256 else None
        uri_records = self.by_uri.setdefault(asset.uri, {})
        if digest is None:
            candidates = [record for records in uri_records.values() for record in records]
        else:
            candidates = self.by_digest.get(digest, []) + uri_records.get(None, [])
        for previous_split, previous_sample, previous_partition in candidates:
            if previous_split != split and _overlap(previous_partition, partition):
                raise ValueError(
                    f"target source {asset.asset_id!r} reused across splits: "
                    f"sample {previous_sample!r} ({previous_split}) and {sample_id!r} ({split})")
        record = (split, sample_id, partition)
        uri_records.setdefault(digest, []).append(record)
        if digest is not None:
            self.by_digest.setdefault(digest, []).append(record)


def _partition(sample, asset, selector, positions, declaration, group):
    if not isinstance(selector, TableColumn):
        raise ValueError("target specimen scope requires a native table target")
    metadata = asset.descriptive_metadata
    block = metadata.get("block")
    if (asset.parent_asset_id is not None or asset.format not in {"csv", "txt", "xlsx"}
            or not isinstance(block, dict) or metadata.get("table_name") != selector.table
            or declaration.column not in metadata.get("column_map", {})):
        raise ValueError("target specimen column must be mapped from a native source block")
    receipts = [a for a in sample.assets if a.parent_asset_id == asset.asset_id
                and a.format == "normalized-table-json" and a.conversion is not None
                and a.conversion.hash_scope == "logical_payload" and a.conversion.source_hash_verified
                and a.descriptive_metadata.get("table_key") == selector.table]
    if not asset.sha256 or not receipts:
        raise ValueError("target specimen scope requires a verified native table conversion receipt")
    records = []
    for position in positions:
        row = sample.tables[selector.table][position]
        if row.get(declaration.column) != group:
            raise ValueError("target specimen identity must equal the declared group in every selected row")
        number, sheet = row.get("source_row"), row.get("source_sheet", "")
        if type(number) is not int or number < 1 or sheet != (block.get("sheet") or ""):
            raise ValueError("target specimen requires original source row and worksheet")
        if not block.get("start_marker") and (
            number < block["data_start_row"] or
            (block.get("data_end_row") is not None and number >= block["data_end_row"])
        ):
            raise ValueError("target specimen source row is outside the recorded native block")
        records.append([sheet, number])
    if len({tuple(record) for record in records}) != len(records):
        raise ValueError("target specimen repeats an original source record")
    return {"asset_id": asset.asset_id, "specimen": group, "records": records,
            "evidence": declaration.evidence, "column": declaration.column}


def register_target_sources(sample, column_record, selector, declaration, split, group, index):
    assets = {asset.asset_id: asset for asset in sample.assets}
    partitions = []
    for asset_id in dict.fromkeys(column_record["asset_ids"]):
        asset = assets[asset_id]
        meaning = asset.descriptive_metadata.get("meaning", {})
        if meaning.get("role") == "target":
            if meaning.get("split") != split or meaning.get("group_id") != group:
                raise ValueError(f"target asset {asset_id!r} has conflicting declared group/split")
        partition = None
        if declaration is not None:
            positions = [row for row, bound in zip(column_record["source_rows"], column_record["asset_ids"])
                         if bound == asset_id]
            partition = _partition(sample, asset, selector, positions, declaration, group)
            partitions.append(partition)
        while asset.parent_asset_id is not None:
            asset = assets[asset.parent_asset_id]
        index.register(asset, split, sample.metadata.sample_id, partition)
    return partitions
