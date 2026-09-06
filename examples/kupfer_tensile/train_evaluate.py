"""Package real FE curves, train a fixed MLP, and evaluate separate holdouts."""
from pathlib import Path
import json,csv
import numpy as np
from experiment_to_cpfe.learning.surrogate import run_training,predict_mlp
from experiment_to_cpfe.mechanics.tensile import regression_metrics
from experiment_to_cpfe.datasets.hdf5 import read_hdf5

import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--case-dir',type=Path,required=True)
args=parser.parse_args()
ROOT=args.case_dir.resolve()
manifest=json.loads((ROOT/'case-manifest.json').read_text())
features=[];targets=[];groups=[];splits=[];sources=[]
grid=np.linspace(0,.008,81)
for case in manifest['cases']:
    if case['split'] not in {'train','validation','test'}: continue
    folder=Path(case['run']); report=json.loads((folder/'reports/run_manifest.json').read_text())
    assert all(s['status']=='completed' for s in report['stages'])
    sample=read_hdf5(folder/'dataset/sample.h5')
    assert any(a.format=='odb' and a.source_kind.value=='simulated' for a in sample.assets)
    with np.load(folder/'dataset/axial-response.npz') as payload:
        strain,stress=payload['strain'],payload['stress']
        assert np.all(np.diff(strain)>0) and strain[-1]>=grid[-1]-1e-8
        y=np.interp(grid,strain,stress)
    p=case['parameters']
    x=np.column_stack([grid,np.full(len(grid),p['modulus']),np.full(len(grid),p['yield_stress']),np.full(len(grid),p['hardening_modulus'])])
    features.append(x);targets.append(y);groups.extend([case['name']]*len(grid));splits.extend([case['split']]*len(grid))
    sources.append({'case':case['name'],'split':case['split'],'hdf5':str(folder/'dataset/sample.h5'),
                    'odb':str(folder/'solver/analysis/gauge.odb'),'source_frames':len(strain),'training_rows':len(grid)})
dataset=ROOT/'surrogate-data.npz'
np.savez_compressed(dataset,features=np.vstack(features),targets=np.concatenate(targets),groups=np.array(groups),splits=np.array(splits))
(ROOT/'surrogate-data.json').write_text(json.dumps({'source_kind':'simulated','sources':sources,
    'target':'sum of top-face RF3 / initial area in MPa','strain':'mean top-face U3 / initial gauge length',
    'processing':'linear interpolation of each FE curve on a fixed 81-point strain grid','grouping':'all rows of one parameter case share a split'},indent=2),encoding='utf-8')
config={'dataset':dataset.name,'feature_names':['engineering_strain','E','yield_stress','plastic_modulus'],
    'feature_units':['1','MPa','MPa','MPa'],'target_name':'nominal_axial_stress','target_unit':'MPa',**manifest['neural_config']}
config_path=ROOT/'training-config.json';config_path.write_text(json.dumps(config,indent=2),encoding='utf-8')
result=run_training(config_path,ROOT/'model')
training=json.loads((ROOT/'model/training.json').read_text())
experimental=json.loads((ROOT/'experimental-curves.json').read_text())
cal=json.loads((ROOT/'calibration.json').read_text())
with np.load(ROOT/'jobs/base/dataset/axial-response.npz') as base:
    base_strain,base_stress=base['strain'],base['stress']
evaluation={'surrogate':training['metrics'],'mean_baseline':training['mean_baseline'],'experiment':{},'numerical_checks':{}}
rows=[]
for name,curve in experimental.items():
    x=np.array(curve['strain']);reference=np.array(curve['stress'])
    fe=np.interp(x,base_strain,base_stress)
    nn=predict_mlp(ROOT/'model/model.pt',np.column_stack([x,np.full(len(x),cal['modulus']),np.full(len(x),cal['yield_stress']),np.full(len(x),cal['hardening_modulus'])]))
    evaluation['experiment'][name]={'role':manifest['experiment_roles'][name],'fe':regression_metrics(reference,fe),'neural':regression_metrics(reference,nn)}
    rows.extend({'specimen':name,'role':manifest['experiment_roles'][name],'strain':float(e),'measured_stress_MPa':float(r),'fe_stress_MPa':float(f),'neural_stress_MPa':float(n)} for e,r,f,n in zip(x,reference,fe,nn))
for name in ['nu_low','nu_high','mesh8']:
    with np.load(ROOT/f'jobs/{name}/dataset/axial-response.npz') as values:
        evaluation['numerical_checks'][name]=regression_metrics(base_stress,np.interp(base_strain,values['strain'],values['stress']))
evaluation['experimental_repeatability']=regression_metrics(np.array(experimental['H_16']['stress']),np.array(experimental['H_18']['stress']))
evaluation['neural_test_target_met']=training['metrics']['test']['nrmse']<manifest['neural_test_nrmse_target']
(ROOT/'evaluation.json').write_text(json.dumps(evaluation,indent=2,allow_nan=False),encoding='utf-8')
with (ROOT/'experimental-comparison.csv').open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
print(json.dumps({'best_epoch':training['best_epoch'],'train_seconds':training['seconds'],'simulation_holdout':training['metrics']['test'],
                  'experimental_holdout':evaluation['experiment']['H_18'],'numerical_checks':evaluation['numerical_checks']},indent=2))
