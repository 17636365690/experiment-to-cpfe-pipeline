"""Partial decoding is useful evidence, but must never bypass semantic gates."""

from pathlib import Path
import json

import h5py
import numpy as np
import pytest


def native(path, meanings=None):
    from experiment_to_cpfe.adapters.native_models import NativeImportConfig
    return NativeImportConfig.model_validate({
        "import_id": "scan", "profile": "numeric", "modality": "voxel_grid",
        "files": {"data": {"path": path, "format": "npy", "source_kind": "inferred",
                           "license": "synthetic", "native_layout": "synthetic channel array"}},
        "selections": {"channels": {"file": "data", "selector": {}}},
        "meanings": meanings or {},
    })


def meaning():
    return dict(quantity="synthetic vector field", unit="mm", axes=["x", "y", "channel"],
                source_kind="inferred", evidence="synthetic fixture definition", role="field",
                components={"channel": ["u", "v"]},
                spatial={"axes": ["x", "y"], "origin": [0, 0], "spacing": [2, 3],
                         "unit": "mm", "coordinate_frame": "synthetic sample"})


@pytest.fixture
def values(tmp_path):
    path = tmp_path / "v.npy"
    np.save(path, np.arange(12).reshape(2, 3, 2))
    return path


def test_unknown_semantics_remain_draft_and_cannot_be_promoted(values):
    from experiment_to_cpfe.adapters.native import decode_native, promote_native
    draft = decode_native(native(values))
    assert draft.arrays["channels"].shape == (2, 3, 2)
    assert draft.blockers
    assert draft.report()["physical_validation"] == "not_performed"
    with pytest.raises(ValueError, match="semantic|blocked"):
        promote_native(draft)


@pytest.mark.parametrize("change, reason", [
    ({"unit": "unknown"}, "unit"), ({"axes": ["x", "y"]}, "axes"),
    ({"components": {"channel": ["u"]}}, "component"),
    ({"spatial": {"axes": ["x", "y", "channel"], "origin": [0, 0], "spacing": [1, 1], "unit": "mm", "coordinate_frame": "sample"}}, "spatial"),
    ({"role": "tensor", "reference_state": None}, "tensor|reference"),
    ({"role": "orientation", "orientation": None}, "orientation"),
])
def test_shape_cannot_supply_missing_physical_conventions(values, change, reason):
    from experiment_to_cpfe.adapters.native import decode_native
    meta = meaning()
    meta.update(change)
    draft = decode_native(native(values, {"channels": meta}))
    assert any(__import__("re").search(reason, item) for item in draft.blockers)


def test_complete_import_preserves_parent_and_dependency_hashes_through_containers(values, tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native, promote_native
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5, read_hdf5
    from experiment_to_cpfe.datasets.package import write_npz
    cfg = native(values, {"channels": meaning()})
    draft = decode_native(cfg)
    assert draft.blockers == []
    arrays, assets = promote_native(draft)
    assert arrays["channels"].shape == (2, 3, 2)
    assert assets[-1].parent_asset_id == assets[0].asset_id
    assert assets[-1].conversion.source_sha256 == assets[0].sha256
    pipeline = load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml"))
    payload = pipeline.model_dump()
    payload.update(imports=[cfg.model_dump()], sources=[], assets=[], solver_inputs={})
    pipeline = type(pipeline).model_validate(payload)
    sample = assemble_sample(pipeline)
    path = tmp_path / "sample.h5"
    digest = write_hdf5(sample, path)
    restored = read_hdf5(path)
    assert restored.assets[-1].descriptive_metadata["meaning"]["spatial"]["spacing"] == [2, 3]
    assert np.array_equal(restored.arrays["channels"], np.arange(12).reshape(2, 3, 2))
    write_npz(path, tmp_path / "sample.npz", digest)
    with np.load(tmp_path / "sample.npz", allow_pickle=False) as p:
        assert p["channels"].tolist() == restored.arrays["channels"].tolist()
        assert json.loads(p["__asset_manifest_json__"].item())[-1]["source_kind"] == "inferred"


def test_source_change_between_decode_and_promotion_is_rejected(values):
    from experiment_to_cpfe.adapters.native import decode_native, promote_native
    draft = decode_native(native(values, {"channels": meaning()}))
    np.save(values, np.zeros((2, 3, 2)))
    with pytest.raises(ValueError, match="changed|hash"):
        promote_native(draft)


def test_partial_array_quality_and_sparse_ids_are_preserved(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native
    from experiment_to_cpfe.adapters.native_models import NativeImportConfig
    path = tmp_path / "field.h5"
    with h5py.File(path, "w") as h:
        h["ids"] = np.array([17, 300, 9001])
        h["field"] = np.array([[1, 2], [np.nan, np.nan], [3, 4]])
        h["quality"] = np.array([1, 0, 1], dtype=np.uint8)
    cfg = NativeImportConfig.model_validate(dict(import_id="field", profile="numeric", modality="point_field",
        files={"d": dict(path=path, format="hdf5", source_kind="inferred", license="synthetic", native_layout="flat")},
        selections={k: dict(file="d", selector={"path": k}) for k in ["ids", "field", "quality"]},
        meanings={"field": dict(quantity="displacement", unit="mm", axes=["grain", "component"],
            source_kind="inferred", evidence="synthetic", role="field", components={"component": ["u", "v"]},
            entity_ids="ids", entity_axis=0, identity_scope="one state only", reference_state="unloaded",
            quality={"array": "quality", "valid_values": [1], "axes": [0]})}))
    draft = decode_native(cfg)
    assert draft.arrays["ids"].tolist() == [17, 300, 9001]
    assert np.isnan(draft.arrays["field"][1]).all()
    assert draft.report()["arrays"]["field"]["nonfinite_count"] == 2
    assert draft.blockers  # finite normalized payload remains an explicit follow-up conversion


def test_duplicate_entity_ids_and_alignment_mismatch_block_promotion(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native
    cfg = native(tmp_path / "v.npy").model_dump()
    np.save(tmp_path / "v.npy", np.array([17, 17]))
    cfg["meanings"] = {"channels": dict(quantity="grain identifier", unit="1", axes=["grain"],
        source_kind="input", evidence="synthetic", role="id", identity_scope="state 1")}
    from experiment_to_cpfe.adapters.native_models import NativeImportConfig
    draft = decode_native(NativeImportConfig.model_validate(cfg))
    assert any("unique" in issue for issue in draft.blockers)


def test_import_dependencies_resolve_relative_to_configuration_and_are_locked(values, tmp_path):
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.provenance.binding import capture_inputs, changed_inputs
    cfg = load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml")).model_dump(mode="json")
    imported = native(values, {"channels": meaning()}).model_dump(mode="json")
    imported["files"]["data"]["path"] = values.name
    cfg.update(imports=[imported], sources=[], assets=[])
    path = tmp_path / "sample.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    loaded = load_pipeline_config(path)
    assert loaded.imports[0].files["data"].path == values.resolve()
    lock = capture_inputs(loaded, path, path)
    assert str(values.resolve()) in lock["files"]
    values.write_bytes(b"modified")
    assert any(str(values.resolve()) in issue for issue in changed_inputs(lock))
