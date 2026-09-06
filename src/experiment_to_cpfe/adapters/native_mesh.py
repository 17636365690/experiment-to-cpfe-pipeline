"""Gmsh 2.2 ASCII selection and native Neper Rodrigues declarations."""

from collections import Counter
import numpy as np


# Gmsh element numbers: (topological dimension, number of nodes).
_ELEMENTS = {1: (1, 2), 2: (2, 3), 3: (2, 4), 4: (3, 4), 5: (3, 8),
             6: (3, 6), 7: (3, 5), 8: (1, 3), 9: (2, 6), 10: (2, 9),
             11: (3, 10), 12: (3, 27), 13: (3, 18), 14: (3, 14), 15: (0, 1)}


def _sections(text):
    result, active = {}, None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("$End"):
            if active is None or line != "$End" + active:
                raise ValueError("mismatched Gmsh section terminator")
            active = None
        elif line.startswith("$"):
            if active is not None or line[1:] in result:
                raise ValueError("duplicate/nested Gmsh section")
            active = line[1:]
            result[active] = []
        elif active is not None:
            result[active].append(line)
        elif line:
            raise ValueError("text outside Gmsh sections")
    if active is not None:
        raise ValueError("unterminated Gmsh section")
    return result


def _records(sections, key):
    lines = sections.get(key, [])
    if not lines or int(lines[0].split()[0]) != len(lines) - 1:
        raise ValueError(f"invalid Gmsh {key} count")
    return [line.split() for line in lines[1:]]


def _rodrigues_matrix(v, passive=False):
    x, y, z = v
    skew = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    r = np.eye(3) + 2 * (skew + skew @ skew) / (1 + np.dot(v, v))
    return r.T if passive else r


def read_mesh(files, options):
    allowed = {"mesh_file", "config_file", "dimension", "element_type", "grain_tag_index", "orientation_conversion", "max_source_bytes"}
    if set(options) - allowed:
        raise ValueError("unknown mesh options")
    mesh_key, cfg_key = options.get("mesh_file"), options.get("config_file")
    if mesh_key not in files or cfg_key not in files:
        raise ValueError("mesh_file and companion config_file must be declared")
    limit = options.get("max_source_bytes", 32 * 1024 * 1024)
    if type(limit) is not int or limit <= 0 or any(files[k].path.stat().st_size > limit for k in (mesh_key, cfg_key)):
        raise ValueError("native mesh/config exceeds source byte limit")
    sections = _sections(files[mesh_key].path.read_text(encoding="utf-8"))
    if sections.get("MeshFormat") != ["2.2 0 8"]:
        raise ValueError("only Gmsh 2.2 ASCII format is supported")
    nodes = _records(sections, "Nodes")
    if not nodes or any(len(row) != 4 for row in nodes):
        raise ValueError("invalid mesh nodes")
    ids = np.array([int(row[0]) for row in nodes], dtype=np.int64)
    coordinates = np.array([[float(v) for v in row[1:]] for row in nodes])
    if len(np.unique(ids)) != len(ids) or (ids <= 0).any() or not np.isfinite(coordinates).all():
        raise ValueError("mesh node IDs must be positive/unique and coordinates finite")
    node_set = set(ids.tolist())
    element_type, dimension, tag_index = (options.get(k) for k in ("element_type", "dimension", "grain_tag_index"))
    if type(element_type) is not int or element_type not in _ELEMENTS or type(dimension) is not int or _ELEMENTS[element_type][0] != dimension or type(tag_index) is not int or tag_index < 0:
        raise ValueError("explicit supported element_type/dimension/grain_tag_index required")
    selected, all_ids, counts = [], set(), Counter()
    for row in _records(sections, "Elements"):
        values = [int(v) for v in row]
        if len(values) < 3:
            raise ValueError("invalid mesh element record")
        eid, typ, ntags = values[:3]
        if typ not in _ELEMENTS or ntags < 0 or len(values) != 3 + ntags + _ELEMENTS[typ][1]:
            raise ValueError("unsupported or malformed Gmsh element type/connectivity")
        connectivity = values[3 + ntags:]
        if eid <= 0 or eid in all_ids or not set(connectivity) <= node_set:
            raise ValueError("duplicate element ID or missing mesh node endpoint")
        all_ids.add(eid)
        counts[typ] += 1
        if typ == element_type:
            if tag_index >= ntags:
                raise ValueError("grain tag index is absent from selected element")
            selected.append((eid, values[3 + tag_index], connectivity))
    if not selected:
        raise ValueError("no selected mesh elements")
    arrays = {"mesh_node_ids": ids, "mesh_coordinates": coordinates,
              "mesh_element_ids": np.array([r[0] for r in selected], dtype=np.int64),
              "mesh_grain_ids": np.array([r[1] for r in selected], dtype=np.int64),
              "mesh_connectivity": np.array([r[2] for r in selected], dtype=np.int64)}
    details = {"parent_file": mesh_key, "all_element_count": len(all_ids), "selected_element_count": len(selected),
               "element_type_counts": dict(counts), "element_type": element_type, "dimension": dimension,
               "grain_tag_index": tag_index, "connectivity_identity": "original_node_ids",
               "config_file": cfg_key, "native_config_lines": files[cfg_key].path.read_text(encoding="utf-8").splitlines(),
               "losses": ["only selected element type is normalized; all dimensions remain in native mesh"]}
    if "ElsetOrientations" in sections:
        rows = _records(sections, "ElsetOrientations")
        header = sections["ElsetOrientations"][0].split()
        if len(header) != 2 or header[1] not in {"rodrigues:active", "rodrigues:passive"} or any(len(r) != 4 for r in rows):
            raise ValueError("unsupported native orientation representation")
        grain_ids = np.array([int(r[0]) for r in rows], dtype=np.int64)
        rod = np.array([[float(v) for v in r[1:]] for r in rows])
        if len(np.unique(grain_ids)) != len(grain_ids) or not set(arrays["mesh_grain_ids"]) <= set(grain_ids) or not np.isfinite(rod).all():
            raise ValueError("invalid orientation/grain references")
        arrays.update(grain_ids=grain_ids, grain_rodrigues=rod)
        details["orientation_header"] = header[1]
        conversion = options.get("orientation_conversion")
        if conversion:
            if (set(conversion) != {"source", "target", "mapping_direction"} or conversion["source"] != header[1]
                    or conversion["target"] != "rotation_matrix"
                    or conversion["mapping_direction"] not in {"crystal_to_sample", "sample_to_crystal"}):
                raise ValueError("orientation conversion convention conflicts with native declaration")
            arrays["grain_rotations"] = np.array([_rodrigues_matrix(v, header[1].endswith("passive")) for v in rod])
            details["orientation_conversion"] = conversion
    elif options.get("orientation_conversion"):
        raise ValueError("orientation conversion requested but no native orientations exist")
    return arrays, {name: dict(details) for name in arrays}, []
