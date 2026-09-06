import io
import json
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def canonical(tmp_path,make_sample):
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5
    sample=make_sample()
    sample.tables['simulation_records']=[{'step':'001','frame':2,'field':'S','component':'S11','value':12.5,'unit':'MPa','instance':'grain-A'}]
    sample.solver_inputs['note']='explicit synthetic fixture'
    path=tmp_path/'canonical.h5'
    digest=write_hdf5(sample,path,{'fixture':'source provenance'})
    return path,digest,sample


def test_npz_preserves_tables_units_metadata_and_provenance(canonical,tmp_path):
    from experiment_to_cpfe.datasets.package import write_npz
    source,digest,sample=canonical
    output=tmp_path/'sample.npz'
    write_npz(source,output,digest)
    with np.load(output,allow_pickle=False) as data:
        assert json.loads(data['__tables_json__'].item())==sample.tables
        assert json.loads(data['__sample_metadata_json__'].item())==sample.metadata.model_dump(mode='json')
        assert json.loads(data['__solver_inputs_json__'].item())==sample.solver_inputs
        assert json.loads(data['__source_manifest_json__'].item())=={'fixture':'source provenance'}
        assert json.loads(data['__asset_manifest_json__'].item())[0]['source_kind']=='measured'
        assert data['__source_hdf5_sha256__'].item()==digest
        derivation=json.loads(data['__derivation_json__'].item())
        assert derivation['parent_asset_id']=='hdf5-'+digest
        assert derivation['original_format']=='hdf5'
        assert derivation['target_format']=='npz'
        assert np.array_equal(data['demo'],sample.arrays['demo'])


@pytest.mark.parametrize('digest',['wrong','0'*64])
def test_unverified_hdf5_cannot_be_exported(canonical,tmp_path,digest):
    from experiment_to_cpfe.datasets.package import write_npz
    with pytest.raises(ValueError,match='HDF5 source hash'):
        write_npz(canonical[0],tmp_path/'out.npz',digest)
    assert not (tmp_path/'out.npz').exists()


def test_npz_does_not_append_an_unrequested_extension(canonical,tmp_path):
    from experiment_to_cpfe.datasets.package import write_npz
    output=tmp_path/'chosen.name'
    write_npz(canonical[0],output,canonical[1])
    assert output.is_file()
    assert not (tmp_path/'chosen.name.npz').exists()


def test_npz_refuses_existing_output(canonical,tmp_path):
    from experiment_to_cpfe.datasets.package import write_npz
    output=tmp_path/'existing.npz'
    output.write_bytes(b'original')
    with pytest.raises(FileExistsError):
        write_npz(canonical[0],output,canonical[1])
    assert output.read_bytes()==b'original'


def test_reserved_array_name_is_not_silently_replaced(tmp_path,make_sample):
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5
    from experiment_to_cpfe.datasets.package import write_npz
    sample=make_sample()
    sample.arrays['__sample_id__']=np.array([55])
    source=tmp_path/'reserved.h5'
    digest=write_hdf5(sample,source)
    with pytest.raises(ValueError,match='reserved'):
        write_npz(source,tmp_path/'out.npz',digest)


def graph_source(tmp_path,make_sample,**updates):
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5
    sample=make_sample()
    sample.arrays.update({'graph_node_features':np.array([[1.],[2.]]),
                          'graph_edge_index':np.array([[0,1],[1,0]],dtype=np.int64),
                          'graph_node_ids':np.array([101,909],dtype=np.int64),
                          'graph_edge_features':np.array([[.5],[.5]])})
    sample.arrays.update(updates)
    sample.solver_inputs['graph_contract']={'directed':False,'node_feature_names':['size'],
        'node_feature_units':['um'],'edge_feature_names':['misorientation'],'edge_feature_units':['degree']}
    source=tmp_path/'graph.h5'
    digest=write_hdf5(sample,source)
    return source,digest,sample


@pytest.mark.parametrize('updates',[
    {'graph_edge_index':np.array([[0.,1.],[1.,0.]])},
    {'graph_edge_index':np.array([[0,2],[1,0]])},
    {'graph_node_ids':np.array([101,101])},
    {'graph_node_features':np.array([[np.nan],[2.]])},
    {'graph_edge_features':np.ones((3,1))},
])
def test_invalid_graph_is_rejected_before_writing(tmp_path,make_sample,updates):
    from experiment_to_cpfe.datasets.package import write_pyg
    source,digest,_=graph_source(tmp_path,make_sample,**updates)
    with pytest.raises(ValueError,match='graph'):
        write_pyg(source,tmp_path/'bad.pt',digest)
    assert not (tmp_path/'bad.pt').exists()


