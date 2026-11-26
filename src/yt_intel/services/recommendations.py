from collections import Counter
from datetime import datetime

from pydantic import TypeAdapter

from yt_intel.contracts.common import (
    AccountBinding,
    Contract,
    FrozenMap,
    Label,
    LanguageTag,
    Limit,
    NonNegative,
    Positive,
    UtcDateTime,
)
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.models import (
    CandidateSet,
    Coverage,
    LibrarySnapshot,
    LibrarySource,
    RankedVideo,
    SourceCoverage,
    Video,
    Warnings,
)
from yt_intel.domain.constraints import NormalizeLanguageTag, audio_language_matches
from yt_intel.domain.profiles import (
    PROFILE_VERSION,
    SOURCE_WEIGHTS,
    PreferenceProfile,
    build_profile,
    profile_search_query,
    rank_recommendations,
)
from yt_intel.domain.proposals import MIN_TOPIC_COSINE
from yt_intel.domain.ranking import tokenize

_UTC_TIME = TypeAdapter(UtcDateTime)


class RecommendationFilters(Contract):
    topic: Label | None = None
    total_seconds: Positive | None = None
    max_video_seconds: Positive | None = None
    language: LanguageTag | None = None
    limit: Limit = 10


class RecommendationResult(Contract):
    ranking_version: Label = PROFILE_VERSION
    results: tuple[RankedVideo, ...]
    sources: FrozenMap[LibrarySource, SourceCoverage]
    candidate_coverage: Coverage
    warnings: Warnings
    total_seconds: NonNegative | None = None
    unused_seconds: NonNegative | None = None


def _failure(code: ErrorCode, message: str, next_action: str) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code, message=message, retryable=False, safe_next_action=next_action
        )
    )


class RecommendationService:
    """Rank a server-resolved snapshot and candidate pool without fetching either."""

    def __init__(self, normalize_language: NormalizeLanguageTag) -> None:
        self._normalize_language = normalize_language

    def search_query(
        self, snapshot: LibrarySnapshot, *, binding: AccountBinding, now: datetime
    ) -> str:
        return profile_search_query(
            self._profile(
                snapshot, binding, _UTC_TIME.validate_python(now, strict=True)
            )
        )

    def recommend(
        self,
        snapshot: LibrarySnapshot,
        candidates: CandidateSet,
        *,
        binding: AccountBinding,
        now: datetime,
        filters: RecommendationFilters = RecommendationFilters(),
    ) -> RecommendationResult:
        now = _UTC_TIME.validate_python(now, strict=True)
        if candidates.binding != binding:
            raise _failure(
                "ACCOUNT_MISMATCH",
                "The candidate set belongs to a different account.",
                "Refresh the candidates for the current account.",
            )
        if not candidates.created_at <= now < candidates.expires_at:
            raise _failure(
                "CONTENT_UNAVAILABLE",
                "The candidate set is outside its validity window.",
                "Refresh the candidates and try again.",
            )
        profile = self._profile(snapshot, binding, now)
        topic = Counter(tokenize(filters.topic)) if filters.topic is not None else None
        language = (
            self._normalize_language(filters.language)
            if filters.language is not None
            else None
        )
        if (topic is not None and not topic) or (
            filters.language is not None and language is None
        ):
            raise _failure(
                "CLARIFICATION_REQUIRED",
                "A topic or language filter needs clarification.",
                "Supply a descriptive topic or a supported audio-language tag.",
            )

        eligible = tuple(
            video
            for video in candidates.videos
            if self._matches_filters(video, filters, language)
        )
        results = rank_recommendations(
            profile,
            eligible,
            limit=filters.limit,
            topic=topic,
            minimum_topic_cosine=MIN_TOPIC_COSINE,
            seed_video_id=candidates.seed_video_id,
            total_seconds=filters.total_seconds,
        )
        warnings = [
            "Videos already in the preference profile and the seed are excluded."
        ]
        for source in SOURCE_WEIGHTS:
            state = snapshot.sources[source].state
            if state != "retrieved":
                warnings.append(
                    f"{source.capitalize()} source: {state.replace('_', ' ')}."
                )
            elif source not in profile.source_documents:
                warnings.append(
                    f"{source.capitalize()} source has no usable preference evidence."
                )
        if "subscriptions" in profile.source_documents:
            warnings.append("Subscription samples describe channel topics.")
        if not results:
            warnings.append(
                "No candidate matched the available preferences and requested filters."
            )
        total = None
        unused = None
        if filters.total_seconds is not None:
            total = sum(
                result.video.duration_seconds
                for result in results
                if result.video.duration_seconds is not None
            )
            unused = filters.total_seconds - total
        return RecommendationResult(
            results=results,
            sources=snapshot.sources,
            candidate_coverage=candidates.coverage,
            warnings=tuple(warnings),
            total_seconds=total,
            unused_seconds=unused,
        )

    def _matches_filters(
        self, video: Video, filters: RecommendationFilters, language: str | None
    ) -> bool:
        duration = video.duration_seconds
        if filters.max_video_seconds is not None and (
            duration is None or duration > filters.max_video_seconds
        ):
            return False
        if filters.total_seconds is not None and (
            duration is None or duration > filters.total_seconds
        ):
            return False
        if language is None:
            return True
        if video.language_evidence != "audio" or video.default_audio_language is None:
            return False
        audio = self._normalize_language(video.default_audio_language)
        return audio is not None and audio_language_matches(language, audio)

    def _profile(
        self, snapshot: LibrarySnapshot, binding: AccountBinding, now: datetime
    ) -> PreferenceProfile:
        if snapshot.binding != binding:
            raise _failure(
                "ACCOUNT_MISMATCH",
                "The library snapshot belongs to a different account.",
                "Load a snapshot for the current account.",
            )
        if binding.mode != "fixture":
            raise _failure(
                "POLICY_BLOCKED",
                "Live recommendations are pending policy clearance.",
                "Use a synthetic fixture account.",
            )
        if not snapshot.fetched_at <= now < snapshot.retained_until:
            raise _failure(
                "CONTENT_UNAVAILABLE",
                "The library snapshot is outside its validity window.",
                "Load a current snapshot and try again.",
            )
        profile = build_profile(snapshot)
        if not profile.documents:
            sources = ", ".join(
                f"{name}: {snapshot.sources[name].state.replace('_', ' ')}"
                for name in SOURCE_WEIGHTS
            )
            raise _failure(
                "INSUFFICIENT_DATA",
                f"No usable preference evidence. Sources: {sources}.",
                "Ask for a seed video or topic.",
            )
        return profile
