"""Semantic gates for decoded arrays; never complete missing scientific metadata."""

import numpy as np

from experiment_to_cpfe.schema.models import OrientationSpec
from experiment_to_cpfe.schema.validation import _unit_is_declared


def semantic_issues(arrays, meanings, modality, names=None) -> list[str]:
    issues = []
    for name in meanings.keys() - arrays.keys():
        issues.append(f"{name}: meaning has no decoded array")
    for name in arrays if names is None else names:
        array = arrays[name]
        meaning = meanings.get(name)
        def issue(message):
            issues.append(f"{name}: {message}")
        if meaning is None:
            issue("semantic declaration is missing")
            continue
        for key in ("quantity", "evidence"):
            if not _unit_is_declared(getattr(meaning, key)):
                issue(f"{key} is unresolved")
        if meaning.source_kind is None:
            issue("source_kind is unresolved")
        if meaning.role in {"field", "tensor", "orientation", "target", "features", "mask", "index"} and array.dtype.kind not in "biuf":
            issue("physical fields/features/masks/indices require real numeric arrays")
            continue
        axes = meaning.axes
        if len(axes) != array.ndim or len(set(axes)) != len(axes) or any(not _unit_is_declared(v) for v in axes):
            issue("axes must explicitly name every array dimension uniquely")
        component_names = []
        for axis, names in meaning.components.items():
            if axis not in axes or axes.index(axis) >= array.ndim or array.shape[axes.index(axis)] != len(names) or len(set(names)) != len(names) or not all(_unit_is_declared(v) for v in names):
                issue(f"component names do not match axis {axis}")
            component_names.extend(names)
        if not _unit_is_declared(meaning.unit):
            if not component_names or set(meaning.component_units) != set(component_names) or not all(_unit_is_declared(v) for v in meaning.component_units.values()):
                issue("unit or complete component_units are unresolved")
        spatial = meaning.spatial
        if spatial is not None:
            valid_axes = (bool(spatial.axes) and len(set(spatial.axes)) == len(spatial.axes)
                          and set(spatial.axes) <= set(axes) and not set(spatial.axes).intersection(meaning.components))
            if not valid_axes or not len(spatial.axes) == len(spatial.origin) == len(spatial.spacing):
                issue("spatial axes/origin/spacing must agree and exclude component axes")
            if not np.isfinite(spatial.origin).all() or not np.isfinite(spatial.spacing).all() or any(v <= 0 for v in spatial.spacing):
                issue("spatial origin/spacing must be finite, with positive spacing")
            if not _unit_is_declared(spatial.unit) or not _unit_is_declared(spatial.coordinate_frame):
                issue("spatial unit and coordinate frame are unresolved")
            if meaning.coordinate_frame is not None and meaning.coordinate_frame != spatial.coordinate_frame:
                issue("coordinate_frame conflicts with spatial declaration")
        elif modality.value == "voxel_grid" and meaning.role not in {"id", "mask", "index", "target"}:
            issue("spatial metadata is required for voxel values")
        if (spatial is None and modality.value in {"mesh", "point_field", "orientation_map", "field_sequence"}
                and meaning.role in {"field", "tensor", "orientation"} and not _unit_is_declared(meaning.coordinate_frame)):
            issue("coordinate_frame is unresolved for spatial field/orientation")
        if meaning.role == "tensor" or meaning.tensor_order:
            if not meaning.tensor_order or len(set(meaning.tensor_order)) != len(meaning.tensor_order) or list(meaning.tensor_order) != component_names:
                issue("tensor_order must match explicitly ordered component names")
            if not _unit_is_declared(meaning.shear_convention):
                issue("tensor shear_convention is unresolved")
            if not _unit_is_declared(meaning.reference_state):
                issue("tensor reference_state is unresolved")
        if meaning.role == "orientation":
            orientation = dict(meaning.orientation or {})
            direction = orientation.pop("mapping_direction", None)
            if direction not in {"crystal_to_sample", "sample_to_crystal"}:
                issue("orientation mapping_direction is unresolved")
            try:
                declared = OrientationSpec.model_validate(orientation)
                if not _unit_is_declared(declared.convention) or not _unit_is_declared(declared.crystal_symmetry):
                    issue("orientation convention/symmetry is unresolved")
                if declared.representation == "quaternion":
                    component_axes = list(meaning.components)
                    axis = axes.index(component_axes[0]) if len(component_axes) == 1 and component_axes[0] in axes else -1
                    if (axis < 0 or axis >= array.ndim or array.shape[axis] != 4
                            or not np.allclose(np.linalg.norm(array, axis=axis), 1, rtol=0, atol=1e-6)):
                        issue("quaternion requires one explicitly named four-component axis and unit norms")
                elif declared.representation == "rotation_matrix":
                    if (array.shape[-2:] != (3, 3) or not np.isfinite(array).all()
                            or not np.allclose(array.swapaxes(-1, -2) @ array, np.eye(3), atol=1e-6, rtol=0)
                            or not np.allclose(np.linalg.det(array), 1, atol=1e-6, rtol=0)):
                        issue("rotation_matrix requires orthonormal 3x3 matrices with determinant +1")
                elif declared.representation == "euler":
                    component_axes = list(meaning.components)
                    axis = axes.index(component_axes[0]) if len(component_axes) == 1 and component_axes[0] in axes else -1
                    if axis < 0 or axis >= array.ndim or array.shape[axis] != 3:
                        issue("Euler orientations require one explicitly named three-component axis")
            except ValueError:
                issue("orientation convention/units/symmetry are unresolved")
        if meaning.role == "id":
            if array.ndim != 1 or array.dtype.kind not in "iuSU" or len(np.unique(array)) != array.size:
                issue("IDs must be a unique one-dimensional integer/string array")
            if not _unit_is_declared(meaning.identity_scope):
                issue("ID identity_scope is unresolved; row positions do not establish tracking")
        if meaning.entity_ids:
            ids = arrays.get(meaning.entity_ids)
            if (ids is None or ids.ndim != 1 or ids.dtype.kind not in "iuSU" or len(np.unique(ids)) != ids.size
                    or not 0 <= meaning.entity_axis < array.ndim or len(ids) != array.shape[meaning.entity_axis]):
                issue("entity_ids must be unique and align with the declared entity_axis")
            if not _unit_is_declared(meaning.identity_scope):
                issue("entity identity_scope is unresolved")
        if meaning.quality:
            quality = meaning.quality
            mask = arrays.get(quality.array)
            if (mask is None or len(set(quality.axes)) != len(quality.axes) or any(i < 0 or i >= array.ndim for i in quality.axes)
                    or mask.shape != tuple(array.shape[i] for i in quality.axes) or not quality.valid_values):
                issue("quality mask must align with explicitly declared axes and valid_values")
        if array.dtype.kind in "fc" and not np.isfinite(array).all():
            issue("nonfinite values retained in draft; select an explicit finite subset before promotion")
        if meaning.role == "target":
            if not all(_unit_is_declared(getattr(meaning, key)) for key in ("group_id", "split", "target_origin")):
                issue("target requires group_id, split and target_origin")
    return issues