def test_pyg_is_real_data_with_portable_full_payload(tmp_path,make_sample):
    torch=pytest.importorskip('torch')
    Data=pytest.importorskip('torch_geometric.data').Data
    from experiment_to_cpfe.datasets.package import write_pyg
    source,digest,sample=graph_source(tmp_path,make_sample)
    output=tmp_path/'nested/graph.pt'
    write_pyg(source,output,digest)
    # Only load this test's own freshly generated object, never an untrusted .pt.
    data=torch.load(output,weights_only=False,map_location='cpu')
    assert isinstance(data,Data)
    assert data.validate(raise_on_error=True)
    assert data.num_nodes==2
    assert data.x.tolist()==[[1.],[2.]]
    assert data.edge_index.dtype==torch.long
    assert data.edge_attr.tolist()==[[.5],[.5]]
    assert data.source_hdf5_sha256==digest
    assert json.loads(data.derivation_json)['target_format']=='pyg'
    assert data.y is None
    with np.load(io.BytesIO(data.package_npz),allow_pickle=False) as payload:
        assert payload['graph_node_ids'].tolist()==[101,909]
        assert json.loads(payload['__tables_json__'].item())==sample.tables
        assert json.loads(payload['__solver_inputs_json__'].item())['graph_contract']['node_feature_units']==['um']


def test_missing_pyg_dependency_is_explicit_and_creates_no_file(tmp_path,make_sample,monkeypatch):
    import builtins
    from experiment_to_cpfe.datasets.package import write_pyg
    source,digest,_=graph_source(tmp_path,make_sample)
    original=builtins.__import__
    def blocked_import(name,*args,**kwargs):
        if name=='torch_geometric.data':
            raise ImportError('deliberately unavailable optional dependency')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',blocked_import)
    with pytest.raises(RuntimeError,match='optional'):
        write_pyg(source,tmp_path/'no-dependency.pt',digest)
    assert not (tmp_path/'no-dependency.pt').exists()


def test_undirected_edges_are_not_invented(tmp_path,make_sample):
    from experiment_to_cpfe.datasets.package import write_pyg
    source,digest,_=graph_source(tmp_path,make_sample,graph_edge_index=np.array([[0],[1]]),graph_edge_features=np.array([[.5]]))
    with pytest.raises(ValueError,match='reverse edges'):
        write_pyg(source,tmp_path/'one-way.pt',digest)


def test_missing_feature_unit_is_not_defaulted(tmp_path,make_sample):
    from experiment_to_cpfe.datasets.hdf5 import write_hdf5
    from experiment_to_cpfe.datasets.package import write_pyg
    _,_,sample=graph_source(tmp_path,make_sample)
    sample.solver_inputs['graph_contract']['node_feature_units']=['unknown']
    source=tmp_path/'unknown-unit.h5'
    digest=write_hdf5(sample,source)
    with pytest.raises(ValueError,match='units'):
        write_pyg(source,tmp_path/'bad-unit.pt',digest)


def test_blank_graph_node_id_is_rejected(tmp_path,make_sample):
    from experiment_to_cpfe.datasets.package import write_pyg
    source,digest,_=graph_source(tmp_path,make_sample,graph_node_ids=np.array([b'',b'node'],dtype='S4'))
    with pytest.raises(ValueError,match='node IDs'):
        write_pyg(source,tmp_path/'blank-id.pt',digest)


def test_npz_preserves_byte_ids_and_dtype_metadata(tmp_path,make_sample):
    from experiment_to_cpfe.datasets.package import write_npz
    source,digest,_=graph_source(tmp_path,make_sample,graph_node_ids=np.array([b'001',b'002'],dtype='S3'))
    output=tmp_path/'ids.npz'
    write_npz(source,output,digest)
    with np.load(output,allow_pickle=False) as bundle:
        assert bundle['graph_node_ids'].tolist()==[b'001',b'002']
        info=json.loads(bundle['__array_metadata_json__'].item())['graph_node_ids']
        assert info['dtype']=='|S3'
        assert info['metadata']['h5py_encoding']=='ascii'
