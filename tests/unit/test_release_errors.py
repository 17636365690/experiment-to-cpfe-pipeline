import json
import pytest
from experiment_to_cpfe.cli import main

@pytest.mark.parametrize('content', ['not: [valid', '{}'])
def test_invalid_configuration_produces_four_reports(tmp_path, content):
    config=tmp_path/'bad.yaml'; config.write_text(content)
    run=tmp_path/'run'
    assert main(['validate','--config',str(config),'--run-dir',str(run)]) == 1
    for name in ['validation.json','solver_readiness.json','qa_report.md','run_manifest.json']:
        assert (run/'reports'/name).is_file()
    assert json.loads((run/'reports/run_manifest.json').read_text())['stages'][-1]['status']=='failed'


def test_existing_simulated_records_are_not_overwritten(tmp_path,multimodal_sample_config):
    import shutil, yaml
    from experiment_to_cpfe import pipeline
    config=multimodal_sample_config
    payload=yaml.safe_load(config.read_text())
    source=dict(payload['sources'][0]); source['table_name']='simulation_records'; source['source_kind']='simulated'
    payload['sources'].append(source)
    config.write_text(yaml.safe_dump(payload))
    run=tmp_path/'run'; pipeline.run_validate(config,run)
    extracted=run/'solver/extracted'
    shutil.copytree('tests/fixtures/odb_extract_fixture',extracted)
    pipeline._record_stage(run,config,{'stage':'extract-odb','status':'completed','artifacts':[str(extracted/'metadata.json'),str(extracted/'frames.csv')],'limitations':['synthetic ledger']})
    result=pipeline.run_export(config,run,'hdf5')
    assert result['status']=='blocked'
    assert any('simulation_records' in s for s in result['limitations'])
    assert not (run/'dataset/sample.h5').exists()


@pytest.mark.parametrize('mode', ['no_template', 'bad_template'])
def test_unrenderable_template_leaves_blocked_stage_receipt(tmp_path, multimodal_sample_config, mode):
    import yaml
    from experiment_to_cpfe import pipeline
    config = multimodal_sample_config
    payload = yaml.safe_load(config.read_text())
    if mode == 'no_template':
        payload['abaqus']['template_path'] = None
    else:
        (config.parent/'template.inp').write_text('{{UNKNOWN_MARKER}}\n')
    config.write_text(yaml.safe_dump(payload))
    run = tmp_path/'run'
    pipeline.run_validate(config, run)
    result = pipeline.run_build_inp(config, run)
    assert result['status'] == 'blocked'
    receipt = json.loads((run/'reports/run_manifest.json').read_text())
    assert receipt['stages'][-1]['stage'] == 'build-inp'
    assert receipt['stages'][-1]['limitations']
    assert not (run/'input/model.inp').exists()
