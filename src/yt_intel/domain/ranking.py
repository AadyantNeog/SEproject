import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import fsum, hypot, log
from unicodedata import normalize

from yt_intel.contracts.models import ChannelSample, RankedChannel, RankedVideo, Video

VIDEO_RANKING_VERSION = "ranking-v1"
CHANNEL_RANKING_VERSION = "channel-ranking-v1"

_TOKEN = re.compile(r"\bv?\d+(?:\.\d+)+\b|[^\W\d_]\w*(?:\+\+|#)|\w+")
_STOP_WORDS = frozenset(
    "a an and are as at be by for from in is it of on or that the this to was with".split()
)
_TITLE_LENGTH = 256
_DESCRIPTION_LENGTH = 2_000
_TAG_COUNT = 32
_TAG_LENGTH = 128


def tokenize(text: str, *, max_chars: int = _DESCRIPTION_LENGTH) -> tuple[str, ...]:
    """Normalize one bounded field and preserve technical terms and dotted versions."""
    normalized = normalize("NFKC", text[:max_chars]).casefold()
    return tuple(
        token
        for token in _TOKEN.findall(normalized)
        if token not in _STOP_WORDS and len(token) <= 64 and token.strip("_")
    )


def build_video_document(video: Video) -> Counter[str]:
    title = tokenize(video.title, max_chars=_TITLE_LENGTH)
    description = tokenize(video.description or "")
    tags = tuple(
        token
        for tag in (video.tags or ())[:_TAG_COUNT]
        for token in tokenize(tag, max_chars=_TAG_LENGTH)
    )
    return Counter(title * 3 + description + tags * 2)


def tfidf_vectors(documents: Sequence[Counter[str]]) -> tuple[dict[str, float], ...]:
    """Fit one vocabulary and produce L2-normalized vectors for the supplied corpus."""
    document_frequency = Counter(term for document in documents for term in document)
    idf = {
        term: log((1 + len(documents)) / (1 + count)) + 1
        for term, count in document_frequency.items()
    }
    vectors = []
    for document in documents:
        weights = {
            term: (1 + log(document[term])) * idf[term] for term in sorted(document)
        }
        norm = hypot(*weights.values())
        vectors.append(
            {term: weight / norm for term, weight in weights.items()} if norm else {}
        )
    return tuple(vectors)


def cosine_similarity(left: Mapping[str, float], right: Mapping[str, float]) -> float:
    similarity = fsum(
        left[term] * right[term] for term in sorted(left.keys() & right.keys())
    )
    return min(similarity, 1.0)


def _matched_terms(
    left: Mapping[str, float], right: Mapping[str, float]
) -> tuple[str, ...]:
    return tuple(
        sorted(
            left.keys() & right.keys(),
            key=lambda term: (-left[term] * right[term], term),
        )[:8]
    )


def _overlap_reason(terms: tuple[str, ...]) -> str:
    return f"Overlapping metadata terms: {', '.join(terms[:3])}."


def _video_warnings(video: Video, label: str) -> list[str]:
    warnings = []
    if not video.description:
        warnings.append(f"{label} description unavailable.")
    if not video.tags:
        warnings.append(f"{label} tags unavailable.")
    return warnings


def rank_videos(
    seed: Video, candidates: Sequence[Video], *, limit: int
) -> tuple[RankedVideo, ...]:
    unique: dict[str, Video] = {}
    for video in candidates:
        if video.video_id != seed.video_id and video.availability == "available":
            unique.setdefault(video.video_id, video)

    seed_vector, *vectors = tfidf_vectors(
        [
            build_video_document(seed),
            *(build_video_document(v) for v in unique.values()),
        ]
    )
    scored = []
    for video, vector in zip(unique.values(), vectors, strict=True):
        cosine = cosine_similarity(seed_vector, vector)
        if cosine <= 0:
            continue
        terms = _matched_terms(seed_vector, vector)
        warnings = [
            *_video_warnings(seed, "Seed"),
            *_video_warnings(video, "Candidate"),
        ]
        if seed.category_id is None or video.category_id is None:
            score = cosine
            warnings.append("Category evidence unavailable. Score uses text only.")
            category_note = ""
        else:
            same_category = seed.category_id == video.category_id
            score = 0.90 * cosine + 0.10 * same_category
            category_note = (
                " Same category." if same_category else " Different category."
            )
        scored.append(
            (
                score,
                video,
                terms,
                _overlap_reason(terms) + category_note,
                tuple(warnings),
            )
        )

    scored.sort(key=lambda result: (-result[0], result[1].video_id))
    return tuple(
        RankedVideo(
            rank=rank,
            video=video,
            score=score,
            ranking_version=VIDEO_RANKING_VERSION,
            reason=reason,
            matched_terms=terms,
            evidence_warnings=warnings,
        )
        for rank, (score, video, terms, reason, warnings) in enumerate(
            scored[:limit], start=1
        )
    )


@dataclass(frozen=True, slots=True)
class ChannelCorpus:
    sample: ChannelSample
    videos: tuple[Video, ...]

    def supporting_document(self) -> Counter[str]:
        document = Counter(tokenize(self.sample.channel.description or ""))
        for video in self.videos:
            document.update(build_video_document(video))
        return document


def _channel_document(entry: ChannelCorpus, supporting: Counter[str]) -> Counter[str]:
    return (
        Counter(tokenize(entry.sample.channel.title, max_chars=_TITLE_LENGTH) * 3)
        + supporting
    )


def rank_channels(
    seed: ChannelCorpus, candidates: Sequence[ChannelCorpus], *, limit: int
) -> tuple[RankedChannel, ...]:
    seed_supporting = seed.supporting_document()
    if not seed_supporting:
        return ()
    unique: dict[str, ChannelCorpus] = {}
    for entry in candidates:
        channel_id = entry.sample.channel.channel_id
        if channel_id != seed.sample.channel.channel_id:
            unique.setdefault(channel_id, entry)

    comparable = [
        (entry, document)
        for entry in unique.values()
        if (document := entry.supporting_document())
    ]
    seed_vector, *vectors = tfidf_vectors(
        [
            _channel_document(seed, seed_supporting),
            *(_channel_document(entry, document) for entry, document in comparable),
        ]
    )
    scored = []
    for (entry, _), vector in zip(comparable, vectors, strict=True):
        cosine = cosine_similarity(seed_vector, vector)
        if cosine > 0:
            scored.append(
                (
                    cosine,
                    entry.sample,
                    _overlap_reason(_matched_terms(seed_vector, vector)),
                )
            )

    scored.sort(key=lambda result: (-result[0], result[1].channel.channel_id))
    return tuple(
        RankedChannel(
            rank=rank,
            sample=sample,
            score=score,
            ranking_version=CHANNEL_RANKING_VERSION,
            reason=reason,
            sample_limitations=sample.coverage.warnings,
        )
        for rank, (score, sample, reason) in enumerate(scored[:limit], start=1)
    )
