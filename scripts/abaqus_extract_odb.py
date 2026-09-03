"""Run inside Abaqus Python to extract ODB fields to JSON/CSV records."""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import os


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
    result.add_argument("--position", default="integration_point")
    return result


def main():
    args = parser().parse_args()
    from odbAccess import openOdb

    if not os.path.isdir(args.output_dir):
        os.makedirs(args.output_dir)
    requested = [item for item in args.fields.split(",") if item]
    rows = []
    seen = set()
    odb = None
    try:
        odb = openOdb(path=args.odb, readOnly=True)
        for step_name, step in odb.steps.items():
            for frame_index, frame in enumerate(step.frames):
                available = frame.fieldOutputs
                for requested_name in requested:
                    names = [requested_name] if requested_name in available else []
                    if requested_name in ("STATEV", "SDV"):
                        names = sorted(name for name in available.keys() if name.startswith("SDV"))
                    for field_name in names:
                        seen.add(requested_name)
                        field = available[field_name]
                        for value in field.values:
                            data = value.data
                            if not isinstance(data, (tuple, list)):
                                data = (data,)
                            labels = getattr(field, "componentLabels", ())
                            for component_index, component_value in enumerate(data):
                                component = (
                                    labels[component_index]
                                    if component_index < len(labels)
                                    else str(component_index)
                                )
                                rows.append({
                                    "step": step_name,
                                    "frame": frame_index,
                                    "frame_time": frame.frameValue,
                                    "increment_id": "%s:%s" % (step_name, frame_index),
                                    "field": field_name,
                                    "element_label": getattr(value, "elementLabel", ""),
                                    "integration_point": getattr(value, "integrationPoint", ""),
                                    "component": component,
                                    "value": component_value,
                                })
    finally:
        if odb is not None:
            odb.close()

    frames_path = os.path.join(args.output_dir, "frames.csv")
    fieldnames = [
        "step", "frame", "frame_time", "increment_id", "field",
        "element_label", "integration_point", "component", "value",
    ]
    with open(frames_path, "w") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    metadata = {
        "extraction_version": "0.1",
        "odb_path": os.path.abspath(args.odb),
        "odb_sha256": sha256_file(args.odb),
        "requested_fields": requested,
        "missing_fields": [name for name in requested if name not in seen],
        "position": args.position,
    }
    with open(os.path.join(args.output_dir, "metadata.json"), "w") as stream:
        json.dump(metadata, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
