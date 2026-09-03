"""Command-line interface for explicit pipeline stages."""

import argparse
import json
from pathlib import Path
import sys

from experiment_to_cpfe.pipeline import (
    inspect_run,
    run_abaqus_stage,
    run_build_inp,
    run_export,
    run_extract_odb,
    run_validate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "build-inp", "extract-odb"):
        command = commands.add_parser(name)
        command.add_argument("--config", required=True, type=Path)
        command.add_argument("--run-dir", required=True, type=Path)
    run = commands.add_parser("run-abaqus")
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--run-dir", required=True, type=Path)
    run.add_argument("--stage", required=True, choices=("datacheck", "analysis"))
    export = commands.add_parser("export")
    export.add_argument("--config", required=True, type=Path)
    export.add_argument("--run-dir", required=True, type=Path)
    export.add_argument("--format", required=True, choices=("hdf5", "npz", "pyg"))
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--run-dir", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    try:
        if args.command == "validate":
            result = run_validate(args.config, args.run_dir)
        elif args.command == "build-inp":
            result = run_build_inp(args.config, args.run_dir)
        elif args.command == "run-abaqus":
            result = run_abaqus_stage(args.config, args.run_dir, args.stage)
        elif args.command == "extract-odb":
            result = run_extract_odb(args.config, args.run_dir)
        elif args.command == "export":
            result = run_export(args.config, args.run_dir, args.format)
        else:
            print(json.dumps(inspect_run(args.run_dir), indent=2, sort_keys=True))
            return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
