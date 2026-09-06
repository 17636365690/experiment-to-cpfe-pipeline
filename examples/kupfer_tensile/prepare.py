"""Prepare the fixed, small public tensile case from the existing local archive."""
from pathlib import Path
import csv, json, zipfile
import numpy as np
from experiment_to_cpfe.adapters.tabular import load_tabular_source
from experiment_to_cpfe.config import TabularSourceConfig
from experiment_to_cpfe.mechanics.tensile import fit_bilinear
from experiment_to_cpfe.mechanics.gauge import build_gauge_config

import argparse
parser=argparse.ArgumentParser(description='Prepare the public CuSn8Ni2 tensile workflow')
parser.add_argument('--source-dir',type=Path,required=True,help='directory containing the published Files.zip')
parser.add_argument('--output-dir',type=Path,required=True)
parser.add_argument('--runtime-config',type=Path,required=True,help='JSON with abaqus_command tokens')
args=parser.parse_args()
ROOT=args.output_dir.resolve()
ROOT.mkdir(parents=True,exist_ok=False)
REPO=Path(__file__).resolve().parents[2]
SOURCE=args.source_dir.resolve()
assert not (ROOT/'case-manifest.json').exists()
(ROOT/'sources').mkdir(exist_ok=True)
archive=zipfile.ZipFile(SOURCE/'Files.zip')
curves={};metadata={};receipts=[]
for specimen in ['H_08','H_16','H_18']:
    member=f'Tensile test/Primary data/Tensile_{specimen}.lis'
    raw=ROOT/'sources'/f'{specimen}.lis';raw.write_bytes(archive.read(member))
    lines=raw.read_text(encoding='cp1252').splitlines()
    def header(prefix): return next(line for line in lines if line.startswith(prefix)).split('\t')[-1].strip()
    numeric=lambda prefix:float(header(prefix).replace(',','.'))
    metadata[specimen]={'material':header('Werkstoff'),'area_mm2':numeric('Probenquerschnitt'),
        'gauge_length_mm':numeric('Anfangsmesslänge'),'elastic_slope_MPa':numeric('Steigung des elastischen Teils')*1000,
        'temperature_C':numeric('Prüftemperatur'),'source_member':member}
    cfg=TabularSourceConfig(path=raw,table_name='measured_observations',source_kind='measured',modality='time_series',
        format='txt',delimiter='\t',encoding='cp1252',column_map={'time':'0','travel':'1','force':'2','strain':'3','stress':'4'},
        units={'time':'s','travel':'mm','force':'N','strain':'1','stress':'MPa'},coordinate_frame=None,axis_order=('row',),
        native_layout='BAM LIS Daten block',license='CC-BY-4.0',
        block={'start_marker':'[Daten]','data_start_row':3,'decimal':',','numeric_fields':['time','travel','force','strain','stress'],
               'header_checks':[{'row':1,'column':3,'value':'Dehnung'},{'row':2,'column':3,'value':'%'}]},
        conversions={'strain':{'source_unit':'%','target_unit':'1','factor':.01,'reason':'percent to dimensionless engineering strain'},
                     'force':{'source_unit':'kN','target_unit':'N','factor':1000,'reason':'SI prefix conversion'}})
    rows=load_tabular_source(cfg)
    strain=np.array([r['strain'] for r in rows]);stress=np.array([r['stress'] for r in rows])
    force=np.array([r['force'] for r in rows])
    assert np.max(np.abs(stress-force/metadata[specimen]['area_mm2']))<1e-8
    strain0,stress0=strain[0],stress[0]
    strain=strain-strain0;stress=stress-stress0
    chosen=[0]
    for i in range(1,len(strain)):
        if strain[i]>strain[chosen[-1]]:
            chosen.append(i)
            if strain[i]>=.008: break
    assert strain[chosen[-1]]>=.008
    grid=np.linspace(0,.008,161)
    values=np.interp(grid,strain[chosen],stress[chosen])
    curves[specimen]={'strain':grid.tolist(),'stress':values.tolist()}
    with (ROOT/'sources'/f'{specimen}-curve.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.writer(f);writer.writerow(['strain','stress']);writer.writerows(zip(grid,values))
    receipts.append({'specimen':specimen,'rows':len(rows),'selected_source_rows':[rows[i]['source_row'] for i in chosen],
        'strain_origin':float(strain0),'stress_origin_MPa':float(stress0),'loading_points':len(chosen),
        'processing':['explicit percent and force prefix conversion','first source point used as preload origin',
                      'strictly increasing initial loading subsequence to 0.8 percent','linear interpolation on fixed 161-point grid'],
        'source_config':cfg.model_dump(mode='json')})
cal=fit_bilinear(np.array(curves['H_08']['strain']),np.array(curves['H_08']['stress']),
    modulus=metadata['H_08']['elastic_slope_MPa'],yield_bounds=(20,300),hardening_bounds=(10,100000))
(ROOT/'calibration.json').write_text(json.dumps(cal,indent=2),encoding='utf-8')
(ROOT/'experimental-curves.json').write_text(json.dumps(curves,indent=2),encoding='utf-8')
(ROOT/'source-records.json').write_text(json.dumps({'metadata':metadata,'processing':receipts,
    'dataset_doi':'10.5281/zenodo.10820299','license':'CC-BY-4.0','method':'Content.pdf pages 2-3, Figure 1, Table 5'},indent=2),encoding='utf-8')
command=json.loads(args.runtime_config.read_text(encoding='utf-8'))['abaqus_command']
cases=[('base','train',(1,1,1),.30,(1,1,1)),('low','train',(.9,.9,.9),.30,(1,1,1)),
       ('high','train',(1.1,1.1,.9),.30,(1,1,1)),('soft_yield_high','train',(.9,1.1,1.1),.30,(1,1,1)),
       ('stiff_yield_low','train',(1.1,.9,1.1),.30,(1,1,1)),('val_a','validation',(.95,1,1.05),.30,(1,1,1)),
       ('val_b','validation',(1.05,1,.95),.30,(1,1,1)),('test_a','test',(1,.95,1.05),.30,(1,1,1)),
       ('test_b','test',(1,1.05,.95),.30,(1,1,1)),('nu_low','sensitivity',(1,1,1),.25,(1,1,1)),
       ('nu_high','sensitivity',(1,1,1),.35,(1,1,1)),('mesh8','mesh_check',(1,1,1),.30,(2,2,2))]
manifest={'case_scope':'small-strain homogenized gauge response from public CuSn8Ni2 tensile data',
    'experiment_roles':{'H_08':'calibration','H_16':'model_check','H_18':'final_holdout'},
    'assumptions':['equivalent square gauge preserves measured initial area and gauge length','isotropic bilinear small-strain response to 0.8 percent strain',
                   'Poisson ratio 0.30 with 0.25/0.35 sensitivity','homogeneous material region and source tensile axis mapped to model z'],
    'strain_rate_s_inv':.00025,'max_strain':.008,'simulation_analytic_nrmse_tolerance':1e-4,
    'neural_test_nrmse_target':.05,'experimental_evaluation':'report errors and repeatability; threshold requires experimental uncertainty budget',
    'neural_config':{'epochs':2500,'patience':500,'hidden':[32,32],'seed':42,'learning_rate':.003},'cases':[]}
for name,split,factors,poisson,divisions in cases:
    params={'modulus':cal['modulus']*factors[0],'yield_stress':cal['yield_stress']*factors[1],
            'hardening_modulus':cal['hardening_modulus']*factors[2]}
    folder=ROOT/'configs'/name
    config=build_gauge_config(case_id='kupfer-'+name,area=metadata['H_08']['area_mm2'],length=25.,
        **params,poisson=poisson,max_strain=.008,strain_rate=.00025,divisions=divisions,
        units={'length':'mm','stress':'MPa','force':'N','time':'s'},abaqus_command=command,
        template_path=REPO/'configs/templates/cpfe_template.inp',work_dir=folder,
        source_description='KupferDigital H_08 calibration; explicit homogeneous square-gauge reduction')
    config['solver_inputs']['calibration_result']={'source':'KupferDigital H_08','file':str(ROOT/'calibration.json'),
        'parameter_scale_factors':list(factors),'definition':'nominal stress vs engineering strain in small-strain gauge model'}
    config['solver_inputs']['dataset_split']=split
    for key,path,kind,fmt,layer in [('raw',ROOT/'sources/H_08.lis','measured','lis','raw'),
        ('curve',ROOT/'sources/H_08-curve.csv','inferred','csv','curated'),('calibration',ROOT/'calibration.json','inferred','json','curated')]:
        config['assets'].append({'asset_id':key,'path':str(path),'parent_asset_id':'raw' if key!='raw' else None,
            'source_kind':kind,'layer':layer,'modality':'table','format':fmt,'units':{},'coordinate_frame':None,
            'axis_order':[],'native_layout':'public tensile calibration source','license':'CC-BY-4.0',
            'lossy_transformations':[] if key=='raw' else ['fixed loading-window selection and declared model calibration'],'adapter_config':{}})
    configpath=folder/'sample.json';configpath.write_text(json.dumps(config,indent=2),encoding='utf-8')
    manifest['cases'].append({'name':name,'split':split,'parameters':params,'poisson':poisson,'divisions':list(divisions),
        'config':str(configpath),'run':str(ROOT/'jobs'/name)})
(ROOT/'case-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'calibration':cal,'cases':len(cases),'specimens':metadata},indent=2))
