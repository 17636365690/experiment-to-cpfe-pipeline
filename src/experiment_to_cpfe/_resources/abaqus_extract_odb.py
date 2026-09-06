"""Standalone packaged script: run inside Abaqus Python, not host Python."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os
import math
import sys

if __package__:
    from .field_contract import CSV_COLUMNS, FIELD_CONTRACT_VERSION
else:
    # Direct `abaqus python path/to/script.py` and the checkout runpy launcher
    # must resolve this sibling without importing host package dependencies.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from field_contract import CSV_COLUMNS, FIELD_CONTRACT_VERSION


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parser():
    result = argparse.ArgumentParser(description="Extract Abaqus ODB field records")
    result.add_argument("--odb", required=True)
    result.add_argument("--output-dir", required=True)
    result.add_argument("--fields", required=True)
    result.add_argument("--position", default="integration_point", choices=(
        "integration_point", "nodal", "element_nodal", "element_face", "centroid", "native"))
    result.add_argument("--max-records", type=int, default=1000000)
    return result


def main():
    args = parser().parse_args()
    if os.path.exists(args.output_dir):
        raise ValueError("output directory already exists; choose a new directory")
    if args.max_records < 1:
        raise ValueError("max-records must be positive")
    requested = [item.strip() for item in args.fields.split(",") if item.strip()]
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("fields must be nonempty and unique")
    from odbAccess import openOdb

    os.makedirs(args.output_dir)
    frames_path = os.path.join(args.output_dir, "frames.csv")
    # Abaqus 2025 uses Python 3; the standalone script also keeps CSV-compatible
    # file modes for older Abaqus Python 2 installations (not verified here).
    stream = open(frames_path, "wb") if sys.version_info[0] < 3 else open(frames_path, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    missing_by_frame = []
    descriptors = []
    errors = []
    count = 0
    frame_count = 0
    odb = None
    try:
        odb = openOdb(path=args.odb, readOnly=True)
        for step_name, step in odb.steps.items():
            for frame_index, frame in enumerate(step.frames):
                frame_count += 1
                available = frame.fieldOutputs
                domain = str(frame.domain)
                for requested_name in requested:
                    names = [requested_name] if requested_name in available else []
                    if requested_name in ("STATEV", "SDV"):
                        names = sorted(name for name in available.keys() if name.startswith("SDV"))
                    before = count
                    for field_name in names:
                        field = available[field_name]
                        if getattr(field, "isComplex", False):
                            raise ValueError("complex fields are not supported; imaginary data would be lost")
                        labels = tuple(field.componentLabels)
                        descriptors.append({
                            "step": step_name, "frame": frame_index, "field": field_name,
                            "type": str(field.type), "component_labels": list(labels),
                            "is_engineering_tensor": (bool(field.isEngineeringTensor)
                                                      if hasattr(field, "isEngineeringTensor") else None),
                        })
                        for value in field.values:
                            position = str(value.position)
                            if args.position != "native" and position != args.position.upper():
                                continue
                            precision = str(value.precision)
                            if precision not in ("SINGLE_PRECISION", "DOUBLE_PRECISION"):
                                raise ValueError("unsupported field precision: " + precision)
                            double = precision == "DOUBLE_PRECISION"
                            data = value.dataDouble if double else value.data
                            try:
                                data = tuple(data)
                            except TypeError:
                                data = (data,)
                            if labels and len(labels) != len(data):
                                raise ValueError("component labels do not match field data")
                            if len(data) != 1 and not labels:
                                raise ValueError("vector/tensor field lacks component labels")
                            section = getattr(value, "sectionPoint", None)
                            local = getattr(value, "localCoordSystemDouble" if double else "localCoordSystem", None)
                            for component_index, component_value in enumerate(data):
                                if count >= args.max_records:
                                    raise ValueError("record limit exceeded; partial output is not complete")
                                if math.isnan(float(component_value)) or math.isinf(float(component_value)):
                                    raise ValueError("nonfinite field value")
                                component = (
                                    labels[component_index]
                                    if component_index < len(labels)
                                    else field_name
                                )
                                writer.writerow({
                                    "step": step_name,
                                    "frame": frame_index,
                                    "increment_number": frame.incrementNumber,
                                    "frame_value": frame.frameValue,
                                    "domain": domain,
                                    "frame_time": frame.frameValue if domain == "TIME" else "",
                                    "increment_id": "%s:%s" % (step_name, frame_index),
                                    "load_case": getattr(getattr(frame, "loadCase", None), "name", ""),
                                    "field": field_name,
                                    "position": position,
                                    "instance": value.instance.name,
                                    "element_label": value.elementLabel if position in ("INTEGRATION_POINT", "ELEMENT_NODAL", "ELEMENT_FACE", "CENTROID") else "",
                                    "node_label": value.nodeLabel if position in ("NODAL", "ELEMENT_NODAL") else "",
                                    "integration_point": value.integrationPoint if position == "INTEGRATION_POINT" else "",
                                    "face": getattr(value, "face", "") if position == "ELEMENT_FACE" else "",
                                    "section_point": getattr(section, "number", ""),
                                    "section_description": getattr(section, "description", ""),
                                    "precision": precision,
                                    "local_coord_system": json.dumps(local) if local is not None else "",
                                    "component": component,
                                    "value": float(component_value),
                                })
                                count += 1
                    if count == before:
                        missing_by_frame.append({"step": step_name, "frame": frame_index,
                                                 "field": requested_name,
                                                 "reason": "no stored values at requested position"})
    except Exception as exc:
        errors.append("%s: %s" % (type(exc).__name__, exc))
    finally:
        stream.close()
        if odb is not None:
            odb.close()
    if frame_count == 0:
        errors.append("ODB contains no readable frames")
    missing = sorted(set(item["field"] for item in missing_by_frame))
    complete = not errors and not missing and count > 0
    metadata = {
        "extraction_version": "0.2",
        "field_contract_version": FIELD_CONTRACT_VERSION,
        "odb_path": os.path.abspath(args.odb),
        "odb_sha256": sha256_file(args.odb),
        "requested_fields": requested,
        "missing_fields": missing,
        "missing_by_frame": missing_by_frame,
        "position": args.position,
        "complete": complete,
        "errors": errors,
        "record_count": count,
        "max_records": args.max_records,
        "field_descriptors": descriptors,
        "time_basis": "frame_value has frame domain; frame_time is step-relative for TIME only",
        "transformations": ["stored field/component selection and flattening; no extrapolation or basis conversion"],
    }
    with open(os.path.join(args.output_dir, "metadata.json"), "w") as stream:
        json.dump(metadata, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
