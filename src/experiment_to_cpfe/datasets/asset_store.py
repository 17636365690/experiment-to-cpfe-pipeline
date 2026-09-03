"""Compatibility facade for the canonical HDF5 asset store."""

from pathlib import Path

from experiment_to_cpfe.datasets.hdf5 import read_hdf5, write_hdf5
from experiment_to_cpfe.schema.models import SamplePackage


def write_asset_store(
    sample: SamplePackage,
    path: Path,
    source_manifest: dict[str, object] | None = None,
) -> str:
    return write_hdf5(sample, path, source_manifest)


def read_asset_store(path: Path) -> SamplePackage:
    return read_hdf5(path)
