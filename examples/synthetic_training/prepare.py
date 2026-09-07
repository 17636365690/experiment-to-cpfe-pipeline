"""Generate two small canonical collections and their scalar regression recipes."""

import argparse
import json
from pathlib import Path

import numpy as np
import yaml

from experiment_to_cpfe.assets.models import AssetRef, ConversionRecord
from experiment_to_cpfe.assets.registry import array_payload_sha256, table_payload_sha256
from experiment_to_cpfe.datasets.hdf5 import write_hdf5
from experiment_to_cpfe.provenance.hashing import sha256_file
from experiment_to_cpfe.schema.models import SampleMetadata, SamplePackage


def prepare(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    for layout in ("table", "array"):
        root = output_dir / layout
        root.mkdir()
        inputs = []
        for name, gain, split in zip("abcd", (1., 2., 1.5, 1.7), ("train", "train", "validation", "test")):
            x = np.linspace(0, 1, 31)
            source = root / f"{name}.json"
            source.write_text(json.dumps({"generator": "synthetic y = x * gain", "case": name,
                                          "gain": gain, "x": x.tolist(), "y": (gain*x).tolist()}), encoding="utf-8")
            raw = AssetRef(asset_id="source", parent_asset_id=None, modality="table", format="json",
                uri=str(source.resolve()), source_kind="input", layer="raw",
                units={"extension": "mm", "stiffness": "N/mm", "force": "kN"} if layout == "table" else {},
                coordinate_frame=None, axis_order=("row",), dtype=None, shape=(31,),
                native_layout="synthetic generator JSON", sha256=sha256_file(source), license="Apache-2.0",
                lossy_transformations=(), descriptive_metadata={"table_name": "measured_observations"} if layout == "table" else {})
            metadata = SampleMetadata(sample_id=f"{layout}-{name}", experiment_id=f"generated-{layout}-{name}",
                microstructure_id="not-applicable-scalar-generator", load_path_id="synthetic-input-sequence", schema_version="0.1",
                coordinate={"name": "synthetic", "axes": ["x"], "units": "mm"},
                unit_system={"length": "mm", "force": "N"} if layout == "table" else {"signal": "V"},
                tensor_order=["scalar"], orientation={"representation": "not_applicable", "reason": "synthetic scalar regression"},
                sources=[{"kind": "input", "uri": str(source.resolve()), "sha256": raw.sha256, "role": "synthetic generator"}])
            assets, tables, arrays = [raw], {}, {}
            if layout == "table":
                rows = [{"increment": i, "extension": float(value), "stiffness": gain, "force": float(value*gain/1000),
                         "source_asset_id": "source", "source_kind": "input"} for i, value in enumerate(x)]
                tables["measured_observations"] = rows
                digest = table_payload_sha256(rows)
                assets.append(AssetRef(asset_id="curve", parent_asset_id="source", modality="table", format="normalized-table-json",
                    uri="hdf5:/measured/measured_observations", source_kind="input", layer="curated", units=raw.units,
                    coordinate_frame=None, axis_order=("row",), dtype=None, shape=(31,), native_layout="normalized generator rows",
                    sha256=digest, license="Apache-2.0", lossy_transformations=("generator expanded into scalar columns",),
                    conversion=ConversionRecord(original_format="json", target_format="normalized-table-json", source_sha256=raw.sha256,
                        hash_scope="logical_payload", target_payload_sha256=digest, source_hash_verified=True),
                    descriptive_metadata={"table_key": "measured_observations", "row_source_asset_id": "source",
                                          "payload_hash_encoding": "normalized-table-json-v1"}))
            else:
                arrays = {"channels": np.vstack([x, np.full(31, gain)]), "amplitude": (x*gain)[::-1].copy(),
                          "ids": np.arange(31), "response_ids": np.arange(31)[::-1].copy()}
                for key, array in arrays.items():
                    digest = array_payload_sha256(array)
                    units = {"phase": "1", "gain": "V"} if key == "channels" else {key: "V" if key == "amplitude" else "1"}
                    assets.append(AssetRef(asset_id=key, parent_asset_id="source", modality="table", format="numpy-array",
                        uri=f"hdf5:/derived/arrays/{key}", source_kind="input", layer="curated", units=units,
                        coordinate_frame=None, axis_order=("channel", "row") if key == "channels" else ("row",),
                        dtype=array.dtype.str, shape=array.shape, native_layout="explicit synthetic array", sha256=digest,
                        license="Apache-2.0", lossy_transformations=("generator expanded to selected array",),
                        conversion=ConversionRecord(original_format="json", target_format="numpy-array", source_sha256=raw.sha256,
                            hash_scope="logical_payload", target_payload_sha256=digest, source_hash_verified=True),
                        descriptive_metadata={"array_key": key}))
            write_hdf5(SamplePackage(metadata, tables, arrays, tuple(assets)), root / f"{name}.h5",
                       {"generator": "synthetic y = x * gain", "source": str(source.resolve()), "split": split})
            inputs.append({"path": f"{name}.h5", "sample_id": metadata.sample_id, "layout": layout, "split": split})
        if layout == "table":
            quantities = {"extension": "mm", "stiffness": "N/mm", "force": "N"}
            columns = {key: {"kind": "table", "table": "measured_observations", "column": key,
                            "id_columns": ["increment"], "source_unit": "kN" if key == "force" else unit}
                       for key, unit in quantities.items()}
            columns["force"]["conversion"] = {"factor": 1000, "reason": "kN to N"}
        else:
            quantities = {"phase": "1", "gain": "V", "amplitude": "V"}
            columns = {key: {"kind": "array", "array": "channels", "asset_id": "channels", "ids": "ids",
                            "row_axis": 1, "component": [index], "unit_key": key, "source_unit": quantities[key]}
                       for index, key in enumerate(("phase", "gain"))}
            columns["amplitude"] = {"kind": "array", "array": "amplitude", "asset_id": "amplitude",
                                    "ids": "response_ids", "source_unit": "V"}
        names = list(quantities)
        config = {"version": 1, "features": [{"name": key, "unit": quantities[key]} for key in names[:2]],
                  "target": {"name": names[2], "unit": quantities[names[2]]}, "group_by": "sample_id",
                  "grouping_evidence": "one independent synthetic parameter case per sample",
                  "layouts": {layout: {"columns": columns, "alignment_evidence": "same integer generator index"}}, "inputs": inputs}
        (root / "build.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    prepare(parser.parse_args().output_dir)
