import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from pydantic import TypeAdapter, ValidationError

from yt_intel.contracts.common import AccountBinding, LanguageTag, OpaqueId, UtcDateTime
from yt_intel.contracts.models import CandidateSet, Video
from yt_intel.contracts.proposals import (
    PROPOSAL_LIFETIME,
    PlaylistBody,
    PlaylistConstraints,
    PlaylistProposal,
    ProposalItem,
    ProposalRef,
)

from .constraints import (
    NormalizeLanguageTag,
    PlaylistRequest,
    audio_language_matches,
    parse_playlist_request,
    planning_error,
)
from .ranking import build_video_document, cosine_similarity, tfidf_vectors, tokenize

TOPIC_VERSION = "topic-v1"
PACKING_VERSION = "greedy-relevance-v1"
AUTHORITY_VERSION = "proposal-authority-v1"
MIN_TOPIC_COSINE = 0.10
_MAX_ITEMS = 50
_UTC_TIME = TypeAdapter(UtcDateTime)
_AUDIO_TAG = TypeAdapter(LanguageTag)
_AUTHORITY_FIELDS = {
    "schema_version",
    "purpose",
    "ref",
    "binding",
    "destination_channel_title",
    "body",
    "constraints",
    "candidate_set_id",
    "items",
    "total_seconds",
    "unused_seconds",
    "exclusions",
    "warnings",
    "algorithm_versions",
    "expires_at",
}


