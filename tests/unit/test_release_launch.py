"""Release regressions for the public fixture and configured process boundary."""

from pathlib import Path
import subprocess
import sys

import pytest
import yaml


def test_public_small_strain_example_declares_actual_field_and_full_bottom_face():
    payload = yaml.safe_load(Path('examples/synthetic_minimal/sample.yaml').read_text())
    assert payload['abaqus']['required_fields'] == ['S', 'E', 'U', 'RF']
    assert payload['abaqus']['field_units']['E'] == '1'
    assert 'E' in payload['solver_inputs']['output_variables']
    assert any(b['target'] == '3' and b['first_dof'] == b['last_dof'] == 3
               and b['value'] == 0 for b in payload['solver_inputs']['boundary_conditions'])
    assert '3, 3, 3, 0.0' in payload['solver_inputs']['inp_replacements']['BOUNDARY_CONDITIONS']


@pytest.mark.parametrize('unsafe', ['a&b.inp', 'a%TEMP%.inp', 'a!b.inp', 'a^b.inp'])
def test_batch_metacharacters_never_reach_process(tmp_path, monkeypatch, unsafe):
    from experiment_to_cpfe.solvers.abaqus import runner
    inp = tmp_path / unsafe
    inp.write_text('*HEADING\n')
    request = runner.AbaqusRunRequest(('abaqus.bat',), 'safe', inp, tmp_path/'job',
                                    runner.SolverStage.DATACHECK, None, 1, 10)
    monkeypatch.setattr(runner, '_execute_process', lambda *a, **k: pytest.fail('unsafe command launched'))
    result = runner.run_abaqus(request)
    assert result.status == 'blocked'
    assert 'shell' in ' '.join(result.limitations).lower()


@pytest.mark.parametrize('mode', ['env', 'timeout'])
def test_extraction_uses_same_command_override_and_records_timeout(tmp_path, multimodal_sample_config, monkeypatch, mode):
    from experiment_to_cpfe import pipeline
    config = multimodal_sample_config
    payload = yaml.safe_load(config.read_text())
    payload['abaqus']['command'] = [sys.executable, str(Path('tests/fixtures/fake_solver.py').resolve())]
    config.write_text(yaml.safe_dump(payload))
    monkeypatch.delenv('EXP2CPFE_ABAQUS_COMMAND', raising=False)
    run = tmp_path / 'run'
    assert pipeline.run_validate(config, run)['status'] == 'completed'
    assert pipeline.run_build_inp(config, run)['status'] == 'completed'
    for stage in ('datacheck', 'analysis'):
        assert pipeline.run_abaqus_stage(config, run, stage)['status'] == 'completed'
    monkeypatch.setenv('EXP2CPFE_ABAQUS_COMMAND', 'override-abaqus')
    def execute(command, **kwargs):
        if mode == 'env':
            assert command[0] == 'override-abaqus'
            raise FileNotFoundError('synthetic unavailable command')
        raise subprocess.TimeoutExpired(command, 1, output=b'partial extraction', stderr=b'timeout')
    monkeypatch.setattr(pipeline, 'execute_process', execute)
    # Both API and CLI must leave a terminal receipt, not an uncaught timeout.
    result = pipeline.run_extract_odb(config, run)
    assert result['status'] == ('blocked' if mode == 'env' else 'failed')
    assert result['limitations']
