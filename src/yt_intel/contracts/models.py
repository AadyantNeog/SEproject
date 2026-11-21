from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .common import (
    AccountBinding,
    ChannelId,
    Contract,
    FrozenMap,
    Label,
    Limit,
    NonNegative,
    OpaqueId,
    PlaylistId,
    Positive,
    Text,
    UtcDateTime,
    VersionedContract,
    VideoId,
)

type Access = Literal["available", "inaccessible", "unknown"]
type LibrarySource = Literal["likes", "subscriptions", "playlists"]
type Warnings = Annotated[tuple[Label, ...], Field(max_length=50)]


class Video(VersionedContract):
    video_id: VideoId
    channel_id: ChannelId | None
    title: Label
    channel_title: Label | None
    canonical_url: Text
    description: Text | None
    tags: Annotated[tuple[Label, ...], Field(max_length=500)] | None
    category_id: OpaqueId | None
    published_at: UtcDateTime | None
    duration_seconds: Positive | None
    default_audio_language: Label | None
    default_metadata_language: Label | None
    language_evidence: Literal["audio", "metadata_only", "unknown"]
    availability: Access
    live_status: Literal["recorded", "live", "upcoming", "unknown"]
    fetched_at: UtcDateTime
    evidence_warnings: Warnings = ()

    @model_validator(mode="after")
    def check_evidence(self) -> Self:
        if self.canonical_url != f"https://www.youtube.com/watch?v={self.video_id}":
            raise ValueError("video URL must be canonical and match video_id")
        if self.language_evidence == "audio" and self.default_audio_language is None:
            raise ValueError("audio language evidence requires an audio language tag")
        if (
            self.language_evidence == "metadata_only"
            and self.default_metadata_language is None
        ):
            raise ValueError(
                "metadata language evidence requires a metadata language tag"
            )
        return self


class Channel(VersionedContract):
    channel_id: ChannelId
    title: Label
    canonical_url: Text
    handle: Label | None
    description: Text | None
    uploads_playlist_id: PlaylistId | None
    fetched_at: UtcDateTime

    @model_validator(mode="after")
    def check_url(self) -> Self:
        if self.canonical_url != f"https://www.youtube.com/channel/{self.channel_id}":
            raise ValueError("channel URL must be canonical and match channel_id")
        return self


class Coverage(Contract):
    complete: bool
    paginated: bool
    sampled: bool
    truncated: bool
    retrieved: NonNegative
    usable: NonNegative
    inaccessible: NonNegative
    unknown: NonNegative
    limits: FrozenMap[Label, NonNegative] = Field(
        default_factory=dict, validate_default=True
    )
    sampled_sources: Warnings = ()
    completeness_basis: Label
    continuation_ref: OpaqueId | None = None
    warnings: Warnings = ()

    @model_validator(mode="after")
    def check_counts(self) -> Self:
        if self.usable > self.retrieved:
            raise ValueError("usable count cannot exceed retrieved count")
        if self.complete and (self.truncated or self.continuation_ref is not None):
            raise ValueError("complete coverage cannot be truncated or continued")
        return self


class ChannelSample(Contract):
    channel: Channel
    video_ids: tuple[VideoId, ...]
    attempted: NonNegative
    usable: NonNegative
    skipped: NonNegative
    selection_rule_version: Label
    coverage: Coverage

    @model_validator(mode="after")
    def check_sample(self) -> Self:
        if (
            len(set(self.video_ids)) != len(self.video_ids)
            or len(self.video_ids) != self.usable
        ):
            raise ValueError("sample must identify each usable video exactly once")
        if self.usable + self.skipped != self.attempted:
            raise ValueError(
                "usable and skipped must account for all attempted samples"
            )
        return self


class Page[T](Contract):
    """Internal provider page. Raw page tokens stay behind the service boundary."""

    items: Annotated[tuple[T, ...], Field(max_length=50)]
    next_page_token: Text | None = Field(exclude=True, repr=False)
    api_reported_total: NonNegative | None
    omitted: NonNegative
    inaccessible: NonNegative
    reason_codes: Warnings = ()


class PlaylistOccurrence(Contract):
    playlist_id: PlaylistId
    playlist_item_id: OpaqueId
    video_id: VideoId | None
    position: NonNegative | None
    added_at: UtcDateTime | None
    accessibility: Access


class SubscriptionSignal(Contract):
    subscription_id: OpaqueId
    channel_id: ChannelId
    subscribed_at: UtcDateTime | None
    topic_sample: ChannelSample | None
    coverage: Coverage

    @model_validator(mode="after")
    def check_channel(self) -> Self:
        if (
            self.topic_sample is not None
            and self.topic_sample.channel.channel_id != self.channel_id
        ):
            raise ValueError("subscription sample must use the subscribed channel")
        return self


class SourceCoverage(Contract):
    state: Literal["retrieved", "denied", "not_requested", "unavailable"]
    coverage: Coverage | None


class LibrarySnapshot(VersionedContract):
    snapshot_id: OpaqueId
    binding: AccountBinding
    started_at: UtcDateTime
    fetched_at: UtcDateTime
    likes: FrozenMap[VideoId, UtcDateTime | None]
    subscriptions: tuple[SubscriptionSignal, ...]
    owned_playlist_ids: tuple[PlaylistId, ...]
    playlist_occurrences: tuple[PlaylistOccurrence, ...]
    videos: FrozenMap[VideoId, Video]
    sources: FrozenMap[LibrarySource, SourceCoverage]
    retained_until: UtcDateTime

    @model_validator(mode="after")
    def check_snapshot(self) -> Self:
        if not self.started_at <= self.fetched_at < self.retained_until:
            raise ValueError("snapshot timestamps are out of order")
        if set(self.sources) != {"likes", "subscriptions", "playlists"}:
            raise ValueError(
                "snapshot must include a coverage state for each library source"
            )
        if any(video.video_id != key for key, video in self.videos.items()):
            raise ValueError("video map keys must match the video IDs")
        owned = set(self.owned_playlist_ids)
        if len(owned) != len(self.owned_playlist_ids):
            raise ValueError("owned playlist IDs must be unique")
        if any(item.playlist_id not in owned for item in self.playlist_occurrences):
            raise ValueError(
                "playlist occurrences must belong to the selected owned playlists"
            )
        return self


class RankedVideo(Contract):
    rank: Limit
    video: Video
    score: float
    ranking_version: Label
    reason: Label
    matched_terms: Warnings = ()
    evidence_warnings: Warnings = ()
    preference_sources: tuple[LibrarySource, ...] = ()


class RankedChannel(Contract):
    rank: Limit
    sample: ChannelSample
    score: float
    ranking_version: Label
    reason: Label
    sample_limitations: Warnings = ()


class CandidateSet(VersionedContract):
    candidate_set_id: OpaqueId
    binding: AccountBinding
    videos: tuple[Video, ...]
    source: Label
    seed_video_id: VideoId | None
    topic: Label | None
    coverage: Coverage
    ranking_version: Label
    config_version: Label
    created_at: UtcDateTime
    expires_at: UtcDateTime

    @model_validator(mode="after")
    def check_bounds(self) -> Self:
        if self.created_at >= self.expires_at:
            raise ValueError("candidate set must expire after creation")
        if len({video.video_id for video in self.videos}) != len(self.videos):
            raise ValueError("candidate video IDs must be unique")
        cap = self.coverage.limits.get("candidates")
        if cap is None or len(self.videos) > cap:
            raise ValueError("candidate set must declare and respect its candidate cap")
        return self
