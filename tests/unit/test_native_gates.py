"""Scientific declarations and auxiliary dependencies cannot be bypassed at export."""

from pathlib import Path
import json

import h5py
import numpy as np
import pytest

from test_native_imports import native, meaning


def test_native_dependency_hash_is_validated_even_when_it_is_not_primary_parent(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native, promote_native
    from experiment_to_cpfe.assets.models import AssetManifest
    from experiment_to_cpfe.adapters.native_models import NativeFile
    path = tmp_path / "v.npy"
    np.save(path, np.zeros((2, 3, 2)))
    cfg = native(path, {"channels": meaning()})
    aux = tmp_path / "calibration.txt"
    aux.write_text("synthetic documented convention")
    cfg.files["evidence"] = NativeFile(path=aux, format="txt", source_kind="input", license="synthetic", native_layout="explanation")
    _, assets = promote_native(decode_native(cfg))
    changed = tuple(a.model_copy(update={"sha256": "a" * 64}) if a.asset_id.endswith(":evidence") else a for a in assets)
    with pytest.raises(ValueError, match="dependency"):
        AssetManifest(assets=changed)


def test_hdf5_roundtrip_rechecks_native_meaning_instead_of_trusting_mutated_units(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native, promote_native
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5, read_hdf5
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.config import load_pipeline_config
    path = tmp_path / "v.npy"
    np.save(path, np.zeros((2, 3, 2)))
    arrays, assets = promote_native(decode_native(native(path, {"channels": meaning()})))
    sample = assemble_sample(load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml")))
    sample.arrays.update(arrays)
    sample.assets += assets
    out = tmp_path / "sample.h5"
    write_hdf5(sample, out)
    with h5py.File(out, "r+") as h:
        group = h["assets/scan:channels:normalized"]
        metadata = json.loads(group.attrs["metadata_json"])
        metadata["descriptive_metadata"]["meaning"]["unit"] = "unknown"
        group.attrs["metadata_json"] = json.dumps(metadata)
    with pytest.raises(ValueError, match="unit|semantic"):
        read_hdf5(out)


def test_tensor_target_also_requires_shear_and_reference_conventions(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native
    path = tmp_path / "v.npy"
    np.save(path, np.zeros((2, 3, 2)))
    m = meaning()
    m.update(role="target", tensor_order=["u", "v"], group_id="specimen-1", split="test", target_origin="synthetic simulation")
    draft = decode_native(native(path, {"channels": m}))
    assert any("shear" in s for s in draft.blockers)
    assert any("reference" in s for s in draft.blockers)


def test_orientation_normalization_requires_valid_rotation_values(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native
    path = tmp_path / "v.npy"
    np.save(path, np.full((2, 3, 2), 10.0))
    m = meaning()
    m.update(role="orientation", orientation={"representation": "quaternion", "convention": "scalar_last",
             "mapping_direction": "crystal_to_sample", "angle_units": None, "crystal_symmetry": "cubic"})
    draft = decode_native(native(path, {"channels": m}))
    assert any("quaternion" in s for s in draft.blockers)


def test_graph_profile_rejects_silently_ignored_selections(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native
    from experiment_to_cpfe.adapters.native_models import NativeImportConfig
    from test_native_mesh_graph import graph_files, graph_options
    cfg = NativeImportConfig(import_id="graph", profile="grain_graph", modality="grain_graph",
            files=graph_files(tmp_path), options=graph_options(), selections={"unused": {"file": "features"}})
    with pytest.raises(ValueError, match="selection"):
        decode_native(cfg)


def test_native_adapt_cli_reports_blockers_without_complete_sample_metadata(tmp_path):
    from experiment_to_cpfe.cli import main
    path = tmp_path / "v.npy"
    np.save(path, np.zeros((2, 3, 2)))
    cfg = tmp_path / "native.json"
    cfg.write_text(json.dumps({"imports": [native(path).model_dump(mode="json")]}), encoding="utf-8")
    out = tmp_path / "run"
    assert main(["adapt", "--config", str(cfg), "--run-dir", str(out)]) == 1
    report = json.loads((out / "reports/native-adapters.json").read_text())
    assert report["status"] == "blocked"
    assert report["imports"][0]["decoding"] == "passed"
    assert report["imports"][0]["physical_validation"] == "not_performed"
    assert not (out / "dataset").exists()
    assert main(["adapt", "--config", str(cfg), "--run-dir", str(out)]) == 1


def test_point_field_requires_coordinate_frame_without_fabricated_grid_spacing(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native
    from experiment_to_cpfe.adapters.native_models import NativeImportConfig
    path = tmp_path / "v.npy"
    np.save(path, np.zeros((2, 3, 2)))
    cfg = native(path, {"channels": meaning()}).model_dump()
    cfg["modality"] = "point_field"
    cfg["meanings"]["channels"]["spatial"] = None
    draft = decode_native(NativeImportConfig.model_validate(cfg))
    assert any("coordinate_frame" in s for s in draft.blockers)
    cfg["meanings"]["channels"]["coordinate_frame"] = "sample"
    draft = decode_native(NativeImportConfig.model_validate(cfg))
    assert not draft.blockers


def test_same_target_group_cannot_be_split_across_train_and_test(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native, promote_native
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.config import load_pipeline_config
    path = tmp_path / "v.npy"
    np.save(path, np.zeros((2, 3, 2)))
    sample = assemble_sample(load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml")))
    from experiment_to_cpfe.adapters.native_models import NativeImportConfig
    for split in ("train", "test"):
        meta = meaning()
        meta.update(role="target", group_id="same-specimen", split=split, target_origin="synthetic generator")
        cfg = native(path).model_dump()
        cfg.update(import_id=split, selections={split: {"file": "data", "selector": {}}}, meanings={split: meta})
        arrays, assets = promote_native(decode_native(NativeImportConfig.model_validate(cfg)))
        sample.arrays.update(arrays)
        sample.assets += assets
    with pytest.raises(ValueError, match="group|split"):
        write_hdf5(sample, tmp_path / "forbidden.h5")


def test_non_numeric_field_cannot_pass_by_declaring_units(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native
    path = tmp_path / "v.npy"
    np.save(path, np.full((2, 3, 2), "invalid"))
    assert decode_native(native(path, {"channels": meaning()})).blockers


def test_euler_angles_require_three_explicit_components(tmp_path):
    from experiment_to_cpfe.adapters.native import decode_native
    path = tmp_path / "v.npy"
    np.save(path, np.zeros((2, 3, 2)))
    meta = meaning()
    meta.update(role="orientation", orientation=dict(representation="euler", convention="ZXZ",
        mapping_direction="crystal_to_sample", angle_units="radian", crystal_symmetry="cubic"))
    assert any("Euler" in b for b in decode_native(native(path, {"channels": meta})).blockers)


def test_native_adapt_malformed_yaml_returns_failure_without_creating_run(tmp_path):
    from experiment_to_cpfe.cli import main
    path = tmp_path / "invalid.yaml"
    path.write_text("imports: [not closed")
    out = tmp_path / "run"
    assert main(["adapt", "--config", str(path), "--run-dir", str(out)]) == 1
    assert not out.exists()
