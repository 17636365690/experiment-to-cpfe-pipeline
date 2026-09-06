"""Homogenized material regions have explicit applicability and plasticity contracts."""

from pathlib import Path
import pytest


def continuum():
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.schema.models import SampleMetadata
    sample = assemble_sample(load_pipeline_config(Path('examples/synthetic_minimal/sample.yaml')))
    meta = sample.metadata.model_dump()
    meta['orientation'] = {'representation': 'not_applicable', 'reason': 'homogenized isotropic continuum'}
    sample.metadata = SampleMetadata.model_validate(meta)
    sample.tables.pop('grains', None)
    sample.assets = tuple(a for a in sample.assets if a.descriptive_metadata.get('table_name', a.descriptive_metadata.get('table_key')) != 'grains')
    sample.solver_inputs.pop('microstructure_mapping')
    sample.solver_inputs.update(material_region_mapping={'ALL': [1]}, orientation_required=False)
    return sample


def test_continuum_region_and_orientation_applicability_roundtrip(tmp_path):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5, read_hdf5
    sample = continuum()
    assert check_solver_readiness(sample, 'abaqus_cpfe').ready
    path = tmp_path / 'continuum.h5'
    write_hdf5(sample, path)
    restored = read_hdf5(path)
    assert restored.metadata.orientation.reason == 'homogenized isotropic continuum'
    assert restored.solver_inputs['material_region_mapping'] == {'ALL': [1]}


@pytest.mark.parametrize('mutation', ['unknown_region', 'unmapped_element', 'orientation_required', 'crystal_umat'])
def test_region_mapping_remains_scoped_to_isotropic_continuum(mutation):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    sample = continuum()
    if mutation == 'unknown_region': sample.solver_inputs['material_region_mapping'] = {'OTHER': [1]}
    if mutation == 'unmapped_element': sample.solver_inputs['material_region_mapping'] = {'ALL': [999]}
    if mutation == 'orientation_required': sample.solver_inputs['orientation_required'] = True
    if mutation == 'crystal_umat': sample.solver_inputs['material_model'] = 'umat'
    assert not check_solver_readiness(sample, 'abaqus_cpfe').ready


def plastic():
    sample = continuum()
    sample.solver_inputs.update(material_model='isotropic_plastic', material_parameters={
        'E': 1000., 'nu': 0.3, 'plastic': [[10., 0.], [20., 0.1]]})
    sample.solver_inputs['inp_replacements']['MATERIALS'] = '*MATERIAL, NAME=MAT\n*ELASTIC\n1000.,0.3\n*PLASTIC\n10.,0.\n20.,0.1\n*SOLID SECTION, ELSET=ALL, MATERIAL=MAT'
    return sample


def test_tabulated_isotropic_plasticity_matches_declared_rows():
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    assert check_solver_readiness(plastic(), 'abaqus_cpfe').ready


@pytest.mark.parametrize('rows', [[[10, .01], [20, .1]], [[10, 0], [9, .1]], [[10, 0], [20, 0]], [[10, 0], [float('nan'), .1]]])
def test_invalid_or_inconsistent_plastic_table_is_rejected(rows):
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    sample = plastic()
    sample.solver_inputs['material_parameters']['plastic'] = rows
    assert not check_solver_readiness(sample, 'abaqus_cpfe').ready


def test_orientation_inapplicable_requires_explanation():
    from experiment_to_cpfe.config import SampleConfig
    from experiment_to_cpfe.config import load_pipeline_config
    meta = load_pipeline_config(Path('examples/synthetic_minimal/sample.yaml')).sample.model_dump()
    meta['orientation'] = {'representation': 'not_applicable', 'reason': ''}
    with pytest.raises(ValueError): SampleConfig.model_validate(meta)


def test_umat_and_builtin_plastic_tables_are_distinct_contracts():
    from experiment_to_cpfe.adapters.tabular import assemble_sample
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.schema.validation import check_solver_readiness
    sample=assemble_sample(load_pipeline_config(Path('examples/synthetic_minimal/sample.yaml')))
    sample.solver_inputs.update(material_model='umat',material_parameters={'constants':[1.,.3],'constant_units':['Pa','1'],'depvar':1})
    sample.solver_inputs['inp_replacements']['MATERIALS']='*MATERIAL, NAME=MAT\n*USER MATERIAL, CONSTANTS=2\n1.,.3\n*DEPVAR\n1\n*PLASTIC\n10,0\n20,.1\n*SOLID SECTION, ELSET=ALL, MATERIAL=MAT'
    assert not check_solver_readiness(sample,'abaqus_cpfe').ready
