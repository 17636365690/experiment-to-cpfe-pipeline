"""Synthetic mixed meshes and sparse graphs exercise source IDs, not fixed sizes."""

import numpy as np
import pytest


def source_file(path, fmt="txt"):
    from experiment_to_cpfe.adapters.native_models import NativeFile
    return NativeFile(path=path, format=fmt, source_kind="input", license="synthetic", native_layout="synthetic")


def mesh_files(tmp_path, mutation=""):
    path = tmp_path / "mesh.msh"
    text = "$MeshFormat\n2.2 0 8\n$EndMeshFormat\n$Nodes\n4\n10 0 0 0\n30 1 0 0\n50 0 1 0\n90 0 0 1\n$EndNodes\n$Elements\n2\n4 15 2 7 2 10\n99 4 2 7 2 10 30 50 90\n$EndElements\n$ElsetOrientations\n1 rodrigues:active\n7 0 0 1\n$EndElsetOrientations\n"
    if mutation == "node": text = text.replace("10 30 50 90", "10 30 50 91")
    if mutation == "grain": text = text.replace("99 4 2 7", "99 4 2 8")
    if mutation == "duplicate": text = text.replace("30 1 0 0", "10 1 0 0")
    if mutation == "binary": text = text.replace("2.2 0 8", "2.2 1 8")
    path.write_text(text)
    cfg = tmp_path / "input.cfg"
    cfg.write_text("number_of_phases 1\ncrystal_type FCC\nset_bc vel z1 z 0.001\n")
    return {"mesh": source_file(path, "msh"), "cfg": source_file(cfg, "cfg")}


def mesh_options():
    return dict(mesh_file="mesh", config_file="cfg", dimension=3, element_type=4, grain_tag_index=0,
                orientation_conversion={"source": "rodrigues:active", "target": "rotation_matrix",
                                        "mapping_direction": "crystal_to_sample"})


def test_mesh_filters_dimension_preserves_ids_and_checks_orientation_direction(tmp_path):
    from experiment_to_cpfe.adapters.native_mesh import read_mesh
    arrays, descriptions, blockers = read_mesh(mesh_files(tmp_path), mesh_options())
    assert not blockers
    assert arrays["mesh_node_ids"].tolist() == [10, 30, 50, 90]
    assert arrays["mesh_element_ids"].tolist() == [99]
    assert arrays["mesh_connectivity"].tolist() == [[10, 30, 50, 90]]
    assert arrays["mesh_grain_ids"].tolist() == [7]
    assert arrays["grain_ids"].tolist() == [7]
    assert np.allclose(arrays["grain_rotations"][0] @ [1, 0, 0], [0, 1, 0])
    assert descriptions["mesh_connectivity"]["all_element_count"] == 2
    assert descriptions["mesh_connectivity"]["selected_element_count"] == 1
    assert descriptions["mesh_connectivity"]["config_file"] == "cfg"


@pytest.mark.parametrize("mutation", ["node", "grain", "duplicate", "binary"])
def test_bad_native_mesh_never_yields_a_normalized_mesh(tmp_path, mutation):
    from experiment_to_cpfe.adapters.native_mesh import read_mesh
    with pytest.raises(ValueError):
        read_mesh(mesh_files(tmp_path, mutation), mesh_options())


def test_wrong_rodrigues_convention_rejected_and_native_values_can_be_retained(tmp_path):
    from experiment_to_cpfe.adapters.native_mesh import read_mesh
    opts = mesh_options()
    opts["orientation_conversion"]["source"] = "rodrigues:passive"
    with pytest.raises(ValueError, match="orientation|convention"):
        read_mesh(mesh_files(tmp_path), opts)
    opts.pop("orientation_conversion")
    arrays, _, _ = read_mesh(mesh_files(tmp_path), opts)
    assert "grain_rotations" not in arrays
    assert arrays["grain_rodrigues"].tolist() == [[0, 0, 1]]


def graph_files(tmp_path, mutation=""):
    neighbor = np.array([[0, 0, 0], [0, 0, 1], [0, 1, 0]])
    features = "7 0 0\n19 2 3\n9001 4 5\n"
    if mutation == "asymmetric": neighbor[1, 2] = 0
    if mutation == "self_loop": neighbor[1, 1] = 1
    if mutation == "duplicate": features = features.replace("9001", "19")
    files = {}
    for key, value in [("adj", neighbor), ("features", features), ("targets", "0 0\n1 0.01\n")]:
        path = tmp_path / f"{key}.txt"
        if isinstance(value, str): path.write_text(value)
        else: np.savetxt(path, value, fmt="%d")
        files[key] = source_file(path)
    return files


def graph_options():
    return dict(adjacency_file="adj", features_file="features", targets_file="targets", id_column=0,
                feature_columns=[1, 2], id_dtype="int64", directed=False, self_loops="preserve", padding_ids=[],
                node_order_evidence="synthetic: adjacency rows follow feature rows", zero_node_policy="keep")


def test_graph_keeps_zero_node_and_sparse_ids_without_padding_as_real_grains(tmp_path):
    from experiment_to_cpfe.adapters.native_graph import read_graph
    arrays, descriptions, blockers = read_graph(graph_files(tmp_path), graph_options())
    assert not blockers
    assert arrays["graph_node_ids"].tolist() == [7, 19, 9001]
    assert arrays["graph_edge_index"].tolist() == [[1, 2], [2, 1]]
    assert arrays["graph_node_features"].tolist() == [[0, 0], [2, 3], [4, 5]]
    assert arrays["graph_targets"].shape == (2, 2)
    assert descriptions["graph_node_features"]["zero_node_ids"] == ["7"]


def test_graph_padding_removal_requires_isolated_declared_ids(tmp_path):
    from experiment_to_cpfe.adapters.native_graph import read_graph
    opts = graph_options()
    opts.update(padding_ids=["7"], padding_evidence="synthetic isolated sentinel", zero_node_policy="keep")
    arrays, descriptions, _ = read_graph(graph_files(tmp_path), opts)
    assert arrays["graph_node_ids"].tolist() == [19, 9001]
    assert arrays["graph_edge_index"].tolist() == [[0, 1], [1, 0]]
    assert descriptions["graph_edge_index"]["removed_padding_ids"] == ["7"]
    opts["padding_ids"] = ["19"]
    with pytest.raises(ValueError, match="padding|isolated"):
        read_graph(graph_files(tmp_path), opts)


@pytest.mark.parametrize("mutation", ["asymmetric", "duplicate", "self_loop"])
def test_graph_invalid_identity_or_adjacency_is_rejected(tmp_path, mutation):
    from experiment_to_cpfe.adapters.native_graph import read_graph
    opts = graph_options()
    opts["self_loops"] = "reject"
    with pytest.raises(ValueError):
        read_graph(graph_files(tmp_path, mutation), opts)


def test_unknown_zero_node_semantics_are_visible_blockers(tmp_path):
    from experiment_to_cpfe.adapters.native_graph import read_graph
    opts = graph_options()
    opts["zero_node_policy"] = "unresolved"
    arrays, _, blockers = read_graph(graph_files(tmp_path), opts)
    assert len(arrays["graph_node_ids"]) == 3
    assert any("zero" in issue for issue in blockers)
