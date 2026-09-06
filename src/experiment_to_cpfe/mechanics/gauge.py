"""Equivalent homogeneous gauge generation with explicit material-domain metadata."""

from pathlib import Path
import math


def build_gauge_config(*, case_id, area, length, modulus, poisson, yield_stress, hardening_modulus,
                       max_strain, strain_rate, divisions, units, abaqus_command, template_path,
                       work_dir, source_description):
    numbers = (area, length, modulus, yield_stress, hardening_modulus, max_strain, strain_rate)
    if not all(math.isfinite(x) and x > 0 for x in numbers) or not -1 < poisson < .5:
        raise ValueError('finite positive geometry/material/load parameters required')
    if len(divisions) != 3 or any(type(n) is not int or n < 1 for n in divisions):
        raise ValueError('three positive integer mesh divisions required')
    if math.prod(divisions) > 1000:
        raise ValueError('gauge generator supports at most 1000 elements per case')
    if (units.get('length'), units.get('stress'), units.get('force')) not in {('mm', 'MPa', 'N'), ('m', 'Pa', 'N')} or units.get('time') != 's':
        raise ValueError('gauge requires consistent mm/MPa/N/s or m/Pa/N/s units')
    if not source_description.strip():
        raise ValueError('gauge modeling/source description required')
    folder = Path(work_dir)
    folder.mkdir(parents=True, exist_ok=True)
    nx, ny, nz = divisions
    width = math.sqrt(area)
    def node(i, j, k): return 1 + i + (nx + 1) * (j + (ny + 1) * k)
    rows = [f'{node(i,j,k)}, {width*i/nx:.16g}, {width*j/ny:.16g}, {length*k/nz:.16g}'
            for k in range(nz + 1) for j in range(ny + 1) for i in range(nx + 1)]
    elements = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                labels = [node(i,j,k),node(i+1,j,k),node(i+1,j+1,k),node(i,j+1,k),
                          node(i,j,k+1),node(i+1,j,k+1),node(i+1,j+1,k+1),node(i,j+1,k+1)]
                elements.append(f'{len(elements)+1}, ' + ', '.join(map(str,labels)))
    top = [node(i,j,nz) for j in range(ny+1) for i in range(nx+1)]
    bottom = [node(i,j,0) for j in range(ny+1) for i in range(nx+1)]
    node_text = '*NODE\n' + '\n'.join(rows)
    element_text = '*ELEMENT, TYPE=C3D8, ELSET=ALL\n' + '\n'.join(elements)
    def nset(name, labels):
        return f'*NSET, NSET={name}\n' + '\n'.join(', '.join(map(str, labels[i:i+16])) for i in range(0,len(labels),16))
    sets = nset('BOTTOM', bottom) + '\n' + nset('TOP', top)
    geometry = folder / 'gauge-mesh.inp'
    with geometry.open('x', encoding='utf-8', newline='\n') as out:
        out.write(node_text + '\n' + element_text + '\n' + sets + '\n')
    period = max_strain / strain_rate
    increment = period / 40
    plastic = [[float(yield_stress), 0.], [float(yield_stress + hardening_modulus * max_strain * 2), float(max_strain * 2)]]
    materials = f'*MATERIAL, NAME=CONTINUUM\n*ELASTIC\n{modulus!r}, {poisson!r}\n*PLASTIC\n' + '\n'.join(f'{s!r}, {p!r}' for s,p in plastic) + '\n*SOLID SECTION, ELSET=ALL, MATERIAL=CONTINUUM'
    boundary = [{'target':'BOTTOM','first_dof':3,'last_dof':3,'value':0.},
                {'target':str(node(0,0,0)),'first_dof':1,'last_dof':2,'value':0.},
                {'target':str(node(nx,0,0)),'first_dof':2,'last_dof':2,'value':0.},
                {'target':'TOP','first_dof':3,'last_dof':3,'value':float(max_strain*length)}]
    def boundary_line(row): return f"{row['target']}, {row['first_dof']}, {row['last_dof']}, {row['value']!r}"
    restraints = sets + '\n*BOUNDARY\n' + '\n'.join(boundary_line(r) for r in boundary[:3])
    step = f'*STEP, NAME=TENSION, NLGEOM=NO, INC=1000\n*STATIC\n{increment!r}, {period!r}, {period*1e-8!r}, {increment!r}\n*BOUNDARY\n' + boundary_line(boundary[-1])
    step += '\n*OUTPUT, FIELD, FREQUENCY=1\n*ELEMENT OUTPUT\nS, E\n*NODE OUTPUT\nU, RF\n*END STEP'
    return {'sample': {'sample_id':case_id,'experiment_id':case_id,'microstructure_id':case_id+'-homogenized',
        'load_path_id':case_id+'-tension','schema_version':'0.1',
        'coordinate':{'name':'gauge','axes':['x','y','z'],'units':units['length']},
        'unit_system':units,'tensor_order':['11','22','33','12','13','23'],
        'orientation':{'representation':'not_applicable','reason':'homogenized isotropic gauge-response model'}},
        'sources':[], 'assets':[{'asset_id':case_id+'-mesh','path':str(geometry.resolve()),'parent_asset_id':None,
            'source_kind':'input','layer':'solver_input','modality':'mesh','format':'inp','units':{'length':units['length']},
            'coordinate_frame':'gauge','axis_order':['x','y','z'],'native_layout':'equivalent homogeneous square gauge',
            'license':'locally generated','lossy_transformations':[],'adapter_config':{}}],
        'solver_inputs':{'material_model':'isotropic_plastic','material_parameters':{'E':float(modulus),'nu':float(poisson),'plastic':plastic},
            'material_region_mapping':{'ALL':list(range(1,len(elements)+1))},'orientation_required':False,
            'boundary_conditions':boundary,'load_steps':[{'name':'TENSION','procedure':'static','initial_increment':increment,'time_period':period}],
            'output_variables':['S','E','U','RF'],'gauge':{'area':area,'length':length,'top_nodes':top,'bottom_nodes':bottom,
                'axis':3,'divisions':list(divisions),'source_description':source_description,'model':'small-strain homogeneous gauge reduction'},
            'inp_replacements':{'HEADING':case_id,'NODES':node_text,'ELEMENTS':element_text,'MATERIALS':materials,'BOUNDARY_CONDITIONS':restraints,'OUTPUT_REQUESTS':step}},
        'abaqus':{'command':list(abaqus_command),'job_name':'gauge','template_path':str(Path(template_path).resolve()),
            'ascii_temp_root':str((folder.parent/'scratch').resolve()),'cpus':1,'timeout_seconds':300,
            'required_fields':['S','E','U','RF'],'extraction_position':'native','extraction_max_records':200000,
            'field_units':{'S':units['stress'],'E':'1','U':units['length'],'RF':units['force']}},
        'export':{'formats':['hdf5','npz']}}
