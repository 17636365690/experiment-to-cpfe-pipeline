"""Checkout-compatible launcher; implementation is shipped in the package."""

import os
import runpy

if __name__ == "__main__":
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src",
                          "experiment_to_cpfe", "_resources", "abaqus_extract_odb.py")
    runpy.run_path(script, run_name="__main__")
