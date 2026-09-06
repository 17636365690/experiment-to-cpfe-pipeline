"""Configuration for partial native ingestion, separate from complete samples."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from experiment_to_cpfe.assets.models import AssetKind, NonEmptyStr, SourceKind


class NativeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NativeFile(NativeModel):
    path: Path
    format: NonEmptyStr
    source_kind: SourceKind
    license: NonEmptyStr | None
    native_layout: NonEmptyStr
    expected_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    source_uri: str | None = None


class ArraySelection(NativeModel):
    file: NonEmptyStr
    selector: dict[str, object] = Field(default_factory=dict)


class SpatialMeaning(NativeModel):
    axes: tuple[str, ...]
    origin: tuple[float, ...]
    spacing: tuple[float, ...]
    unit: str | None
    coordinate_frame: str | None


class QualityMeaning(NativeModel):
    array: str
    valid_values: tuple[float, ...]
    axes: tuple[int, ...]


class ArrayMeaning(NativeModel):
    quantity: str | None = None
    unit: str | None = None
    axes: tuple[str, ...] = ()
    source_kind: SourceKind | None = None
    evidence: str | None = None
    role: Literal["value", "field", "tensor", "orientation", "id", "mask", "target", "index", "features"] = "value"
    components: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    component_units: dict[str, str] = Field(default_factory=dict)
    spatial: SpatialMeaning | None = None
    coordinate_frame: str | None = None
    tensor_order: tuple[str, ...] = ()
    shear_convention: str | None = None
    reference_state: str | None = None
    orientation: dict[str, object] | None = None
    entity_ids: str | None = None
    entity_axis: int = 0
    identity_scope: str | None = None
    quality: QualityMeaning | None = None
    group_id: str | None = None
    split: str | None = None
    target_origin: str | None = None


class NativeImportConfig(NativeModel):
    import_id: NonEmptyStr
    profile: Literal["numeric", "gmsh22", "grain_graph", "stiffness"]
    modality: AssetKind
    files: dict[NonEmptyStr, NativeFile] = Field(min_length=1)
    selections: dict[NonEmptyStr, ArraySelection] = Field(default_factory=dict)
    meanings: dict[NonEmptyStr, ArrayMeaning] = Field(default_factory=dict)
    options: dict[str, object] = Field(default_factory=dict)
    checks: tuple[dict[str, object], ...] = ()
