from collections.abc import Callable
from datetime import datetime
from hashlib import sha256
from re import fullmatch
from sqlite3 import Error as SqliteError
from uuid import uuid4

from pydantic import ValidationError

from yt_intel.contracts.common import AccountBinding, OpaqueId
from yt_intel.contracts.errors import ContractError, ErrorDetail
from yt_intel.contracts.models import CandidateSet, Coverage
from yt_intel.contracts.repositories import CacheRepository
from yt_intel.domain.ranking import VIDEO_RANKING_VERSION
from yt_intel.infrastructure.repositories import DEFAULT_CACHE_TTL
from yt_intel.services.discovery import VideoDiscoveryResult

_SOURCE = "fixture-video-discovery"


def _cache_key(candidate_set_id: OpaqueId) -> str:
    return sha256(f"{_SOURCE}:{candidate_set_id}".encode()).hexdigest()


def _storage_error() -> ContractError:
    return ContractError(
        ErrorDetail(
            code="PROVIDER_UNAVAILABLE",
            message="The local candidate set could not be stored or loaded.",
            retryable=False,
            safe_next_action="Check the fixture database and repeat the search.",
        )
    )


class FixtureCandidateSets:
    """Store bounded synthetic candidates using the account-scoped cache."""

    def __init__(self, cache: Callable[[], CacheRepository]) -> None:
        self._cache = cache

    async def publish(
        self, discovery: VideoDiscoveryResult, binding: AccountBinding, *, now: datetime
    ) -> OpaqueId:
        if binding.mode != "fixture":
            raise ValueError("only synthetic fixture candidates can be published")
        reference = f"discovery-{uuid4().hex}"
        cap = discovery.coverage.limits["video_candidates"]
        videos = discovery.candidates
        if len(videos) < cap:
            videos = (*videos, discovery.seed)
        coverage = Coverage.model_validate(
            {
                **discovery.coverage.model_dump(),
                "limits": {**discovery.coverage.limits, "candidates": cap},
            }
        )
        candidate_set = CandidateSet(
            candidate_set_id=reference,
            binding=binding,
            videos=videos,
            source=_SOURCE,
            seed_video_id=discovery.seed.video_id,
            topic=None,
            coverage=coverage,
            ranking_version=VIDEO_RANKING_VERSION,
            config_version="fixture-v1",
            created_at=now,
            expires_at=now + DEFAULT_CACHE_TTL,
        )
        try:
            await self._cache().put(
                binding,
                _cache_key(reference),
                candidate_set.model_dump_json().encode(),
                expires_at=candidate_set.expires_at,
                retained_until=candidate_set.expires_at,
            )
        except (OSError, SqliteError) as error:
            raise _storage_error() from error
        return reference

    async def load(
        self, reference: OpaqueId, binding: AccountBinding, *, now: datetime
    ) -> CandidateSet | None:
        if binding.mode != "fixture" or not fullmatch(
            r"discovery-[0-9a-f]{32}", reference
        ):
            return None
        try:
            raw = await self._cache().get(binding, _cache_key(reference), now=now)
            if raw is None:
                return None
            candidates = CandidateSet.model_validate_json(raw)
        except (OSError, SqliteError, ValidationError) as error:
            raise _storage_error() from error
        if (
            candidates.binding != binding
            or candidates.candidate_set_id != reference
            or candidates.source != _SOURCE
            or not candidates.created_at <= now < candidates.expires_at
        ):
            return None
        return candidates
