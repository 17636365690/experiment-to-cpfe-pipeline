"""Explicit scalar ASCII VTK ImageData subset, without the VTK runtime."""

from pathlib import Path
import math
import xml.etree.ElementTree as ET

import numpy as np


_DTYPES = {"Int8": "int8", "UInt8": "uint8", "Int16": "int16", "UInt16": "uint16",
           "Int32": "int32", "UInt32": "uint32", "Int64": "int64", "UInt64": "uint64",
           "Float32": "float32", "Float64": "float64"}


def load_vti_scalar(path: Path, config: dict[str, object]) -> tuple[dict[str, object], np.ndarray]:
    """Load one full-extent Piece and one scalar PointData/3D CellData array.

    VTK indexes x fastest. Returned arrays and origin/spacing are z,y,x.
    ``origin`` identifies the first returned sample (cell center for CellData);
    the native VTK index-zero origin and extents remain explicit metadata.
    """
    for name in ("array_name", "association", "units", "value_units", "coordinate_frame", "axis_order"):
        if name not in config or config[name] in (None, "", []):
            raise ValueError(f"VTI {name} is required")
    if tuple(config["axis_order"]) != ("z", "y", "x"):
        raise ValueError("VTI scalar arrays require explicit axis_order z,y,x")
    association = config["association"]
    if association not in {"PointData", "CellData"}:
        raise ValueError("VTI association must be PointData or CellData")
    data = Path(path).read_bytes()
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data or b"<AppendedData" in data:
        raise ValueError("VTI DTD/entities and appended data are unsupported")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError(f"invalid VTI XML: {exc}") from exc
    if root.tag != "VTKFile" or root.get("type") != "ImageData":
        raise ValueError("VTI reader requires serial VTKFile ImageData")
    images = root.findall("ImageData")
    if len(images) != 1 or len(images[0].findall("Piece")) != 1:
        raise ValueError("VTI requires exactly one ImageData and one Piece")
    image = images[0]
    piece = image.find("Piece")

    def numbers(element, name, count, cast):
        try:
            values = tuple(cast(token) for token in element.attrib[name].split())
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"VTI {name} must be explicitly specified") from exc
        if len(values) != count:
            raise ValueError(f"VTI {name} requires {count} components")
        return values

    extent = numbers(piece, "Extent", 6, int)
    if extent != numbers(image, "WholeExtent", 6, int):
        raise ValueError("VTI partial Piece extents are unsupported")
    native_origin = numbers(image, "Origin", 3, float)
    native_spacing = numbers(image, "Spacing", 3, float)
    if "Direction" in image.attrib and numbers(image, "Direction", 9, float) != (1, 0, 0, 0, 1, 0, 0, 0, 1):
        raise ValueError("VTI rotated Direction matrices are unsupported")
    point_shape = tuple(extent[2 * axis + 1] - extent[2 * axis] + 1 for axis in range(3))
    if any(size < 1 for size in point_shape):
        raise ValueError("VTI extents must define nonempty point dimensions")
    if association == "CellData" and any(size < 2 for size in point_shape):
        raise ValueError("VTI CellData currently requires full 3D cells")
    shape = point_shape if association == "PointData" else tuple(size - 1 for size in point_shape)
    selected = [a for a in piece.findall(f"{association}/DataArray") if a.get("Name") == config["array_name"]]
    if len(selected) != 1:
        raise ValueError("VTI selected array_name must identify exactly one array in association")
    field = selected[0]
    if field.get("format") != "ascii" or field.get("NumberOfComponents", "1") != "1":
        raise ValueError("VTI supports selected ASCII scalar arrays only")
    if field.get("type") not in _DTYPES:
        raise ValueError("VTI selected array has an unsupported scalar dtype")
    tokens = (field.text or "").split()
    if len(tokens) != math.prod(shape):
        raise ValueError("VTI scalar value count disagrees with extent/association")
    try:
        array = np.asarray(tokens, dtype=_DTYPES[field.get("type")]).reshape(shape[::-1])
    except (ValueError, OverflowError) as exc:
        raise ValueError("VTI scalar values do not match declared dtype") from exc
    offset = 0.0 if association == "PointData" else 0.5
    origin = tuple(native_origin[axis] + (extent[2 * axis] + offset) * native_spacing[axis] for axis in range(3))[::-1]
    spacing = native_spacing[::-1]
    for name, actual in (("origin", origin), ("spacing", spacing)):
        if name in config and tuple(config[name]) != actual:
            raise ValueError(f"VTI {name} conflicts with file geometry")
    metadata = {"origin": origin, "spacing": spacing, "axis_order": ("z", "y", "x"),
        "vtk_origin_xyz": native_origin, "vtk_spacing_xyz": native_spacing, "vtk_extent": extent,
        "association": association, "array_name": config["array_name"], "value_units": config["value_units"],
        "sampling_location": "points" if association == "PointData" else "cell_centers",
        "vtk_byte_order": root.get("byte_order"), "vtk_scalar_type": field.get("type"),
        "native_layout": "vtk_image_data_single_piece_ascii_scalar_x_fastest",
        "lossy_transformations": (*config.get("lossy_transformations", ()),
             "Only the selected scalar array is normalized; other VTI arrays and headers remain in the raw source")}
    return metadata, array
