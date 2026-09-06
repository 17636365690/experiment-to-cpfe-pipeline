"""Decode partial assets and promote only explicitly described numerical outputs."""

from dataclasses import dataclass

import numpy as np

from experiment_to_cpfe.adapters.native_models import NativeImportConfig
from experiment_to_cpfe.adapters.native_numeric import read_numeric
from experiment_to_cpfe.adapters.native_semantics import semantic_issues, alignment_issues
from experiment_to_cpfe.assets.models import AssetRef, ConversionRecord
from experiment_to_cpfe.assets.registry import array_payload_sha256
from experiment_to_cpfe.provenance.hashing import sha256_file


@dataclass
class NativeDraft:
    config: NativeImportConfig
    arrays: dict[str, np.ndarray]
    descriptions: dict[str, dict]
    source_hashes: dict[str, str]
    payload_hashes: dict[str, str]
    blockers: list[str]

    def report(self):
        return {"import_id": self.config.import_id, "profile": self.config.profile,
                "decoding": "passed", "semantic_conversion": "blocked" if self.blockers else "eligible",
                "complete_sample": "requires_explicit_sample_metadata_and_validation",
                "solver_readiness": "not_evaluated", "physical_validation": "not_performed",
                "source_hashes": self.source_hashes, "blockers": self.blockers,
                "arrays": {name: {"shape": list(a.shape), "dtype": a.dtype.str,
                           "payload_sha256": self.payload_hashes[name],
                           "nonfinite_count": int(np.count_nonzero(~np.isfinite(a))) if a.dtype.kind in "fc" else 0,
                           "description": self.descriptions[name],
                           "meaning": self.config.meanings[name].model_dump(mode="json") if name in self.config.meanings else None}
                           for name, a in self.arrays.items()}}


def decode_native(config: NativeImportConfig) -> NativeDraft:
    if config.profile != "numeric" and config.selections:
        raise ValueError("selections apply only to numeric imports; use the profile's options")
    hashes = {key: sha256_file(f.path) for key, f in config.files.items()}
    for key, f in config.files.items():
        if f.expected_sha256 and f.expected_sha256.lower() != hashes[key]:
            raise ValueError(f"native source hash mismatch: {key}")
    arrays, descriptions, blockers = {}, {}, []
    if config.profile == "numeric":
        if config.options or not config.selections:
            raise ValueError("numeric import requires selections and no profile options")
        for name, selection in config.selections.items():
            if selection.file not in config.files:
                raise ValueError(f"selection refers to missing source file: {selection.file}")
            source = config.files[selection.file]
            if "format" in selection.selector and selection.selector["format"] != source.format:
                raise ValueError("selection format conflicts with source format")
            arrays[name], descriptions[name] = read_numeric(source.path, {**selection.selector, "format": source.format})
            descriptions[name]["parent_file"] = selection.file
    elif config.profile == "gmsh22":
        from experiment_to_cpfe.adapters.native_mesh import read_mesh
        arrays, descriptions, blockers = read_mesh(config.files, config.options)
    elif config.profile == "grain_graph":
        from experiment_to_cpfe.adapters.native_graph import read_graph
        arrays, descriptions, blockers = read_graph(config.files, config.options)
    elif config.profile == "stiffness":
        from experiment_to_cpfe.adapters.native_stiffness import read_stiffness
        arrays, descriptions, blockers = read_stiffness(config.files, config.options)
    else:
        raise ValueError(f"profile is not implemented: {config.profile}")
    if not arrays:
        raise ValueError("native import produced no arrays")
    for name in (*arrays, config.import_id, *config.files):
        if name in {"", ".", ".."} or any(c in name for c in ("/", "\\", "\0")):
            raise ValueError("native IDs and array names must be single path components")
    for key, f in config.files.items():
        if sha256_file(f.path) != hashes[key]:
            raise ValueError(f"native source changed during decoding: {key}")
    required_roles = {
        "grain_graph": {"graph_node_ids": "id", "graph_node_features": "features", "graph_edge_index": "index", "graph_targets": "target"},
        "stiffness": {"sample_ids": "id", "stiffness_labels": "target"},
        "gmsh22": {"mesh_node_ids": "id", "mesh_coordinates": "field", "mesh_element_ids": "id",
                   "mesh_connectivity": "index", "grain_ids": "id", "grain_rotations": "orientation"},
    }.get(config.profile, {})
    for name, role in required_roles.items():
        if name not in arrays:
            continue
        descriptions[name]["required_role"] = role
        meaning = config.meanings.get(name)
        if meaning is not None and meaning.role != role:
            blockers.append(f"{name}: profile requires semantic role {role}")
    if config.profile == "stiffness":
        descriptions["stiffness_labels"]["requires_tensor"] = True
        meaning = config.meanings.get("stiffness_labels")
        if meaning is not None and not meaning.tensor_order:
            blockers.append("stiffness_labels: tensor_order, shear convention and reference state are required")
    blockers += semantic_issues(arrays, config.meanings, config.modality)
    blockers += alignment_issues(arrays, config.checks)
    for name, meaning in config.meanings.items():
        if name in descriptions and meaning.source_kind is not None:
            parent = config.files[descriptions[name]["parent_file"]]
            if meaning.source_kind != parent.source_kind:
                blockers.append(f"{name}: source_kind differs from its source; use a separate explicitly classified source view")
    return NativeDraft(config, arrays, descriptions, hashes,
                       {k: array_payload_sha256(a) for k, a in arrays.items()}, blockers)


