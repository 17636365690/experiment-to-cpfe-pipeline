"""Modality-neutral asset metadata models."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class AssetKind(str, Enum):
    """Physical or logical modality represented by an asset."""

    TABLE = "table"
    TIME_SERIES = "time_series"
    ORIENTATION_MAP = "orientation_map"
    IMAGE = "image"
    VOXEL_GRID = "voxel_grid"
    POINT_FIELD = "point_field"
    MESH = "mesh"
    GRAIN_GRAPH = "grain_graph"
    FIELD_SEQUENCE = "field_sequence"


class DataLayer(str, Enum):
    """Provenance layer occupied by an asset."""

    RAW = "raw"
    CURATED = "curated"
    SOLVER_INPUT = "solver_input"
    SOLVER_OUTPUT = "solver_output"
    DERIVED_ML = "derived_ml"


class SourceKind(str, Enum):
    """Evidence class for a value or asset."""

    MEASURED = "measured"
    INFERRED = "inferred"
    INPUT = "input"
    SIMULATED = "simulated"


class AssetRef(BaseModel):
    """Immutable reference to one native or derived data asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: NonEmptyStr
    parent_asset_id: NonEmptyStr | None
    modality: AssetKind
    format: NonEmptyStr
    uri: NonEmptyStr
    source_kind: SourceKind
    layer: DataLayer
    units: dict[NonEmptyStr, NonEmptyStr]
    coordinate_frame: NonEmptyStr | None
    axis_order: tuple[NonEmptyStr, ...]
    dtype: NonEmptyStr | None
    shape: tuple[int, ...]
    native_layout: NonEmptyStr
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    license: NonEmptyStr | None
    lossy_transformations: tuple[NonEmptyStr, ...]


class AssetManifest(BaseModel):
    """Validated collection of assets and their immediate provenance links."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    assets: tuple[AssetRef, ...]

    @model_validator(mode="after")
    def validate_asset_ids_and_parents(self) -> "AssetManifest":
        asset_ids = [asset.asset_id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("duplicate asset_id in asset manifest")

        known_ids = set(asset_ids)
        for asset in self.assets:
            if (
                asset.parent_asset_id is not None
                and asset.parent_asset_id not in known_ids
            ):
                raise ValueError(
                    f"parent_asset_id {asset.parent_asset_id!r} is not in manifest"
                )
        return self

    def get(self, asset_id: str) -> AssetRef:
        """Return an asset by stable ID, or raise ``KeyError``."""

        for asset in self.assets:
            if asset.asset_id == asset_id:
                return asset
        raise KeyError(asset_id)


class ModalitySpec(BaseModel):
    """Explicit field contract for one supported modality and format."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: AssetKind
    format: NonEmptyStr
    required_fields: tuple[NonEmptyStr, ...]
    optional_fields: tuple[NonEmptyStr, ...]

    @model_validator(mode="after")
    def validate_field_sets(self) -> "ModalitySpec":
        required = set(self.required_fields)
        optional = set(self.optional_fields)
        if len(required) != len(self.required_fields):
            raise ValueError("required_fields contains duplicates")
        if len(optional) != len(self.optional_fields):
            raise ValueError("optional_fields contains duplicates")
        if required & optional:
            raise ValueError("optional_fields overlap required_fields")
        return self