def proposal_digest(proposal: PlaylistProposal) -> str:
    """Hash the versioned creation authority and exact ordered proposal content."""
    material = proposal.model_dump(mode="json", include=_AUTHORITY_FIELDS)
    canonical = json.dumps(
        {"authority_version": AUTHORITY_VERSION, "proposal": material},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ProposalRevision:
    superseded: PlaylistProposal
    replacement: PlaylistProposal


class PlaylistPlanner:
    """Pure planner consuming an already resolved candidate set and account context."""

    def __init__(self, normalize_language: NormalizeLanguageTag) -> None:
        self._normalize_language = normalize_language

    def plan(
        self,
        request: PlaylistRequest,
        candidates: CandidateSet,
        *,
        binding: AccountBinding,
        destination_channel_title: str,
        proposal_id: OpaqueId,
        now: datetime,
    ) -> PlaylistProposal:
        return self._build(
            request,
            candidates,
            binding,
            destination_channel_title,
            ProposalRef(proposal_id=proposal_id, version=1),
            now,
        )

    def revise(
        self,
        previous: PlaylistProposal,
        request: PlaylistRequest | Mapping[str, object],
        candidates: CandidateSet,
        *,
        binding: AccountBinding,
        destination_channel_title: str,
        now: datetime,
    ) -> ProposalRevision:
        now = _UTC_TIME.validate_python(now, strict=True)
        if previous.binding != binding:
            raise planning_error(
                "ACCOUNT_MISMATCH",
                "The proposal belongs to a different account.",
                "Open a proposal for the current account.",
            )
        if previous.expires_at <= now:
            raise planning_error(
                "APPROVAL_EXPIRED",
                "The previous proposal has expired.",
                "Build a new proposal from current candidates.",
            )
        if previous.state not in {
            "proposed",
            "approved",
        } or previous.digest != proposal_digest(previous):
            raise planning_error(
                "PROPOSAL_CHANGED",
                "The prior proposal version is no longer current.",
                "Load the current proposal or build a new preview.",
            )
        if not isinstance(request, PlaylistRequest):
            request = _revision_request(previous, candidates, request)
        reference = ProposalRef(
            proposal_id=previous.ref.proposal_id, version=previous.ref.version + 1
        )
        replacement = self._build(
            request, candidates, binding, destination_channel_title, reference, now
        )
        return ProposalRevision(
            previous.model_copy(update={"state": "superseded"}), replacement
        )

    def _build(
        self,
        request: PlaylistRequest,
        candidates: CandidateSet,
        binding: AccountBinding,
        destination_channel_title: str,
        reference: ProposalRef,
        now: datetime,
    ) -> PlaylistProposal:
        now = _UTC_TIME.validate_python(now, strict=True)
        if candidates.binding != binding:
            raise planning_error(
                "ACCOUNT_MISMATCH",
                "The candidate set belongs to a different account.",
                "Refresh the candidates for the current account.",
            )
        if binding.mode != "fixture":
            raise planning_error(
                "POLICY_BLOCKED",
                "Live playlist planning is pending policy clearance.",
                "Use a synthetic fixture account.",
            )
        if not candidates.created_at <= now < candidates.expires_at:
            raise planning_error(
                "CONTENT_UNAVAILABLE",
                "The candidate set is outside its validity window.",
                "Refresh the candidates and try again.",
            )

        normalized = self._normalize_language(request.language)
        topic = Counter(tokenize(request.topic))
        if normalized is None or not topic:
            raise planning_error(
                "CLARIFICATION_REQUIRED",
                "The topic or requested language needs clarification.",
                "Supply a descriptive topic and a supported audio language tag.",
            )
        exclusions: Counter[str] = Counter()
        eligible: list[Video] = []
        for video in candidates.videos:
            reason = self._ineligible(
                video, candidates.seed_video_id, request, normalized
            )
            if reason is None:
                eligible.append(video)
            else:
                exclusions[reason] += 1

        packed = _pack(topic, eligible, request.total_seconds, exclusions)
        if not packed:
            raise planning_error(
                "NO_FEASIBLE_PLAYLIST",
                "No candidate meets the current playlist constraints.",
                "Try a different candidate pool or explicitly revise the constraints.",
            )
        total = sum(item.duration_seconds for item in packed)
        warnings = [
            "Topic and audio matches use API metadata evidence.",
            f"Candidate coverage: {candidates.coverage.retrieved} retrieved, {candidates.coverage.usable} usable, "
            f"{candidates.coverage.inaccessible} inaccessible, {candidates.coverage.unknown} unknown.",
        ]
        if candidates.coverage.truncated or not candidates.coverage.complete:
            warnings.append("Candidate coverage is incomplete.")
        if total < request.total_seconds:
            warnings.append(
                "The playlist uses less than the requested maximum duration."
            )
        if (
            request.include_seed
            and candidates.seed_video_id
            and all(item.video_id != candidates.seed_video_id for item in packed)
        ):
            warnings.append(
                "The requested seed could not be selected under the current constraints and candidate pool."
            )

        proposal = PlaylistProposal(
            ref=reference,
            binding=binding,
            destination_channel_title=destination_channel_title,
            body=PlaylistBody(
                title=request.title,
                description=request.description,
                privacy=request.privacy,
            ),
            constraints=PlaylistConstraints(
                topic=request.topic,
                max_total_seconds=request.total_seconds,
                max_video_seconds=request.max_video_seconds,
                language=request.language,
            ),
            digest="0" * 64,
            created_at=now,
            expires_at=now + PROPOSAL_LIFETIME,
            warnings=tuple([*warnings, *candidates.coverage.warnings][:50]),
            candidate_set_id=candidates.candidate_set_id,
            items=packed,
            total_seconds=total,
            unused_seconds=request.total_seconds - total,
            exclusions=dict(exclusions),
            algorithm_versions={
                "topic": TOPIC_VERSION,
                "packing": PACKING_VERSION,
                "candidate-ranking": candidates.ranking_version,
            },
        )
        return proposal.model_copy(update={"digest": proposal_digest(proposal)})

    def _ineligible(
        self, video: Video, seed_id: str | None, request: PlaylistRequest, language: str
    ) -> str | None:
        if video.video_id == seed_id and not request.include_seed:
            return "seed_not_requested"
        if video.availability != "available":
            return "video_unavailable"
        if video.live_status != "recorded":
            return "recorded_status_not_verified"
        if video.duration_seconds is None or video.duration_seconds <= 0:
            return "duration_unknown"
        if video.duration_seconds > request.max_video_seconds:
            return "individual_duration_limit"
        raw_audio = video.default_audio_language
        if video.language_evidence != "audio" or raw_audio is None:
            return "audio_language_unverified"
        try:
            _AUDIO_TAG.validate_python(raw_audio, strict=True)
        except ValidationError:
            return "audio_language_unverified"
        normalized_audio = self._normalize_language(raw_audio)
        if normalized_audio is None:
            return "audio_language_unverified"
        if not audio_language_matches(language, normalized_audio):
            return "audio_language_mismatch"
        return None


def _revision_request(
    previous: PlaylistProposal, candidates: CandidateSet, changes: Mapping[str, object]
) -> PlaylistRequest:
    if not changes:
        raise planning_error(
            "CLARIFICATION_REQUIRED",
            "No playlist changes were supplied.",
            "Provide the fields you want to revise.",
        )
    if candidates.candidate_set_id != previous.candidate_set_id:
        raise planning_error(
            "PROPOSAL_CHANGED",
            "The saved candidate set does not match this proposal.",
            "Load the original candidate set or start a new proposal.",
        )
    constraints = previous.constraints
    seed_id = candidates.seed_video_id
    # If the saved pool contains the seed, the planner records its default
    # exclusion before any eligibility checks. Preserve the prior choice even
    # when an explicitly requested seed did not fit the prior constraints.
    include_seed = (
        "seed_not_requested" not in previous.exclusions
        and seed_id is not None
        and any(video.video_id == seed_id for video in candidates.videos)
    )
    return parse_playlist_request(
        {
            **previous.body.model_dump(),
            "topic": constraints.topic,
            "total_seconds": constraints.max_total_seconds,
            "max_video_seconds": constraints.max_video_seconds,
            "language": constraints.language,
            "duration_mode": constraints.duration_mode,
            "include_seed": include_seed,
            **changes,
        }
    )


def _pack(
    topic: Counter[str], eligible: list[Video], maximum: int, exclusions: Counter[str]
) -> tuple[ProposalItem, ...]:
    topic_vector, *vectors = tfidf_vectors(
        [topic, *(build_video_document(video) for video in eligible)]
    )
    scored = []
    for video, vector in zip(eligible, vectors, strict=True):
        terms = topic_vector.keys() & vector.keys()
        score = cosine_similarity(topic_vector, vector)
        if not terms or score < MIN_TOPIC_COSINE:
            exclusions["topic_mismatch"] += 1
        else:
            scored.append((score, video, terms))
    scored.sort(key=lambda match: (-match[0], match[1].video_id))

    items: list[ProposalItem] = []
    remaining = maximum
    for _, video, terms in scored:
        duration = video.duration_seconds
        audio = video.default_audio_language
        assert duration is not None and audio is not None
        if len(items) == _MAX_ITEMS:
            exclusions["item_limit"] += 1
        elif duration > remaining:
            exclusions["remaining_duration_limit"] += 1
        else:
            items.append(
                ProposalItem(
                    video_id=video.video_id,
                    title=video.title,
                    channel_title=video.channel_title
                    or video.channel_id
                    or "Unknown channel",
                    duration_seconds=duration,
                    audio_language=audio,
                    topic_evidence=f"{TOPIC_VERSION} matched: {', '.join(sorted(terms)[:3])}.",
                )
            )
            remaining -= duration
    return tuple(items)
