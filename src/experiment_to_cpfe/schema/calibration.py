"""Explicit links between measured observations and calibration workflows."""

from dataclasses import dataclass

from experiment_to_cpfe.schema.models import SamplePackage


@dataclass(frozen=True)
class CalibrationTarget:
    source_asset_id: str
    response_kind: str
    observation_table: str
    split_role: str


def make_calibration_target(sample: SamplePackage) -> CalibrationTarget:
    """Register a measured curve as a target, never as a material card."""

    if "measured_observations" not in sample.tables:
        raise ValueError("measured_observations table is required")
    measured_assets = [
        asset
        for asset in sample.assets
        if asset.source_kind.value == "measured"
        and asset.modality.value == "time_series"
    ]
    if not measured_assets:
        raise ValueError("a measured time-series asset is required")
    return CalibrationTarget(
        source_asset_id=measured_assets[0].asset_id,
        response_kind="stress_strain",
        observation_table="measured_observations",
        split_role="calibration_or_validation",
    )
