"""Run a fixed small case list using the project stages and resume completed stages."""
from pathlib import Path
import json,sys,datetime
from experiment_to_cpfe import pipeline
from experiment_to_cpfe.datasets.hdf5 import read_hdf5
from experiment_to_cpfe.mechanics.tensile import reduce_axial_records,bilinear_stress,regression_metrics
import numpy as np

import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--case-dir',type=Path,required=True)
parser.add_argument('--cases',nargs='*')
args=parser.parse_args()
ROOT=args.case_dir.resolve()
manifest=json.loads((ROOT/'case-manifest.json').read_text())
selection=args.cases
cases=[case for case in manifest['cases'] if not selection or case['name'] in selection]
def status(case,stage,result):
    record={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'case':case,'stage':stage,'status':result['status']}
    print(json.dumps(record),flush=True)
    with (ROOT/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(record)+'\n')
    if result['status']!='completed': raise RuntimeError(json.dumps(result,indent=2))
for case in cases:
    config=Path(case['config']);run=Path(case['run'])
    stages=[('validate',pipeline.run_validate,()),('build-inp',pipeline.run_build_inp,()),
        ('abaqus-datacheck',pipeline.run_abaqus_stage,('datacheck',)),('abaqus-analysis',pipeline.run_abaqus_stage,('analysis',)),
        ('extract-odb',pipeline.run_extract_odb,()),('export-hdf5',pipeline.run_export,('hdf5',)),('export-npz',pipeline.run_export,('npz',))]
    prior=run/'reports/run_manifest.json'
    completed={s['stage'] for s in json.loads(prior.read_text())['stages'] if s['status']=='completed'} if prior.exists() else set()
    for stage,fn,args in stages:
        if stage not in completed: status(case['name'],stage,fn(config,run,*args))
    sample=read_hdf5(run/'dataset/sample.h5')
    records=sample.tables['simulation_records']
    instances={r['instance'] for r in records if r['field']=='U'}
    assert len(instances)==1,instances
    gauge=sample.solver_inputs['gauge']
    curve=reduce_axial_records(records,step='TENSION',instance=next(iter(instances)),top_nodes=gauge['top_nodes'],
        axis=3,area=gauge['area'],length=gauge['length'],force_unit='N',length_unit='mm')
    predicted=bilinear_stress(curve['strain'],**case['parameters'])
    result=regression_metrics(predicted,curve['stress'])
    np.savez_compressed(run/'dataset/axial-response.npz',**curve,analytical_stress=predicted)
    (run/'reports/axial-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'case':case['name'],'frames':len(curve['frame']),'analytic_nrmse':result['nrmse'],'peak_stress_MPa':float(curve['stress'].max())}),flush=True)
    assert result['nrmse'] < manifest['simulation_analytic_nrmse_tolerance'],result
