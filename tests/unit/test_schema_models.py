import numpy as np
import pytest
from pydantic import ValidationError

from experiment_to_cpfe.assets.models import (
    AssetKind,
    AssetRef,
    DataLayer,
    SourceKind,
)


def make_metadata():
    from experiment_to_cpfe.schema.models import (
        CoordinateSpec,
        OrientationSpec,
        SampleMetadata,
        SourceRef,
    )

    return SampleMetadata(
        sample_id="synthetic-001",
        experiment_id="demo-exp",
        microstructure_id="micro-001",
        load_path_id="uniaxial-z",
        schema_version="0.1",
        coordinate=CoordinateSpec(
            name="sample",
            axes=("x", "y", "z"),
            units="m",
        ),
        unit_system={"length": "m", "stress": "Pa", "time": "s"},
        tensor_order=("11", "22", "33", "12", "13", "23"),
        orientation=OrientationSpec(
            representation="quaternion",
            convention="scalar_first",
            angle_units=None,
            crystal_symmetry="cubic",
        ),
        sources=(
            SourceRef(
                kind=SourceKind.MEASURED,
                uri="examples/synthetic_minimal/experiment.csv",
                sha256=None,
                role="stress_strain_observation",
            ),
        ),
    )


def make_time_series_asset():
    return AssetRef(
        asset_id="asset-curated-001",
        parent_asset_id=None,
        modality=AssetKind.TIME_SERIES,
        format="csv",
        uri="examples/synthetic_minimal/experiment.csv",
        source_kind=SourceKind.MEASURED,
        layer=DataLayer.CURATED,
        units={"stress_33": "Pa", "time": "s"},
        coordinate_frame="sample",
        axis_order=("time",),
        dtype="float64",
        shape=(3, 3),
        native_layout="comma_delimited_columns",
        sha256=None,
        license="synthetic",
        lossy_transformations=(),
    )


def test_sample_package_preserves_evidence_labels_and_assets():
    from experiment_to_cpfe.schema.models import SamplePackage

    sample = SamplePackage(
        metadata=make_metadata(),
        tables={
            "measured_observations": [
                {"increment_id": "i0", "stress": 0.0}
            ],
            "simulation_records": [
                {"increment_id": "i0", "stress": 0.0}
            ],
        },
        arrays={"demo": np.array([1.0, 2.0])},
        assets=(make_time_series_asset(),),
    )

    assert sample.metadata.sources[0].kind is SourceKind.MEASURED
    assert "simulation_records" in sample.tables
    assert sample.assets[0].modality is AssetKind.TIME_SERIES


def test_sample_metadata_rejects_duplicate_tensor_components():
    values = make_metadata().model_dump()
    values["tensor_order"] = ("11", "22", "11")

    with pytest.raises(ValidationError, match="tensor_order"):
        type(make_metadata())(**values)


def test_euler_orientation_requires_explicit_angle_units():
    from experiment_to_cpfe.schema.models import OrientationSpec

    with pytest.raises(ValidationError, match="angle_units"):
        OrientationSpec(
            representation="euler",
            convention="bunge_zxz",
            angle_units=None,
            crystal_symmetry="cubic",
        )


def test_sample_package_rejects_unknown_table_name():
    from experiment_to_cpfe.schema.models import SamplePackage

    with pytest.raises(ValueError, match="reserved table"):
        SamplePackage(
            metadata=make_metadata(),
            tables={"stress_data": []},
            arrays={},
            assets=(),
        )


def test_sample_package_rejects_non_numpy_array():
    from experiment_to_cpfe.schema.models import SamplePackage

    with pytest.raises(TypeError, match="NumPy array"):
        SamplePackage(
            metadata=make_metadata(),
            tables={},
            arrays={"demo": [1.0, 2.0]},
            assets=(),
        )


def test_modality_spec_rejects_overlapping_fields():
    from experiment_to_cpfe.assets.models import ModalitySpec

    with pytest.raises(ValidationError, match="required_fields"):
        ModalitySpec(
            name=AssetKind.POINT_FIELD,
            format="csv",
            required_fields=("x", "y"),
            optional_fields=("y", "u"),
        )
