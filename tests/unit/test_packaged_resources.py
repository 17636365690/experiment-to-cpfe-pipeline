import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


def test_release_ci_covers_windows_linux_and_installed_wheel():
    import yaml
    jobs = yaml.safe_load(Path('.github/workflows/tests.yml').read_text())['jobs']
    offline = jobs['offline']
    assert set(offline['strategy']['matrix']['os']) == {'ubuntu-latest', 'windows-latest'}
    assert any(step.get('env', {}).get('EXP2CPFE_WHEEL_DIR') == 'dist'
               and 'test_installed_wheel' in step.get('run', '') for step in offline['steps'])


def test_package_has_readme_and_type_marker():
    import tomllib
    metadata = tomllib.loads(Path('pyproject.toml').read_text())['project']
    assert metadata['readme'] == 'README.md'
    assert Path('src/experiment_to_cpfe/py.typed').is_file()


@pytest.mark.parametrize('resource', ['policy', 'extractor'])
def test_resources_work_when_package_is_relocated_outside_checkout(tmp_path, resource):
    import experiment_to_cpfe

    isolated = tmp_path/'site'
    shutil.copytree(Path(experiment_to_cpfe.__file__).parent, isolated/'experiment_to_cpfe',
                    ignore=shutil.ignore_patterns('__pycache__'))
    code = """
import sys
from pathlib import Path
import subprocess
sys.path.insert(0, sys.argv[1])
import experiment_to_cpfe
assert Path(experiment_to_cpfe.__file__).is_relative_to(Path(sys.argv[1]))
if sys.argv[2] == 'policy':
    from experiment_to_cpfe.pipeline import _default_policy_path
    from experiment_to_cpfe.schema.validation import load_validation_policy
    assert load_validation_policy(_default_policy_path()).require_finite
else:
    from experiment_to_cpfe.solvers.abaqus.extraction import ExtractionRequest, build_abaqus_extraction_command
    command = build_abaqus_extraction_command(ExtractionRequest(Path('x.odb'),Path('out'),('S',),'integration_point'),('abaqus',))
    script = Path(command[2])
    assert script.is_relative_to(Path(sys.argv[1]))
    result = subprocess.run([sys.executable,str(script),'--help'],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
"""
    result = subprocess.run([sys.executable, '-c', code, str(isolated), resource],
                            cwd=tmp_path, env={**os.environ, 'PYTHONPATH': str(isolated)},
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
