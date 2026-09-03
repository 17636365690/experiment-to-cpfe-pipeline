"""Small subprocess fixture that mimics Abaqus artifact behavior."""

import os
from pathlib import Path
import sys


def argument(prefix: str, default: str) -> str:
    for value in sys.argv[1:]:
        if value.startswith(prefix):
            return value.split("=", 1)[1]
    return default


job = argument("job=", "job")
is_datacheck = "datacheck" in sys.argv[1:]
if os.environ.get("FAKE_SOLVER_COMPILE_SUCCESS") == "1":
    print("FORTRAN COMPILE SUCCESS")
    print("FORTRAN LINK SUCCESS")
if os.environ.get("FAKE_SOLVER_NO_OUTPUT") == "1":
    raise SystemExit(0)

Path(f"{job}.dat").write_text("DATACHECK COMPLETE\n", encoding="ascii")
Path(f"{job}.msg").write_text("NO ERRORS\n", encoding="ascii")
if not is_datacheck:
    status = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n"
    if os.environ.get("FAKE_SOLVER_ABORT") == "1":
        status = "THE ANALYSIS HAS BEEN ABORTED\n"
    Path(f"{job}.sta").write_text(status, encoding="ascii")
    Path(f"{job}.odb").write_bytes(b"synthetic fake odb evidence")
