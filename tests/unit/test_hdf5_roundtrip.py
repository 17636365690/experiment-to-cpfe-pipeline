import h5py
import numpy as np
import pytest


def test_hdf5_round_trip_preserves_sample(tmp_path, make_sample):
    from experiment_to_cpfe.datasets.hdf5 import read_hdf5, write_hdf5

    source = make_sample()
    output = tmp_path / "sample.h5"

    digest = write_hdf5(source, output)
    restored = read_hdf5(output)

    assert len(digest) == 64
    assert restored.metadata.sample_id == source.metadata.sample_id
    assert restored.tables == source.tables
    assert restored.arrays["demo"].tolist() == [1.0, 2.0]
    assert restored.assets[0].source_kind == source.assets[0].source_kind


def test_hdf5_contains_canonical_groups(tmp_path, make_sample):
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5

    output = tmp_path / "sample.h5"
    write_hdf5(make_sample(), output)
    with h5py.File(output, "r") as handle:
        assert {
            "meta",
            "assets",
            "geometry",
            "mesh",
            "grains",
            "grain_boundaries",
            "load_history",
            "measured",
            "simulation",
            "macro_response",
            "derived",
            "provenance",
            "quality",
        } <= set(handle)


def test_hdf5_rejects_existing_output(tmp_path, make_sample):
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5

    output = tmp_path / "sample.h5"
    output.write_bytes(b"keep")

    with pytest.raises(FileExistsError):
        write_hdf5(make_sample(), output)
    assert output.read_bytes() == b"keep"


def test_npz_records_hdf5_source_hash(tmp_path, make_sample):
    from experiment_to_cpfe.datasets.package import write_npz

    output = tmp_path / "sample.npz"
    source_hash = "b" * 64
    write_npz(make_sample(), output, source_hash)

    with np.load(output, allow_pickle=False) as bundle:
        assert bundle["demo"].tolist() == [1.0, 2.0]
        assert bundle["__source_hdf5_sha256__"].item() == source_hash


def test_npz_rejects_empty_source_hash(tmp_path, make_sample):
    from experiment_to_cpfe.datasets.package import write_npz

    with pytest.raises(ValueError, match="HDF5 source hash"):
        write_npz(make_sample(), tmp_path / "sample.npz", "")
