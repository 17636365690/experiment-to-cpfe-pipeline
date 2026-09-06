"""Explicit adjacency/feature/target bundles; IDs and graph indices are distinct."""

import numpy as np

from experiment_to_cpfe.adapters.native_numeric import read_numeric


def read_graph(files, options):
    allowed = {"adjacency_file", "features_file", "targets_file", "id_column", "id_dtype", "feature_columns",
               "directed", "self_loops", "padding_ids", "padding_evidence", "node_order_evidence", "zero_node_policy", "max_bytes"}
    if set(options) - allowed:
        raise ValueError("unknown graph options")
    keys = [options.get(k) for k in ("adjacency_file", "features_file", "targets_file")]
    if any(k not in files for k in keys):
        raise ValueError("adjacency, feature and target files must all be declared")
    if type(options.get("directed")) is not bool or not options.get("node_order_evidence"):
        raise ValueError("explicit directedness and adjacency-to-feature row evidence required")
    limit = options.get("max_bytes", 32 * 1024 * 1024)
    def read(key, dtype):
        return read_numeric(files[key].path, {"format": "txt", "dtype": dtype, "max_bytes": limit,
                                               "max_source_bytes": limit})[0]
    adjacency = read(keys[0], "float64")
    raw = read(keys[1], "str")
    targets = read(keys[2], "float64")
    n = raw.shape[0]
    if adjacency.shape != (n, n) or not np.isin(adjacency, [0, 1]).all():
        raise ValueError("adjacency must be a finite binary square matrix aligned with feature rows")
    if not options["directed"] and not np.array_equal(adjacency, adjacency.T):
        raise ValueError("undirected adjacency must be symmetric")
    id_column, columns = options.get("id_column"), options.get("feature_columns")
    if (type(id_column) is not int or not 0 <= id_column < raw.shape[1] or not isinstance(columns, (list, tuple))
            or not columns or len(set(columns)) != len(columns) or id_column in columns
            or any(type(i) is not int or not 0 <= i < raw.shape[1] for i in columns)):
        raise ValueError("explicit distinct ID/feature column indices are required")
    dtype = options.get("id_dtype", "str")
    if dtype not in {"str", "int64"}:
        raise ValueError("id_dtype must be str or int64")
    ids = raw[:, id_column].astype(dtype)
    if len(np.unique(ids)) != n or any(not str(v).strip() for v in ids):
        raise ValueError("graph IDs must be nonempty and unique")
    features = raw[:, columns].astype(np.float64)
    if not np.isfinite(features).all() or not np.isfinite(targets).all():
        raise ValueError("graph features and targets must be finite")
    ids_text = [str(v) for v in ids]
    zero_nodes = np.all(features == 0, axis=1) & np.all(adjacency == 0, axis=0) & np.all(adjacency == 0, axis=1)
    padding = options.get("padding_ids")
    if not isinstance(padding, (list, tuple)) or len(set(padding)) != len(padding) or not set(padding) <= set(ids_text):
        raise ValueError("padding_ids must explicitly list distinct existing original IDs as strings")
    if padding and not options.get("padding_evidence"):
        raise ValueError("padding removal requires evidence")
    for index, name in enumerate(ids_text):
        if name in padding and not zero_nodes[index]:
            raise ValueError("declared padding node must have zero features and be isolated")
    keep = np.array([name not in padding for name in ids_text])
    if not keep.any():
        raise ValueError("padding removal cannot remove every node")
    adjacency = adjacency[np.ix_(keep, keep)]
    loop_policy = options.get("self_loops")
    losses = ["text formatting not preserved; original files retained", "binary adjacency converted to explicit graph row indices"]
    if loop_policy == "reject":
        if np.diag(adjacency).any():
            raise ValueError("self loops are forbidden by the declared policy")
    elif loop_policy == "add":
        np.fill_diagonal(adjacency, 1)
        losses.append("self loops added by explicit policy")
    elif loop_policy == "remove":
        np.fill_diagonal(adjacency, 0)
        losses.append("self loops removed by explicit policy")
    elif loop_policy != "preserve":
        raise ValueError("explicit self_loops policy is required")
    if padding:
        losses.append("declared isolated padding nodes removed; remaining edge row indices remapped")
    blockers = []
    zero_policy = options.get("zero_node_policy")
    if zero_policy not in {"keep", "unresolved"}:
        raise ValueError("zero_node_policy must be keep or unresolved; removal needs explicit padding IDs")
    if zero_policy == "unresolved" and zero_nodes.any():
        blockers.append("zero-node background/padding meaning is unresolved; original nodes retained")
    arrays = {"graph_node_ids": ids[keep], "graph_node_features": features[keep],
              "graph_edge_index": np.array(np.nonzero(adjacency), dtype=np.int64), "graph_targets": targets}
    metadata = {"options": options, "zero_node_ids": [ids_text[i] for i in np.flatnonzero(zero_nodes)],
                "removed_padding_ids": list(padding), "edge_identity": "zero-based rows of graph_node_ids",
                "losses": losses}
    parents = {"graph_node_ids": keys[1], "graph_node_features": keys[1], "graph_edge_index": keys[0], "graph_targets": keys[2]}
    return arrays, {name: {**metadata, "parent_file": parents[name]} for name in arrays}, blockers