def promote_native(draft: NativeDraft) -> tuple[dict[str, np.ndarray], tuple[AssetRef, ...]]:
    """Return arrays and lineage assets; complete sample and solver gates remain separate."""
    blockers = [*draft.blockers, *semantic_issues(draft.arrays, draft.config.meanings, draft.config.modality),
                *alignment_issues(draft.arrays, draft.config.checks)]
    if blockers:
        raise ValueError("native semantic promotion blocked: " + "; ".join(dict.fromkeys(blockers)))
    config = draft.config
    for key, source in config.files.items():
        if sha256_file(source.path) != draft.source_hashes[key]:
            raise ValueError(f"native source changed before promotion: {key}")
    for key, array in draft.arrays.items():
        if array_payload_sha256(array) != draft.payload_hashes[key]:
            raise ValueError(f"native array changed before promotion: {key}")
    assets = []
    for key, source in config.files.items():
        assets.append(AssetRef(asset_id=f"{config.import_id}:source:{key}", parent_asset_id=None,
            modality=config.modality, format=source.format, uri=str(source.path), source_kind=source.source_kind,
            layer="raw", units={}, coordinate_frame=None, axis_order=(), dtype=None, shape=(),
            native_layout=source.native_layout, sha256=draft.source_hashes[key], license=source.license,
            lossy_transformations=(), descriptive_metadata={"source_uri": source.source_uri}))
    dependencies = {asset.asset_id: asset.sha256 for asset in assets}
    for name, array in draft.arrays.items():
        meaning = config.meanings[name]
        description = draft.descriptions[name]
        parent_key = description["parent_file"]
        source = config.files[parent_key]
        digest = draft.payload_hashes[name]
        units = {name: meaning.unit} if meaning.unit else meaning.component_units
        assets.append(AssetRef(asset_id=f"{config.import_id}:{name}:normalized",
            parent_asset_id=f"{config.import_id}:source:{parent_key}", modality=config.modality,
            format="numpy-array", uri=f"hdf5:/derived/arrays/{name}", source_kind=meaning.source_kind,
            layer="curated", units=units, coordinate_frame=meaning.spatial.coordinate_frame if meaning.spatial else meaning.coordinate_frame,
            axis_order=meaning.axes, dtype=array.dtype.str, shape=array.shape,
            native_layout=f"{config.profile}:explicit-array", sha256=digest, license=source.license,
            lossy_transformations=tuple(description.get("losses", ())),
            conversion=ConversionRecord(original_format=source.format, target_format="numpy-array",
                source_sha256=draft.source_hashes[parent_key], hash_scope="logical_payload",
                target_payload_sha256=digest, source_hash_verified=True),
            descriptive_metadata={"array_key": name, "payload_hash_encoding": "numpy-array-v1",
                "meaning": meaning.model_dump(mode="json"), "selection": description,
                "dependency_hashes": dependencies, "alignment_checks": list(config.checks)}))
    return dict(draft.arrays), tuple(assets)
