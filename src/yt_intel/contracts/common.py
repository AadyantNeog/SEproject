from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
)

type Mode = Literal["fixture", "live"]
type NonNegative = Annotated[int, Field(ge=0)]
type Positive = Annotated[int, Field(gt=0)]
type Limit = Annotated[int, Field(ge=1, le=50)]
type Text = Annotated[str, StringConstraints(max_length=10_000)]
type Label = Annotated[str, StringConstraints(pattern=r"\S", max_length=256)]
type OpaqueId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,128}$")]
type VideoId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{11}$")]
type ChannelId = Annotated[str, StringConstraints(pattern=r"^UC[A-Za-z0-9_-]{22}$")]
type PlaylistId = OpaqueId
type Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
type LanguageTag = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$", max_length=64)
]


def to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def freeze_mapping[K, V](value: Mapping[K, V]) -> Mapping[K, V]:
    return MappingProxyType(dict(value))


type UtcDateTime = Annotated[datetime, AwareDatetime, AfterValidator(to_utc)]
type FrozenMap[K, V] = Annotated[
    Mapping[K, V], AfterValidator(freeze_mapping), PlainSerializer(lambda value: dict(value))
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class VersionedContract(Contract):
    schema_version: Literal["1"] = "1"


class AccountBinding(Contract):
    installation_id: OpaqueId
    credential_binding_id: OpaqueId
    channel_id: ChannelId
    mode: Mode
