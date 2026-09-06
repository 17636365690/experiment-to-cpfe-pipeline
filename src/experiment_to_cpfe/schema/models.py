"""Normalized metadata and in-memory sample package models."""

from dataclasses import dataclass, field
from typing import Annotated, Literal

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from experiment_to_cpfe.assets.models import (
    AssetManifest,
    AssetRef,
    SourceKind,
)


NonEmptyStr = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]

RESERVED_TABLE_NAMES = frozenset(
    {
        "grains",
        "grain_boundaries",
        "mesh_nodes",
        "mesh_elements",
        "load_history",
        "measured_observations",
        "simulation_records",
    }
)


class SourceRef(BaseModel):
    """Reference to evidence used by a normalized sample."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: SourceKind
    uri: NonEmptyStr
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    role: NonEmptyStr


class CoordinateSpec(BaseModel):
    """Named spatial frame with an explicit axis convention and unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: NonEmptyStr
    axes: tuple[NonEmptyStr, ...] = Field(min_length=1)
    units: NonEmptyStr

    @field_validator("axes")
    @classmethod
    def axes_must_be_unique(
        cls,
        axes: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(axes) != len(set(axes)):
            raise ValueError("coordinate axes must be unique")
        return axes


class OrientationSpec(BaseModel):
    """Explicit orientation representation and crystallographic convention."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    representation: Literal["euler", "quaternion", "rotation_matrix"]
    convention: NonEmptyStr
    angle_units: Literal["degree", "radian"] | None
    crystal_symmetry: NonEmptyStr

    @model_validator(mode="after")
    def require_euler_angle_units(self) -> "OrientationSpec":
        if self.representation == "euler" and self.angle_units is None:
            raise ValueError("angle_units is required for Euler orientations")
        return self


class OrientationNotApplicable(BaseModel):
    """Explicit modeling applicability, distinct from unknown crystal orientation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    representation: Literal["not_applicable"]
    reason: NonEmptyStr


class SampleMetadata(BaseModel):
    """Stable identifiers and conventions shared by all sample modalities."""

    model_config = ConfigDict(extra="forbid")

    sample_id: NonEmptyStr
    experiment_id: NonEmptyStr
    microstructure_id: NonEmptyStr
    load_path_id: NonEmptyStr
    schema_version: NonEmptyStr
    coordinate: CoordinateSpec
    unit_system: dict[NonEmptyStr, NonEmptyStr]
    tensor_order: tuple[NonEmptyStr, ...] = Field(min_length=1)
    orientation: OrientationSpec | OrientationNotApplicable
    sources: tuple[SourceRef, ...]

    @field_validator("tensor_order")
    @classmethod
    def tensor_components_must_be_unique(
        cls,
        components: tuple[str, ...],
    ) -> tuple[str, ...]:
        if len(components) != len(set(components)):
            raise ValueError("tensor_order contains duplicate components")
        return components


@dataclass
class SamplePackage:
    """In-memory normalized sample with metadata kept separate from arrays."""

    metadata: SampleMetadata
    tables: dict[str, list[dict[str, object]]]
    arrays: dict[str, np.ndarray]
    assets: tuple[AssetRef, ...] = ()
    solver_inputs: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown_tables = set(self.tables) - RESERVED_TABLE_NAMES
        if unknown_tables:
            names = ", ".join(sorted(unknown_tables))
            raise ValueError(f"unknown reserved table name: {names}")

        for name, array in self.arrays.items():
            if not isinstance(array, np.ndarray):
                raise TypeError(f"array {name!r} must be a NumPy array")

        AssetManifest(assets=self.assets)
