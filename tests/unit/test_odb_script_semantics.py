import csv
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest


class Value:
    def __init__(self, position='INTEGRATION_POINT', number=2.5, precision='SINGLE_PRECISION'):
        self.position = position
        self.precision = precision
        self.number = number
        self.instance = NS(name='PART-1')
        self.sectionPoint = NS(number=2, description='top')
        self.type = 'SCALAR'
        self.elementLabel = 17
        self.nodeLabel = 9
        self.integrationPoint = 3
        self.localCoordSystem = None
        self.localCoordSystemDouble = None

    @property
    def data(self):
        if self.precision == 'DOUBLE_PRECISION':
            raise RuntimeError('double data accessed through single interface')
        return self.number

    @property
    def dataDouble(self):
        assert self.precision == 'DOUBLE_PRECISION'
        return self.number


def field(*values):
    return NS(values=values, componentLabels=(), type='SCALAR', isEngineeringTensor=False, description='test field')


def extract(tmp_path, monkeypatch, frames, *, fields='S', position='integration_point', extra=()):
    from experiment_to_cpfe._resources import abaqus_extract_odb as script

    odb_path = tmp_path/'input.odb'
    odb_path.write_bytes(b'opaque fixture, not a real ODB')
    closed = []
    odb = NS(steps={'001': NS(frames=frames, domain='TIME')}, close=lambda: closed.append(True))
    def open_odb(path, readOnly):
        assert Path(path) == odb_path
        assert readOnly is True
        return odb
    monkeypatch.setitem(sys.modules, 'odbAccess', NS(openOdb=open_odb))
    out = tmp_path/'extracted'
    monkeypatch.setattr(sys, 'argv', ['extract', '--odb', str(odb_path), '--output-dir', str(out), '--fields', fields, '--position', position, *extra])
    result = script.main()
    assert closed == [True]
    return result, json.loads((out/'metadata.json').read_text()), list(csv.DictReader((out/'frames.csv').open()))


def frame(fields, number=7, domain='TIME'):
    return NS(fieldOutputs=fields, frameValue=0.25, incrementNumber=number, domain=domain, loadCase=None)


def test_position_filters_stored_values_and_retains_full_location(tmp_path, monkeypatch):
    result, meta, rows = extract(tmp_path, monkeypatch, [frame({'S':field(Value(), Value('NODAL',99))})])
    assert result == 0
    assert len(rows) == 1
    row = rows[0]
    assert row['position'] == 'INTEGRATION_POINT'
    assert row['instance'] == 'PART-1'
    assert row['element_label'] == '17'
    assert row['integration_point'] == '3'
    assert row['node_label'] == ''
    assert row['section_point'] == '2'
    assert row['increment_number'] == '7'
    assert row['step'] == '001'


def test_extractor_records_versioned_contract_and_host_uses_its_types(tmp_path, monkeypatch, make_sample, validation_policy):
    from experiment_to_cpfe.solvers.abaqus.extraction import load_extraction_bundle
    from experiment_to_cpfe.schema.validation import validate_sample

    first = Value('ELEMENT_NODAL', 2.0)
    second = Value('ELEMENT_NODAL', 3.0)
    second.nodeLabel = 10
    result, metadata, rows = extract(tmp_path, monkeypatch, [frame({'S': field(first, second)})], position='native')
    assert result == 0
    assert metadata['field_contract_version'] == '1.0'
    metadata['sample_metadata'] = make_sample().metadata.model_dump(mode='json')
    metadata['field_units'] = {'S': 'Pa'}
    (tmp_path / 'extracted' / 'metadata.json').write_text(json.dumps(metadata))
    sample = load_extraction_bundle(tmp_path / 'extracted')
    values = sample.tables['simulation_records']
    assert [(row['node_label'], row['element_label'], row['value']) for row in values] == [(9, 17, 2.0), (10, 17, 3.0)]
    assert validate_sample(sample, validation_policy).passed
    sample.tables['simulation_records'].append(dict(values[0]))
    assert any(issue.code == 'DUPLICATE_FIELD_RECORD' for issue in validate_sample(sample, validation_policy).errors)


def test_double_precision_access_is_not_silently_downcast(tmp_path, monkeypatch):
    value = Value(number=1.123456789012345, precision='DOUBLE_PRECISION')
    result, meta, rows = extract(tmp_path, monkeypatch, [frame({'S':field(value)})])
    assert result == 0
    assert float(rows[0]['value']) == 1.123456789012345
    assert rows[0]['precision'] == 'DOUBLE_PRECISION'


