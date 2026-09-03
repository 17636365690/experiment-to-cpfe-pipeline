import os
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("EXP2CPFE_RUN_ABAQUS") != "1",
    reason="real Abaqus integration is opt-in via EXP2CPFE_RUN_ABAQUS=1",
)
def test_user_supplied_real_abaqus_stage():
    from experiment_to_cpfe.pipeline import run_abaqus_stage

    config = os.environ.get("EXP2CPFE_ABAQUS_CONFIG")
    run_dir = os.environ.get("EXP2CPFE_ABAQUS_RUN_DIR")
    if not config or not run_dir:
        pytest.skip("EXP2CPFE_ABAQUS_CONFIG and EXP2CPFE_ABAQUS_RUN_DIR are required")

    result = run_abaqus_stage(Path(config), Path(run_dir), "datacheck")
    assert result["status"] in {"completed", "blocked"}
