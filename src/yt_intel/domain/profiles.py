from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import fsum, hypot

from yt_intel.contracts.models import LibrarySnapshot, LibrarySource, RankedVideo, Video

from .ranking import build_video_document, cosine_similarity, tfidf_vectors, tokenize

PROFILE_VERSION = "profile-v1"
SOURCE_WEIGHTS: Mapping[LibrarySource, float] = {
    "likes": 0.50,
    "playlists": 0.30,
    "subscriptions": 0.20,
}
_SOURCE_LABELS: Mapping[LibrarySource, str] = {
    "likes": "liked videos",
    "playlists": "playlist items",
    "subscriptions": "subscribed channel topics",
}


@dataclass(frozen=True, slots=True)
class PreferenceProfile:
    documents: tuple[Counter[str], ...]
    source_documents: Mapping[LibrarySource, tuple[int, ...]]
    excluded_video_ids: frozenset[str]


def build_profile(snapshot: LibrarySnapshot) -> PreferenceProfile:
    documents: list[Counter[str]] = []
    video_indices: dict[str, int] = {}
    excluded: set[str] = set()
    families: dict[LibrarySource, tuple[int, ...]] = {}

    def add_video_family(source: LibrarySource, video_ids: set[str]) -> None:
        excluded.update(video_ids)
        indices = []
        for video_id in sorted(video_ids):
            video = snapshot.videos.get(video_id)
            if video is None or video.availability != "available":
                continue
            if video_id not in video_indices:
                document = build_video_document(video)
                if not document:
                    continue
                video_indices[video_id] = len(documents)
                documents.append(document)
            indices.append(video_indices[video_id])
        if indices:
            families[source] = tuple(indices)

    if snapshot.sources["likes"].state == "retrieved":
        add_video_family("likes", set(snapshot.likes))
    if snapshot.sources["playlists"].state == "retrieved":
        playlist_ids = {
            item.video_id
            for item in snapshot.playlist_occurrences
            if item.video_id is not None
        }
        usable_ids = {
            item.video_id
            for item in snapshot.playlist_occurrences
            if item.video_id is not None and item.accessibility == "available"
        }
        excluded.update(playlist_ids)
        add_video_family("playlists", usable_ids)
    if snapshot.sources["subscriptions"].state == "retrieved":
        indices = []
        sampled_channels = set()
        for subscription in snapshot.subscriptions:
            sample = subscription.topic_sample
            if sample is None:
                continue
            excluded.update(sample.video_ids)
            if subscription.channel_id in sampled_channels:
                continue
            document = Counter(tokenize(sample.channel.title, max_chars=256) * 3)
            document.update(tokenize(sample.channel.description or ""))
            for video_id in sample.video_ids:
                video = snapshot.videos.get(video_id)
                if (
                    video is not None
                    and video.channel_id == subscription.channel_id
                    and video.availability == "available"
                ):
                    document.update(build_video_document(video))
            if document:
                sampled_channels.add(subscription.channel_id)
                indices.append(len(documents))
                documents.append(document)
        if indices:
            families["subscriptions"] = tuple(indices)

    return PreferenceProfile(tuple(documents), families, frozenset(excluded))


def _unit_vector(weights: Mapping[str, float]) -> dict[str, float]:
    norm = hypot(*(weights[term] for term in sorted(weights)))
    return {term: weight / norm for term, weight in weights.items()} if norm else {}


def _mean(vectors: Sequence[Mapping[str, float]]) -> dict[str, float]:
    weights: dict[str, list[float]] = {}
    for vector in vectors:
        for term, weight in vector.items():
            weights.setdefault(term, []).append(weight)
    return {term: fsum(weights[term]) / len(vectors) for term in sorted(weights)}


def _profile_vectors(
    profile: PreferenceProfile, vectors: Sequence[Mapping[str, float]]
) -> tuple[dict[str, float], dict[LibrarySource, dict[str, float]]]:
    families = {
        source: _unit_vector(_mean([vectors[index] for index in indices]))
        for source, indices in profile.source_documents.items()
    }
    active_weight = fsum(SOURCE_WEIGHTS[source] for source in families)
    combined: dict[str, float] = {}
    for source, vector in families.items():
        for term, weight in vector.items():
            combined[term] = (
                combined.get(term, 0.0)
                + weight * SOURCE_WEIGHTS[source] / active_weight
            )
    return _unit_vector(combined), families


def profile_search_query(profile: PreferenceProfile) -> str:
    """Derive a bounded search query. Final ranking refits the full shared corpus."""
    centroid, _ = _profile_vectors(profile, tfidf_vectors(profile.documents))
    terms = sorted(centroid, key=lambda term: (-centroid[term], term))[:8]
    selected: list[str] = []
    for term in terms:
        if len(" ".join([*selected, term])) > 256:
            break
        selected.append(term)
    return " ".join(selected)


def rank_recommendations(
    profile: PreferenceProfile,
    candidates: Sequence[Video],
    *,
    limit: int,
    topic: Counter[str] | None = None,
    minimum_topic_cosine: float = 0.0,
    seed_video_id: str | None = None,
    total_seconds: int | None = None,
) -> tuple[RankedVideo, ...]:
    unique: dict[str, Video] = {}
    for video in candidates:
        if (
            video.video_id != seed_video_id
            and video.video_id not in profile.excluded_video_ids
            and video.availability == "available"
        ):
            unique.setdefault(video.video_id, video)
    documents = [
        *profile.documents,
        *(build_video_document(video) for video in unique.values()),
    ]
    if topic is not None:
        documents.append(topic)
    vectors = tfidf_vectors(documents)
    centroid, families = _profile_vectors(profile, vectors)
    topic_vector = vectors[-1] if topic is not None else None
    scored = []
    for video, vector in zip(
        unique.values(),
        vectors[len(profile.documents) : len(profile.documents) + len(unique)],
        strict=True,
    ):
        if topic_vector is not None:
            overlap = cosine_similarity(topic_vector, vector)
            if overlap <= 0 or overlap < minimum_topic_cosine:
                continue
        score = cosine_similarity(centroid, vector)
        if score <= 0:
            continue
        sources = tuple(
            source
            for source, family in families.items()
            if cosine_similarity(family, vector) > 0
        )
        terms = tuple(
            sorted(
                centroid.keys() & vector.keys(),
                key=lambda term: (-centroid[term] * vector[term], term),
            )[:8]
        )
        scored.append((score, video, sources, terms))
    scored.sort(key=lambda result: (-result[0], result[1].video_id))

    results: list[RankedVideo] = []
    remaining = total_seconds
    for score, video, sources, terms in scored:
        if len(results) == limit:
            break
        if remaining is not None:
            duration = video.duration_seconds
            if duration is None or duration > remaining:
                continue
            remaining -= duration
        evidence = ", ".join(_SOURCE_LABELS[source] for source in sources)
        results.append(
            RankedVideo(
                rank=len(results) + 1,
                video=video,
                score=score,
                ranking_version=PROFILE_VERSION,
                reason=f"Matched {', '.join(terms[:2])} in {evidence}.",
                matched_terms=terms,
                preference_sources=sources,
            )
        )
    return tuple(results)
