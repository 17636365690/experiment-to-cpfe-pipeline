from pathlib import Path

import pytest


def test_load_synthetic_config_resolves_paths():
    from experiment_to_cpfe.config import load_pipeline_config

    config = load_pipeline_config(Path("examples/synthetic_minimal/sample.yaml"))

    assert config.sample.sample_id == "synthetic-001"
    assert config.sources[0].table_name == "measured_observations"
    assert config.sources[0].path.name == "experiment.csv"
    assert config.sources[0].path.is_absolute()


def test_config_rejects_source_without_units(tmp_path):
    from experiment_to_cpfe.config import load_pipeline_config
    from experiment_to_cpfe.errors import ConfigurationError

    data = tmp_path / "data.csv"
    data.write_text("t,s\n0,0\n", encoding="utf-8")
    config = tmp_path / "sample.yaml"
    config.write_text(
        """
sample:
  sample_id: s1
  experiment_id: e1
  microstructure_id: m1
  load_path_id: l1
  schema_version: '0.1'
  coordinate: {name: sample, axes: [x, y, z], units: m}
  unit_system: {length: m, stress: Pa, time: s}
  tensor_order: ['11', '22', '33', '12', '13', '23']
  orientation: {representation: quaternion, convention: scalar_first, angle_units: null, crystal_symmetry: cubic}
sources:
  - path: data.csv
    table_name: measured_observations
    source_kind: measured
    modality: time_series
    format: csv
    delimiter: ','
    encoding: utf-8
    column_map: {time: t, stress_33: s}
    coordinate_frame: sample
    axis_order: [time]
    native_layout: columns
    license: synthetic
abaqus: {command: [abaqus], job_name: job}
export: {formats: [hdf5]}
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="units"):
        load_pipeline_config(config)


def test_config_resolves_native_input_bundle_paths(tmp_path):
    from experiment_to_cpfe.config import load_pipeline_config

    (tmp_path / "Example").mkdir()
    (tmp_path / "Input").mkdir()
    (tmp_path / "Example/main.inp").write_text("*Include, input=../Input/model.inp\n")
    (tmp_path / "Input/model.inp").write_text("*Node\n1,0,0,0\n")
    config = tmp_path / "native.yaml"
    config.write_text(f"""
sample:
  sample_id: s1
  experiment_id: e1
  microstructure_id: m1
  load_path_id: l1
  schema_version: '0.1'
  coordinate: {{name: sample, axes: [x, y, z], units: m}}
  unit_system: {{length: m, stress: Pa, time: s}}
  tensor_order: ['11', '22', '33', '12', '13', '23']
  orientation: {{representation: quaternion, convention: scalar_first, angle_units: null, crystal_symmetry: cubic}}
sources: []
abaqus:
  command: [abaqus]
  job_name: native
  input_bundle:
    source_root: .
    entrypoint: Example/main.inp
    submission_dir: Example
    license: synthetic
export: {{formats: [hdf5]}}
""", encoding="utf-8")

    loaded = load_pipeline_config(config)
    bundle = loaded.abaqus.input_bundle
    assert bundle is not None
    assert bundle.entrypoint == (tmp_path / "Example/main.inp").resolve()
    assert bundle.source_root == tmp_path.resolve()
    assert bundle.submission_dir == (tmp_path / "Example").resolve()
