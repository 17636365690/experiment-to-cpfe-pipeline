"""Opt-in local wheel installation test; never builds or downloads dependencies."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(not os.environ.get('EXP2CPFE_WHEEL_DIR'), reason='set EXP2CPFE_WHEEL_DIR after building the wheel')
def test_wheel_installation_outside_checkout(tmp_path, multimodal_sample_config):
    wheels=list(Path(os.environ['EXP2CPFE_WHEEL_DIR']).resolve().glob('*.whl'))
    assert len(wheels)==1, 'use a directory containing exactly one candidate wheel'
    target=tmp_path/'installed'
    installed=subprocess.run([sys.executable,'-m','pip','install','--no-deps','--no-compile',
                              '--disable-pip-version-check','--target',str(target),str(wheels[0])],
                             capture_output=True,text=True)
    assert installed.returncode==0,installed.stdout+installed.stderr
    code="""
import sys
from pathlib import Path
import subprocess
sys.path.insert(0,sys.argv[1])
import experiment_to_cpfe
assert Path(experiment_to_cpfe.__file__).is_relative_to(Path(sys.argv[1]))
from experiment_to_cpfe.cli import main
from experiment_to_cpfe.pipeline import _default_policy_path
assert _default_policy_path().is_relative_to(Path(sys.argv[1]))
assert main(['validate','--config',sys.argv[2],'--run-dir',sys.argv[3]])==0
from experiment_to_cpfe.solvers.abaqus.extraction import ExtractionRequest,build_abaqus_extraction_command
cmd=build_abaqus_extraction_command(ExtractionRequest(Path('none.odb'),Path('out'),('U',),'nodal'),('abaqus',))
script=Path(cmd[2])
assert script.is_relative_to(Path(sys.argv[1]))
r=subprocess.run([sys.executable,str(script),'--help'],capture_output=True,text=True)
assert r.returncode==0,r.stderr
print('Installed-wheel validate and extractor help passed')
"""
    result=subprocess.run([sys.executable,'-I','-c',code,str(target),str(multimodal_sample_config),str(tmp_path/'run')],
                          cwd=tmp_path,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
