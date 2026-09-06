"""An unlabeled CSV row is not a sample identity without pinned mapping evidence."""

import numpy as np
import pytest


def setup(tmp_path):
    from experiment_to_cpfe.adapters.native_models import NativeFile
    folder = tmp_path / "texture_2"
    folder.mkdir()
    voxel = folder / "texture_2.npy"
    np.save(voxel, np.ones((2, 3, 2, 4)))
    labels = tmp_path / "labels.csv"
    labels.write_text("C0000,C0011,C1100,C1111\n1,2,3,4\n11,12,13,14\n")
    loader = tmp_path / "mapping.txt"
    loader.write_text("Synthetic mapping: zero-based CSV row r maps to texture_(r+1).")
    files = {key: NativeFile(path=p, format=fmt, source_kind="simulated", license="synthetic", native_layout="synthetic")
             for key, p, fmt in [("voxel", voxel, "npy"), ("labels", labels, "csv"), ("loader", loader, "txt")]}
    opts = dict(voxel_file="voxel", labels_file="labels", columns=["C0000", "C0011", "C1100", "C1111"],
        pairing={"row_index": 1, "index_base": 1, "sample_template": "texture_{index}",
                 "relative_path_template": "{sample}/{sample}.npy", "expected_rows": 2,
                 "loader_file": "loader", "evidence": "synthetic explicit mapping definition"})
    return files, opts


def test_stiffness_pair_uses_original_csv_row_not_numeric_filename_sort(tmp_path):
    from experiment_to_cpfe.adapters.native_stiffness import read_stiffness
    files, opts = setup(tmp_path)
    arrays, desc, blockers = read_stiffness(files, opts)
    assert not blockers
    assert arrays["stiffness_labels"].tolist() == [[11, 12, 13, 14]]
    assert arrays["sample_ids"].tolist() == ["texture_2"]
    assert desc["stiffness_labels"]["source_data_row"] == 1
    assert desc["stiffness_labels"]["columns"] == opts["columns"]


def test_missing_loader_evidence_blocks_pairing_without_fabricating_ids(tmp_path):
    from experiment_to_cpfe.adapters.native_stiffness import read_stiffness
    files, opts = setup(tmp_path)
    opts.pop("pairing")
    arrays, _, blockers = read_stiffness(files, opts)
    assert blockers and "sample_ids" not in arrays
    assert arrays["stiffness_labels"].shape == (2, 4)


@pytest.mark.parametrize("change", [{"row_index": 0}, {"expected_rows": 3}, {"loader_file": "absent"}])
def test_conflicting_pairing_evidence_is_rejected(tmp_path, change):
    from experiment_to_cpfe.adapters.native_stiffness import read_stiffness
    files, opts = setup(tmp_path)
    opts["pairing"].update(change)
    with pytest.raises(ValueError):
        read_stiffness(files, opts)


def test_no_implicit_voigt_reordering_or_shear_scaling(tmp_path):
    from experiment_to_cpfe.adapters.native_stiffness import read_stiffness
    files, opts = setup(tmp_path)
    opts["columns"] = ["C1111", "C0011", "C1100", "C0000"]
    arrays, desc, _ = read_stiffness(files, opts)
    assert arrays["stiffness_labels"].tolist() == [[14, 12, 13, 11]]
    assert desc["stiffness_labels"]["unit_conversion"] == "none"
