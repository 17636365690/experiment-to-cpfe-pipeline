import json
from pathlib import Path
import sys
import yaml

def test_configured_ascii_workspace_is_used_and_results_archived(tmp_path, multimodal_sample_config,monkeypatch):
    from experiment_to_cpfe import pipeline
    monkeypatch.delenv('EXP2CPFE_ABAQUS_COMMAND',raising=False)
    config=multimodal_sample_config
    data=yaml.safe_load(config.read_text())
    ascii_root=tmp_path/'scratch'
    data['abaqus']['ascii_temp_root']=str(ascii_root)
    data['abaqus']['command']=[sys.executable,str(Path('tests/fixtures/fake_solver.py').resolve())]
    config.write_text(yaml.safe_dump(data))
    run=tmp_path/'run'
    assert pipeline.run_validate(config,run)['status']=='completed'
    assert pipeline.run_build_inp(config,run)['status']=='completed'
    result=pipeline.run_abaqus_stage(config,run,'datacheck')
    assert result['status']=='completed'
    assert Path(result['work_dir']).is_relative_to(ascii_root)
    assert (run/'solver/datacheck/synthetic.dat').is_file()
    assert all(Path(p).is_relative_to(run) for p in result['artifacts'])
