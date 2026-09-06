"""Offline native inputs enter the existing containers with explicit semantics."""

from pathlib import Path
import json

import numpy as np
import pytest


def test_public_native_example_inspects_and_enters_complete_sample(tmp_path):
    import yaml
    from experiment_to_cpfe.cli import main
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.adapters.native_models import NativeImportConfig
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5, read_hdf5
    from experiment_to_cpfe.datasets.package import write_npz
    from experiment_to_cpfe.schema.validation import validate_sample, ValidationPolicy
    example = Path("examples/synthetic_native/imports.yaml").resolve()
    assert main(["adapt", "--config", str(example), "--run-dir", str(tmp_path / "inspect")]) == 0
    config = yaml.safe_load(example.read_text())
    for source in config["imports"][0]["files"].values():
        source["path"] = example.parent / source["path"]
    imported = NativeImportConfig.model_validate(config["imports"][0])
    pipeline = load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml"))
    sample = assemble_sample(pipeline.model_copy(update={"imports": (imported,)}))
    assert validate_sample(sample, ValidationPolicy()).passed
    path = tmp_path / "sample.h5"
    digest = write_hdf5(sample, path)
    restored = read_hdf5(path)
    assert restored.arrays["point_displacements"].tolist() == [[0,0,0,0],[1,0,0.1,0],[0,1,0,0.2],[1,1,0.1,0.2]]
    write_npz(path, tmp_path / "sample.npz", digest)
    with np.load(tmp_path / "sample.npz", allow_pickle=False) as payload:
        assert np.array_equal(payload["point_displacements"], restored.arrays["point_displacements"])
    report = json.loads((tmp_path / "inspect/reports/native-adapters.json").read_text())
    assert report["imports"][0]["solver_readiness"] == "not_evaluated"


def test_graph_arrays_survive_native_to_hdf5_npz_with_target_provenance(tmp_path):
    from experiment_to_cpfe.adapters.native_models import NativeImportConfig
    from experiment_to_cpfe.adapters.native import decode_native, promote_native
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5, read_hdf5
    from experiment_to_cpfe.datasets.package import write_npz
    files = {}
    for key, content in {"adj": "0 1\n1 0\n", "feat": "19 2\n9001 4\n", "target": "0 0\n1 0.1\n"}.items():
        path = tmp_path / f"{key}.txt"
        path.write_text(content)
        files[key] = dict(path=path, format="txt", source_kind="simulated", license="synthetic", native_layout="synthetic graph")
    def meta(quantity, axes, role, **extra):
        return dict(quantity=quantity, axes=axes, role=role, unit="1", source_kind="simulated", evidence="synthetic fixture", **extra)
    config = dict(import_id="graph", profile="grain_graph", modality="grain_graph", files=files,
        options=dict(adjacency_file="adj", features_file="feat", targets_file="target", id_column=0, id_dtype="int64",
                     feature_columns=[1], directed=False, self_loops="preserve", padding_ids=[], zero_node_policy="keep",
                     node_order_evidence="synthetic matrix rows match feature rows"),
        meanings={"graph_node_ids": meta("node identifier", ["node"], "id", identity_scope="one synthetic structure"),
            "graph_node_features": meta("dimensionless synthetic size", ["node", "feature"], "features", components={"feature": ["size"]},
                                        entity_ids="graph_node_ids", identity_scope="one synthetic structure"),
            "graph_edge_index": meta("zero-based node row endpoints", ["endpoint", "edge"], "index"),
            "graph_targets": meta("synthetic response", ["load", "component"], "target", components={"component": ["field", "response"]},
                                  target_origin="synthetic simulated response", group_id="structure-A", split="train")})
    imported = NativeImportConfig.model_validate(config)
    draft = decode_native(imported)
    assert not draft.blockers
    sample = assemble_sample(load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml")).model_copy(update={"imports": (imported,)}))
    path = tmp_path / "sample.h5"
    digest = write_hdf5(sample, path)
    restored = read_hdf5(path)
    assert restored.arrays["graph_node_ids"].tolist() == [19, 9001]
    assert restored.arrays["graph_edge_index"].tolist() == [[0, 1], [1, 0]]
    write_npz(path, tmp_path / "sample.npz", digest)
    with np.load(tmp_path / "sample.npz", allow_pickle=False) as data:
        target = next(a for a in json.loads(data["__asset_manifest_json__"].item()) if a["asset_id"] == "graph:graph_targets:normalized")
        assert target["descriptive_metadata"]["meaning"]["target_origin"] == "synthetic simulated response"
        assert target["descriptive_metadata"]["meaning"]["group_id"] == "structure-A"
    config["meanings"]["graph_targets"]["role"] = "value"
    invalid = decode_native(NativeImportConfig.model_validate(config))
    assert any("target" in b for b in invalid.blockers)
    with pytest.raises(ValueError, match="blocked"):
        promote_native(invalid)