def test_missing_field_is_reported_per_frame_even_if_seen_elsewhere(tmp_path, monkeypatch):
    result, meta, rows = extract(tmp_path, monkeypatch, [frame({'S':field(Value())}), frame({})])
    assert result == 1
    assert meta['missing_fields'] == ['S']
    assert meta['missing_by_frame'][0]['frame'] == 1
    assert meta['missing_by_frame'][0]['field'] == 'S'
    assert len(rows) == 1


def test_field_at_wrong_position_is_missing_not_filled(tmp_path, monkeypatch):
    result, meta, rows = extract(tmp_path, monkeypatch, [frame({'S':field(Value('NODAL'))})])
    assert result == 1
    assert meta['missing_fields'] == ['S']
    assert rows == []


def test_native_position_preserves_nodal_values_and_node_ids(tmp_path, monkeypatch):
    result, meta, rows = extract(tmp_path, monkeypatch, [frame({'U':field(Value('NODAL'))})], fields='U', position='native')
    assert result == 0
    assert rows[0]['node_label'] == '9'
    assert rows[0]['element_label'] == ''


def test_frequency_frame_is_not_mislabeled_as_time(tmp_path, monkeypatch):
    result, meta, rows = extract(tmp_path, monkeypatch, [frame({'S':field(Value())},domain='FREQUENCY')])
    assert result == 0
    assert rows[0]['frame_time'] == ''
    assert rows[0]['frame_value'] == '0.25'
    assert rows[0]['domain'] == 'FREQUENCY'


def test_record_limit_reports_partial_output_as_failed(tmp_path, monkeypatch):
    result, meta, rows = extract(tmp_path, monkeypatch, [frame({'S':field(Value(),Value(),Value())})],extra=('--max-records','2'))
    assert result == 1
    assert len(rows) == 2
    assert meta['complete'] is False
    assert any('limit' in e for e in meta['errors'])


def test_existing_output_directory_is_not_overwritten(tmp_path, monkeypatch):
    from experiment_to_cpfe._resources import abaqus_extract_odb as script

    out=tmp_path/'existing'
    out.mkdir()
    (out/'frames.csv').write_text('original')
    monkeypatch.setitem(sys.modules,'odbAccess',NS(openOdb=lambda **kwargs: pytest.fail('opened ODB despite existing output')))
    monkeypatch.setattr(sys,'argv',['extract','--odb','x.odb','--output-dir',str(out),'--fields','S'])
    with pytest.raises((OSError, ValueError)):
        script.main()
    assert (out/'frames.csv').read_text() == 'original'


def test_complex_field_is_rejected_instead_of_dropping_imaginary_part(tmp_path,monkeypatch):
    complex_field=field(Value())
    complex_field.isComplex=True
    result,meta,rows=extract(tmp_path,monkeypatch,[frame({'S':complex_field},domain='FREQUENCY')])
    assert result==1
    assert rows==[]
    assert any('complex' in e.lower() for e in meta['errors'])


def test_unreadable_engineering_tensor_flag_is_recorded_unknown(tmp_path,monkeypatch):
    output=field(Value('NODAL'))
    del output.isEngineeringTensor
    result,meta,rows=extract(tmp_path,monkeypatch,[frame({'U':output})],fields='U',position='nodal')
    assert result==0
    assert meta['field_descriptors'][0]['is_engineering_tensor'] is None


def test_abaqus_numpy_vector_data_preserves_all_labeled_components(tmp_path,monkeypatch):
    import numpy as np

    value=Value('NODAL',np.array([1.,2.,3.],dtype=np.float32))
    output=field(value)
    output.componentLabels=('U1','U2','U3')
    output.type='VECTOR'
    result,meta,rows=extract(tmp_path,monkeypatch,[frame({'U':output})],fields='U',position='nodal')
    assert result==0
    assert [(r['component'],float(r['value'])) for r in rows]==[('U1',1.),('U2',2.),('U3',3.)]


def test_csv_preserves_exact_promoted_float32_value(tmp_path,monkeypatch):
    import numpy as np

    value=np.float32(1.1234567)
    result,meta,rows=extract(tmp_path,monkeypatch,[frame({'S':field(Value(number=value))})])
    assert result==0
    assert float(rows[0]['value'])==float(value)
