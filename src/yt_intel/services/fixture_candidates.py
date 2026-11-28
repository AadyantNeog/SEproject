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
from yt_intel.domain.derived import DerivedProcessingCheck, fixture_only
from yt_intel.domain.ranking import VIDEO_RANKING_VERSION
from yt_intel.infrastructure.repositories import DEFAULT_CACHE_TTL
from yt_intel.services.discovery import VideoDiscoveryResult

_SOURCE = "fixture-video-discovery"


def _cache_key(source: str, candidate_set_id: OpaqueId) -> str:
    return sha256(f"{source}:{candidate_set_id}".encode()).hexdigest()


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
    """Store bounded discovery candidates using the account-scoped cache.

    The default stores synthetic fixture candidates only. The live composition
    passes the recorded D-02 check and its own source name.
    """

    def __init__(
        self,
        cache: Callable[[], CacheRepository],
        *,
        permits: DerivedProcessingCheck = fixture_only,
        source: str = _SOURCE,
        config_version: str = "fixture-v1",
    ) -> None:
        self._cache = cache
        self._permits = permits
        self._source = source
        self._config_version = config_version

    async def publish(
        self, discovery: VideoDiscoveryResult, binding: AccountBinding, *, now: datetime
    ) -> OpaqueId:
        if not self._permits(binding):
            raise ValueError("derived candidates are not permitted for this binding")
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
            source=self._source,
            seed_video_id=discovery.seed.video_id,
            topic=None,
            coverage=coverage,
            ranking_version=VIDEO_RANKING_VERSION,
            config_version=self._config_version,
            created_at=now,
            expires_at=now + DEFAULT_CACHE_TTL,
        )
        try:
            await self._cache().put(
                binding,
                _cache_key(self._source, reference),
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
        if not self._permits(binding) or not fullmatch(
            r"discovery-[0-9a-f]{32}", reference
        ):
            return None
        try:
            raw = await self._cache().get(
                binding, _cache_key(self._source, reference), now=now
            )
            if raw is None:
                return None
            candidates = CandidateSet.model_validate_json(raw)
        except (OSError, SqliteError, ValidationError) as error:
            raise _storage_error() from error
        if (
            candidates.binding != binding
            or candidates.candidate_set_id != reference
            or candidates.source != self._source
            or not candidates.created_at <= now < candidates.expires_at
        ):
            return None
        return candidates
