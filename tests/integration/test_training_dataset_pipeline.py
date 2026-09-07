"""Configured canonical collections exercise real CPU optimization end to end."""

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from training_fixtures import training_collection, save_config


@pytest.mark.parametrize("layout", ["table", "array"])
def test_configured_collection_trains_evaluates_and_restores(tmp_path, make_sample, layout):
    pytest.importorskip("torch")
    from experiment_to_cpfe.cli import main
    from experiment_to_cpfe.learning.surrogate import predict_mlp
    from experiment_to_cpfe.provenance.hashing import sha256_file

    config, _ = training_collection(tmp_path / "input", make_sample, layout, count=31)
    path = save_config(tmp_path / "input" / "build.json", config)
    out, model = tmp_path / "dataset", tmp_path / "model"
    assert main(["build-training-dataset", "--config", str(path), "--run-dir", str(out)]) == 0
    metadata = json.loads((out / "dataset.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "build-manifest.json").read_text(encoding="utf-8"))
    assert manifest["config_sha256"] == sha256_file(path)
    assert manifest["artifacts"]["dataset.npz"]["sha256"] == sha256_file(out / "dataset.npz")
    with np.load(out / "dataset.npz", allow_pickle=False) as payload:
        assert json.loads(payload["__metadata_json__"].item()) == metadata
        features, splits = payload["features"], payload["splits"]
        assert payload["targets"][:31] == pytest.approx(np.linspace(0, 1, 31))
    train = json.loads((out / "training-config.json").read_text())
    train.update(epochs=800, patience=300, seed=17)
    save_config(out / "training-config.json", train)
    assert main(["train-surrogate", "--config", str(out / "training-config.json"), "--run-dir", str(model)]) == 0
    result = json.loads((model / "training.json").read_text())
    assert result["history"][-1]["train_mse_standardized"] < result["history"][0]["train_mse_standardized"] / 10
    assert result["metrics"]["test"]["nrmse"] < .05
    assert result["metrics"]["test"]["rmse"] < result["mean_baseline"]["test"]["rmse"]
    assert result["normalization"]["x_mean"] == pytest.approx([.5, 1.5])
    assert result["dataset"]["sha256"] == sha256_file(out / "dataset.npz")
    receipt = json.loads((model / "dataset-receipt.json").read_text(encoding="utf-8"))
    assert receipt["metadata"]["sources"][3]["sample_metadata"]["sample_id"] == "d"
    assert receipt["training_config_sha256"] == sha256_file(out / "training-config.json")
    with np.load(model / "predictions.npz") as prediction:
        assert predict_mlp(model / "model.pt", features[splits == "test"]) == pytest.approx(prediction["prediction"][splits == "test"])


def test_build_command_rejects_invalid_input_without_outputs_and_preserves_existing(tmp_path, make_sample, capsys):
    from experiment_to_cpfe.cli import main
    config, _ = training_collection(tmp_path, make_sample)
    path = save_config(tmp_path / "build.json", config)
    out = tmp_path / "built"
    assert main(["build-training-dataset", "--config", str(path), "--run-dir", str(out)]) == 0
    original = (out / "dataset.npz").read_bytes()
    assert main(["build-training-dataset", "--config", str(path), "--run-dir", str(out)]) == 1
    assert (out / "dataset.npz").read_bytes() == original
    config["inputs"][0]["sample_id"] = "wrong"
    save_config(path, config)
    invalid = tmp_path / "invalid"
    assert main(["build-training-dataset", "--config", str(path), "--run-dir", str(invalid)]) == 1
    assert "wrong" in capsys.readouterr().err
    assert not invalid.exists()


@pytest.mark.parametrize("mutation", ["names", "units", "target", "payload", "metadata", "format", "file_hash"])
def test_new_bundle_conflicts_fail_before_training_outputs(tmp_path, make_sample, mutation):
    from experiment_to_cpfe.datasets.training import run_dataset_build
    from experiment_to_cpfe.learning.surrogate import run_training
    config, _ = training_collection(tmp_path, make_sample)
    run_dataset_build(save_config(tmp_path / "build.json", config), tmp_path / "built")
    path = tmp_path / "built" / "training-config.json"
    train = json.loads(path.read_text())
    if mutation == "names": train["feature_names"].reverse()
    elif mutation == "units": train["feature_units"][1] = "kPa"
    elif mutation == "target": train["target_name"] = "different"
    elif mutation == "file_hash": train["dataset_sha256"] = "0" * 64
    else:
        train.pop("dataset_sha256")  # Exercise the independent embedded bundle contract.
        dataset_path = path.parent / "dataset.npz"
        with np.load(dataset_path, allow_pickle=False) as payload:
            arrays = {key: payload[key] for key in payload.files}
        if mutation == "payload": arrays["targets"][0] = 100
        elif mutation == "metadata": arrays["__metadata_json__"] = np.asarray('{}')
        else: arrays["__format_version__"] = np.asarray("experiment-to-cpfe-training-999")
        np.savez_compressed(dataset_path, **arrays)
    save_config(path, train)
    with pytest.raises(ValueError, match="dataset|bundle|metadata"):
        run_training(path, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_documented_synthetic_example_builds_both_layouts_outside_checkout(tmp_path):
    from experiment_to_cpfe.datasets.training import run_dataset_build
    script = Path("examples/synthetic_training/prepare.py").resolve()
    result = subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "inputs")],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    for layout in ("table", "array"):
        out = tmp_path / layout
        run_dataset_build(tmp_path / "inputs" / layout / "build.yaml", out)
        with np.load(out / "dataset.npz", allow_pickle=False) as data:
            assert data["features"].shape == (124, 2)
            assert data["targets"][:31] == pytest.approx(np.linspace(0, 1, 31))
    assert subprocess.run([sys.executable, str(script), "--output-dir", str(tmp_path / "inputs")],
                          cwd=tmp_path, capture_output=True).returncode != 0


@pytest.mark.parametrize("key,value", [("dataset", 123), ("feature_names", "strain"),
    ("feature_units", None), ("target_unit", ["Pa"]), ("seed", "bad"), ("hidden", 2),
    ("learning_rate", "fast"), ("epochs", True)])
def test_invalid_training_config_reports_value_error_before_output(tmp_path, key, value):
    from experiment_to_cpfe.learning.surrogate import run_training
    np.savez_compressed(tmp_path / "legacy.npz", features=np.arange(6.)[:, None], targets=np.arange(6.),
                        groups=np.repeat(["a", "b", "c"], 2), splits=np.repeat(["train", "validation", "test"], 2))
    config = {"dataset": "legacy.npz", "feature_names": ["strain"], "feature_units": ["1"],
              "target_name": "stress", "target_unit": "Pa", "epochs": 1}
    config[key] = value
    with pytest.raises(ValueError):
        run_training(save_config(tmp_path / "train.json", config), tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_existing_canonical_npz_with_training_arrays_remains_trainable(tmp_path, make_sample):
    pytest.importorskip("torch")
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5
    from experiment_to_cpfe.datasets.package import write_npz
    from experiment_to_cpfe.learning.surrogate import run_training

    sample = make_sample()
    sample.arrays.update(features=np.arange(6.)[:, None], targets=np.arange(6.),
                         groups=np.repeat(["a", "b", "c"], 2),
                         splits=np.repeat(["train", "validation", "test"], 2))
    source = tmp_path / "sample.h5"
    digest = write_hdf5(sample, source)
    write_npz(source, tmp_path / "sample.npz", digest)
    config = {"dataset": "sample.npz", "feature_names": ["strain"], "feature_units": ["1"],
              "target_name": "stress", "target_unit": "Pa", "epochs": 1}
    result = run_training(save_config(tmp_path / "train.json", config), tmp_path / "model")
    assert result["status"] == "completed"
    with np.load(tmp_path / "model" / "predictions.npz") as predictions:
        assert predictions["target"].tolist() == [0., 1., 2., 3., 4., 5.]


@pytest.mark.parametrize("marker", [None, "experiment-to-cpfe-npz-1"])
def test_partial_training_metadata_cannot_silently_become_a_legacy_bundle(tmp_path, make_sample, marker):
    from experiment_to_cpfe.datasets.training import run_dataset_build
    from experiment_to_cpfe.learning.surrogate import run_training

    config, _ = training_collection(tmp_path, make_sample)
    out = tmp_path / "built"
    run_dataset_build(save_config(tmp_path / "build.json", config), out)
    path = out / "training-config.json"
    training = json.loads(path.read_text())
    training.pop("dataset_sha256")  # Verify the embedded contract independently.
    training["epochs"] = 1
    with np.load(out / "dataset.npz", allow_pickle=False) as payload:
        arrays = {key: payload[key] for key in payload.files if key != "__format_version__"}
    if marker is not None:
        arrays["__format_version__"] = np.asarray(marker)
    np.savez_compressed(out / "dataset.npz", **arrays)
    with pytest.raises(ValueError, match="training bundle"):
        run_training(save_config(path, training), tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()
