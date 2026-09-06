"""Standalone scientific comparisons from saved experiment, ODB and model outputs."""
from pathlib import Path
import json,csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import argparse
parser=argparse.ArgumentParser()
parser.add_argument('--case-dir',type=Path,required=True)
args=parser.parse_args()
ROOT=args.case_dir.resolve()
OUT=ROOT/'figures';OUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,
                     'axes.labelcolor':'#252525','text.color':'#252525','axes.edgecolor':'#777777','savefig.facecolor':'white'})
blue='#28629E';orange='#C67A25';ink='#303030'
with (ROOT/'experimental-comparison.csv').open() as f: rows=list(csv.DictReader(f))
evaluation=json.loads((ROOT/'evaluation.json').read_text())
fig,axes=plt.subplots(1,3,figsize=(13.2,3.8),layout='constrained',sharey=True)
for ax,name in zip(axes,['H_08','H_16','H_18']):
    selected=[r for r in rows if r['specimen']==name]
    values={k:np.array([float(r[k]) for r in selected]) for k in ['strain','measured_stress_MPa','fe_stress_MPa','neural_stress_MPa']}
    ax.plot(values['strain']*100,values['measured_stress_MPa'],color=ink,lw=1.6,label='Experiment')
    ax.plot(values['strain']*100,values['fe_stress_MPa'],color=blue,lw=1.6,ls='--',label='Abaqus gauge')
    ax.plot(values['strain']*100,values['neural_stress_MPa'],color=orange,lw=1.4,ls=':',label='MLP surrogate')
    role=evaluation['experiment'][name]['role'].replace('_',' ')
    ax.set_title(f'{name} | {role}',loc='left',fontsize=11)
    ax.set_xlabel('Engineering strain from preload origin (%)')
    ax.set_xlim(0,.8);ax.set_ylim(-3,205);ax.grid(axis='y',alpha=.15)
    ax.text(.04,.90,f"FE RMSE: {evaluation['experiment'][name]['fe']['rmse']:.2f} MPa",transform=ax.transAxes,fontsize=9)
axes[0].set_ylabel('Nominal stress increment (MPa)');axes[2].legend(loc='lower right',frameon=False,fontsize=8)
fig.suptitle('Public CuSn8Ni2 tensile workflow | 22 C, 0.025%/s, equivalent uniform gauge',fontsize=12)
fig.savefig(OUT/'experimental-workflow.png',dpi=180)
fig.savefig(OUT/'experimental-workflow.svg');plt.close(fig)

training=json.loads((ROOT/'model/training.json').read_text());history=training['history']
data=np.load(ROOT/'model/predictions.npz');mask=data['splits']=='test'
fig,axes=plt.subplots(1,2,figsize=(9.5,3.8),layout='constrained')
axes[0].plot([r['epoch'] for r in history],[r['train_mse_standardized'] for r in history],color=blue,label='Train')
axes[0].plot([r['epoch'] for r in history],[r['validation_mse_standardized'] for r in history],color=orange,ls='--',label='Validation')
axes[0].axvline(training['best_epoch'],color=ink,lw=.8,ls=':')
axes[0].set_yscale('log');axes[0].set_xlabel('Epoch');axes[0].set_ylabel('Standardized MSE');axes[0].legend(frameon=False)
axes[0].set_title('Checkpoint selected on validation cases',loc='left',fontsize=10)
reference=data['target'][mask];prediction=data['prediction'][mask]
axes[1].scatter(reference,prediction,s=13,color=blue,alpha=.65,edgecolors='none')
axes[1].plot([0,205],[0,205],color=ink,ls='--',lw=1)
axes[1].set(xlim=(-3,205),ylim=(-3,205),xlabel='Abaqus nominal stress (MPa)',ylabel='MLP prediction (MPa)')
axes[1].set_title(f"Held-out FE cases | RMSE {training['metrics']['test']['rmse']:.2f} MPa",loc='left',fontsize=10)
fig.suptitle('Neural surrogate | 5 train / 2 validation / 2 test parameter cases',fontsize=12)
fig.savefig(OUT/'neural-validation.png',dpi=180);fig.savefig(OUT/'neural-validation.svg');plt.close(fig)
print('saved experiment and neural comparison figures')