def verify_native_asset_semantics(sample):
    """Recheck modeled native semantics on canonical write/read, including cross-array links."""
    from experiment_to_cpfe.adapters.native_models import ArrayMeaning
    target_groups = {}
    for asset in sample.assets:
        metadata = asset.descriptive_metadata
        if "meaning" not in metadata or asset.format != "numpy-array":
            continue
        key = metadata.get("array_key")
        if key not in sample.arrays:
            raise ValueError("native semantic asset has no matching array")
        meaning = ArrayMeaning.model_validate(metadata["meaning"])
        issues = semantic_issues(sample.arrays, {key: meaning}, asset.modality, names=[key])
        selection = metadata.get("selection", {})
        if selection.get("required_role") and meaning.role != selection["required_role"]:
            issues.append("native profile semantic role is inconsistent")
        if selection.get("requires_tensor") and not meaning.tensor_order:
            issues.append("stiffness tensor conventions are missing")
        issues += alignment_issues(sample.arrays, metadata.get("alignment_checks", []))
        expected_units = {key: meaning.unit} if meaning.unit else meaning.component_units
        if asset.units != expected_units or asset.axis_order != meaning.axes or asset.source_kind != meaning.source_kind:
            issues.append("native units, axes or evidence conflict with asset declaration")
        frame = meaning.spatial.coordinate_frame if meaning.spatial else meaning.coordinate_frame
        if asset.coordinate_frame != frame:
            issues.append("native coordinate_frame conflicts with asset declaration")
        if meaning.role == "target" and meaning.group_id:
            previous = target_groups.setdefault(meaning.group_id, meaning.split)
            if previous != meaning.split:
                issues.append("target group cannot appear in different dataset splits")
        if issues:
            raise ValueError("native semantic validation failed: " + "; ".join(issues))


def alignment_issues(arrays, checks):
    issues = []
    for check in checks:
        if set(check) - {"arrays", "axis", "identity_scope", "evidence"}:
            raise ValueError("unknown alignment check options")
        names, axis = check.get("arrays", []), check.get("axis")
        if not isinstance(names, (list, tuple)) or len(names) < 2 or type(axis) is not int or axis < 0:
            raise ValueError("alignment checks require at least two arrays and a nonnegative axis")
        if not all(_unit_is_declared(check.get(k)) for k in ("identity_scope", "evidence")):
            issues.append("alignment requires scoped identity evidence; equal row counts alone are insufficient")
        elif any(name not in arrays or arrays[name].ndim <= axis for name in names):
            issues.append("alignment array/axis is missing")
        elif len({arrays[name].shape[axis] for name in names}) != 1:
            issues.append("alignment row counts differ within declared identity_scope")
    return issues
