"""Small declared input generators; no solver or experimental evidence."""

import hashlib
import json

import numpy as np

from experiment_to_cpfe.datasets.hdf5 import write_hdf5
from experiment_to_cpfe.assets.models import DataLayer, SourceKind


def training_collection(root, make_sample, layout="table", count=5):
    root.mkdir(parents=True, exist_ok=True)
    inputs = []
    samples = []
    for name, parameter, split in zip("abcd", (1., 2., 1.5, 1.7),
                                     ("train", "train", "validation", "test")):
        sample = make_sample()
        sample.metadata.sample_id = name
        sample.metadata.experiment_id = "experiment-" + name
        sample.metadata.sources = ()
        x = np.linspace(0, 1, count)
        ids = np.array([f"r{i}" for i in range(count)])
        raw = sample.assets[0].model_copy(update={
            "asset_id": "raw", "source_kind": SourceKind.INPUT, "layer": DataLayer.RAW,
            "uri": "synthetic:" + name, "license": "Apache-2.0",
            "sha256": hashlib.sha256((name + str(parameter)).encode()).hexdigest(),
            "units": {"eps": "1", "modulus": "Pa", "load": "kPa"},
            "descriptive_metadata": {"table_name": "measured_observations"},
        })
        sample.tables = {}
        sample.arrays = {}
        sample.assets = (raw,)
        if layout == "table":
            sample.tables = {"measured_observations": [
                {"increment_id": str(ids[i]), "phase": phase,
                 "eps": float(x[i]), "modulus": parameter, "load": float(x[i]*parameter/1000),
                 "source_asset_id": "raw", "source_kind": "input"}
                for phase, order in (("input", range(count)), ("response", reversed(range(count))))
                for i in order
            ]}
        else:
            sample.arrays = {"channels": np.vstack([x, np.full(count, parameter)]),
                             "response": (x*parameter/1000)[::-1],
                             "ids": ids, "response_ids": ids[::-1].copy()}
            sample.assets += tuple(raw.model_copy(update={
                "asset_id": key, "parent_asset_id": "raw", "format": "numpy-array",
                "layer": DataLayer.CURATED, "uri": "hdf5:/derived/arrays/" + key,
                "shape": array.shape, "axis_order": ("component", "row") if array.ndim == 2 else ("row",),
                "descriptive_metadata": {"array_key": key}, "sha256": None,
            }) for key, array in sample.arrays.items() if key in {"channels", "response"})
        write_hdf5(sample, root / f"{name}.h5", {"generator": "synthetic product", "case": name})
        samples.append(sample)
        inputs.append({"path": f"{name}.h5", "sample_id": name, "layout": layout, "split": split})
    if layout == "table":
        def column(key, phase, unit):
            return {"kind": "table", "table": "measured_observations", "column": key,
                    "id_columns": ["increment_id"], "where": {"phase": phase}, "source_unit": unit}
        columns = {"strain": column("eps", "input", "1"),
                   "modulus": column("modulus", "input", "Pa"),
                   "stress": column("load", "response", "kPa")}
    else:
        def column(array, ids, component, unit, key, axis=0):
            return {"kind": "array", "array": array, "asset_id": array, "ids": ids,
                    "row_axis": axis, "component": component, "source_unit": unit, "unit_key": key}
        columns = {"strain": column("channels", "ids", [0], "1", "eps", 1),
                   "modulus": column("channels", "ids", [1], "Pa", "modulus", 1),
                   "stress": column("response", "response_ids", [], "kPa", "load")}
    columns["stress"]["conversion"] = {"factor": 1000., "offset": 0., "reason": "kPa to Pa"}
    config = {"version": 1, "features": [{"name": "strain", "unit": "1"}, {"name": "modulus", "unit": "Pa"}],
              "target": {"name": "stress", "unit": "Pa"}, "group_by": "sample_id",
              "grouping_evidence": "independent synthetic parameter cases",
              "layouts": {layout: {"columns": columns, "alignment_evidence": "same synthetic increment IDs"}},
              "inputs": inputs}
    return config, samples


def replace_sample(root, sample):
    path = root / (sample.metadata.sample_id + ".h5")
    path.unlink()
    write_hdf5(sample, path, {"generator": "mutated synthetic fixture"})


def save_config(path, config):
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path
