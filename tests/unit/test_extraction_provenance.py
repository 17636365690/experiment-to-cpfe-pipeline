import hashlib
import json
from pathlib import Path
import shutil

import pytest


@pytest.fixture
def extraction_bundle(tmp_path):
    target=tmp_path/'bundle'
    shutil.copytree('tests/fixtures/odb_extract_fixture',target)
    odb=tmp_path/'fixture.odb'
    odb.write_bytes(b'explicit synthetic test bytes; not a real ODB')
    metadata=json.loads((target/'metadata.json').read_text())
    metadata['odb_path']=str(odb)
    metadata['odb_sha256']=hashlib.sha256(odb.read_bytes()).hexdigest()
    metadata['field_units']={'S':'MPa','LE':'1'}
    metadata['sample_metadata']['unit_system']['stress']='MPa'
    (target/'metadata.json').write_text(json.dumps(metadata))
    return target


def test_units_are_attached_to_each_field_record(extraction_bundle):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    sample=load_extraction_bundle(extraction_bundle)
    assert [(r['field'],r['unit']) for r in sample.tables['simulation_records']]==[('S','MPa'),('LE','1')]
    child=next(a for a in sample.assets if a.format=='odb-extraction-bundle')
    assert child.units=={'S':'MPa','LE':'1'}


@pytest.mark.parametrize('declared',[{}, {'S':'MPa'}, {'S':'unknown','LE':'1'}, {'S':'Pa','SDV':'1'}])
def test_missing_field_unit_is_not_guessed_from_system_or_group(extraction_bundle,declared):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    meta=json.loads((extraction_bundle/'metadata.json').read_text())
    meta['field_units']=declared
    (extraction_bundle/'metadata.json').write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='field unit'):
        load_extraction_bundle(extraction_bundle)


def test_child_hash_describes_extracted_files_not_parent_odb(extraction_bundle):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    sample=load_extraction_bundle(extraction_bundle)
    child=next(a for a in sample.assets if a.format=='odb-extraction-bundle')
    assert child.parent_asset_id is not None
    parent=next(a for a in sample.assets if a.asset_id==child.parent_asset_id)
    assert parent.format=='odb'
    assert child.sha256!=parent.sha256
    assert child.source_kind.value==parent.source_kind.value=='simulated'
    assert child.license is None
    assert child.conversion.source_sha256==parent.sha256
    assert child.conversion.original_format=='odb'
    assert child.conversion.target_format=='odb-extraction-bundle'
    assert child.conversion.source_hash_verified is True
    assert child.conversion.target_file_hashes=={
        name:hashlib.sha256((extraction_bundle/name).read_bytes()).hexdigest()
        for name in ('metadata.json','frames.csv')
    }
    assert child.lossy_transformations


def test_modified_available_parent_is_rejected(extraction_bundle):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    meta=json.loads((extraction_bundle/'metadata.json').read_text())
    Path(meta['odb_path']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='ODB hash'):
        load_extraction_bundle(extraction_bundle)


def test_changed_selected_values_change_child_identity_only(extraction_bundle):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    first=load_extraction_bundle(extraction_bundle)
    path=extraction_bundle/'frames.csv'
    path.write_text(path.read_text().replace('0.001','0.002'))
    second=load_extraction_bundle(extraction_bundle)
    a=next(x for x in first.assets if x.parent_asset_id)
    b=next(x for x in second.assets if x.parent_asset_id)
    assert a.asset_id!=b.asset_id
    assert a.parent_asset_id==b.parent_asset_id


def test_hdf5_roundtrip_retains_field_units_and_conversion(extraction_bundle,tmp_path):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle
    from experiment_to_cpfe.datasets.hdf5 import read_hdf5,write_hdf5

    sample=load_extraction_bundle(extraction_bundle)
    path=tmp_path/'sample.h5'
    digest=write_hdf5(sample,path)
    restored=read_hdf5(path)
    assert digest==hashlib.sha256(path.read_bytes()).hexdigest()
    assert restored.tables['simulation_records'][0]['unit']=='MPa'
    assert restored.tables==sample.tables
    assert {a.asset_id:a for a in restored.assets}=={a.asset_id:a for a in sample.assets}
    assert any(a.conversion is not None for a in restored.assets)


def test_conversion_parent_hash_cannot_disagree(extraction_bundle):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle
    from experiment_to_cpfe.assets.models import AssetManifest

    sample=load_extraction_bundle(extraction_bundle)
    child=next(a for a in sample.assets if a.parent_asset_id)
    invalid=child.model_copy(update={'conversion':child.conversion.model_copy(update={'source_sha256':'0'*64})})
    with pytest.raises(ValueError,match='source hash'):
        AssetManifest(assets=tuple(invalid if a.asset_id==child.asset_id else a for a in sample.assets))


def test_unavailable_parent_is_a_reference_not_a_verified_file(extraction_bundle):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    meta=json.loads((extraction_bundle/'metadata.json').read_text())
    Path(meta['odb_path']).unlink()
    sample=load_extraction_bundle(extraction_bundle)
    child=next(a for a in sample.assets if a.parent_asset_id)
    assert child.conversion.source_hash_verified is False


def test_unit_column_cannot_disagree_with_declared_unit(extraction_bundle):
    import csv
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    path=extraction_bundle/'frames.csv'
    with path.open() as stream:
        rows=list(csv.DictReader(stream))
    for row in rows:
        row['unit']='incorrect'
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError,match='field unit'):
        load_extraction_bundle(extraction_bundle)


def test_group_unit_does_not_cover_individual_state_variables(extraction_bundle):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle

    path=extraction_bundle/'frames.csv'
    path.write_text(path.read_text().replace(',S,',',SDV_phi1,'))
    meta=json.loads((extraction_bundle/'metadata.json').read_text())
    meta['field_units']={'SDV':'1','LE':'1'}
    (extraction_bundle/'metadata.json').write_text(json.dumps(meta))
    with pytest.raises(ValueError,match='SDV_phi1'):
        load_extraction_bundle(extraction_bundle)


def test_parent_graph_cannot_contain_cycles(extraction_bundle):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle
    from experiment_to_cpfe.assets.models import AssetManifest

    sample=load_extraction_bundle(extraction_bundle)
    child=next(a for a in sample.assets if a.parent_asset_id)
    parent=next(a for a in sample.assets if a.asset_id==child.parent_asset_id)
    parent=parent.model_copy(update={'parent_asset_id':child.asset_id})
    with pytest.raises(ValueError,match='cycle'):
        AssetManifest(assets=(child,parent))
