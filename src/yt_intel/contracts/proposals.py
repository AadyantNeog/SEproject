from collections.abc import Sequence
from datetime import timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from .common import (
    AccountBinding,
    Contract,
    Digest,
    FrozenMap,
    Label,
    LanguageTag,
    NonNegative,
    OpaqueId,
    PlaylistId,
    Positive,
    UtcDateTime,
    VersionedContract,
    VideoId,
)
from .models import Warnings

type Privacy = Literal["private", "unlisted", "public"]
type ProposalState = Literal[
    "proposed", "approved", "rejected", "expired", "superseded"
]
PROPOSAL_LIFETIME = timedelta(minutes=10)


class PlaylistConstraints(Contract):
    topic: Label
    max_total_seconds: Positive
    max_video_seconds: Positive
    language: LanguageTag
    duration_mode: Literal["max"] = "max"


class PlaylistBody(Contract):
    title: Annotated[str, StringConstraints(pattern=r"\S", max_length=150)]
    description: Annotated[str, StringConstraints(max_length=5_000)] = ""
    privacy: Privacy = "private"


class ProposalItem(Contract):
    video_id: VideoId
    title: Label
    channel_title: Label
    duration_seconds: Positive
    audio_language: LanguageTag
    topic_evidence: Label

    @property
    def canonical_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


class ProposalRef(Contract):
    proposal_id: OpaqueId
    version: Positive


def validate_item_bounds(
    items: Sequence[ProposalItem], constraints: PlaylistConstraints
) -> int:
    if len(items) > 50 or len({item.video_id for item in items}) != len(items):
        raise ValueError("a playlist must contain at most 50 unique video IDs")
    if any(item.duration_seconds > constraints.max_video_seconds for item in items):
        raise ValueError("a playlist item exceeds the individual duration limit")
    total = sum(item.duration_seconds for item in items)
    if total > constraints.max_total_seconds:
        raise ValueError("playlist exceeds the total duration limit")
    return total


class ProposalAuthority(VersionedContract):
    ref: ProposalRef
    binding: AccountBinding
    destination_channel_title: Label
    body: PlaylistBody
    constraints: PlaylistConstraints
    digest: Digest
    created_at: UtcDateTime
    expires_at: UtcDateTime
    state: ProposalState = "proposed"
    warnings: Warnings = ()

    @model_validator(mode="after")
    def check_expiry(self) -> Self:
        if not timedelta(0) < self.expires_at - self.created_at <= PROPOSAL_LIFETIME:
            raise ValueError("proposal expiry must be within ten minutes of issuance")
        return self


class PlaylistProposal(ProposalAuthority):
    purpose: Literal["create"] = "create"
    candidate_set_id: OpaqueId
    items: Annotated[tuple[ProposalItem, ...], Field(min_length=1, max_length=50)]
    total_seconds: Positive
    unused_seconds: NonNegative
    exclusions: FrozenMap[Label, NonNegative]
    algorithm_versions: FrozenMap[Label, Label]

    @model_validator(mode="after")
    def check_totals(self) -> Self:
        total = validate_item_bounds(self.items, self.constraints)
        if self.total_seconds != total or self.unused_seconds != (
            self.constraints.max_total_seconds - total
        ):
            raise ValueError(
                "proposal totals must match the exact approved item durations"
            )
        return self


class VerifiedPlaylistItem(Contract):
    playlist_item_id: OpaqueId
    item: ProposalItem


class ResumeProposal(ProposalAuthority):
    purpose: Literal["resume"] = "resume"
    original_operation_id: OpaqueId
    original_proposal: ProposalRef
    original_digest: Digest
    remote_playlist_id: PlaylistId
    verified_at: UtcDateTime
    verified_prefix: Annotated[tuple[VerifiedPlaylistItem, ...], Field(max_length=49)]
    missing_suffix: Annotated[
        tuple[ProposalItem, ...], Field(min_length=1, max_length=50)
    ]

    @model_validator(mode="after")
    def check_verified_items(self) -> Self:
        if self.ref.proposal_id == self.original_proposal.proposal_id:
            raise ValueError("a resume proposal requires its own ID")
        if self.verified_at > self.created_at:
            raise ValueError("resume proposal must follow verification")
        remote_ids = {entry.playlist_item_id for entry in self.verified_prefix}
        if len(remote_ids) != len(self.verified_prefix):
            raise ValueError("verified playlist item IDs must be unique")
        items = (
            tuple(entry.item for entry in self.verified_prefix) + self.missing_suffix
        )
        validate_item_bounds(items, self.constraints)
        return self
