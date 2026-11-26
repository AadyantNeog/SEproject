from __future__ import annotations

import re

from yt_intel.contracts.errors import ContractError, ErrorDetail

_MAX_TAG_LENGTH = 64
_ASCII_ALPHA_RE = re.compile(r"^[A-Za-z]+$")
_ASCII_ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")
_REGION_DIGITS_RE = re.compile(r"^\d{3}$")
_VARIANT_RE = re.compile(r"^(?:[A-Za-z0-9]{5,8}|\d[A-Za-z0-9]{3})$")


def normalize_language_tag(raw: str) -> str | None:
    """Validate and canonicalize a BCP 47 language tag, or return None if invalid.

    Compatible with ``yt_intel.domain.constraints.NormalizeLanguageTag``.
    Rejects underscores, empty subtags, unknown orderings, duplicate singletons,
    and tags longer than 64 characters.
    """
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if not cleaned or len(cleaned) > _MAX_TAG_LENGTH:
        return None
    if "_" in cleaned or " " in cleaned:
        return None

    parts = cleaned.split("-")
    if any(not part or not _ASCII_ALNUM_RE.fullmatch(part) for part in parts):
        return None

    idx = 0
    total = len(parts)
    output: list[str] = []

    # 1. Primary language subtag: 2-3 alpha (optional extlang) or 4-8 alpha.
    primary = parts[idx]
    if not _ASCII_ALPHA_RE.fullmatch(primary) or not 2 <= len(primary) <= 8:
        return None
    output.append(primary.lower())
    idx += 1

    # Optional extlang (up to 3 three-letter alpha subtags) only after 2-3 letter primary.
    if len(primary) <= 3:
        extlang_count = 0
        while (
            idx < total
            and extlang_count < 3
            and len(parts[idx]) == 3
            and _ASCII_ALPHA_RE.fullmatch(parts[idx])
        ):
            output.append(parts[idx].lower())
            idx += 1
            extlang_count += 1

    # 2. Optional script subtag: 4 alpha (Title Case).
    if idx < total and len(parts[idx]) == 4 and _ASCII_ALPHA_RE.fullmatch(parts[idx]):
        output.append(parts[idx].title())
        idx += 1

    # 3. Optional region subtag: 2 alpha (UPPER) or 3 digits.
    if idx < total and (
        (len(parts[idx]) == 2 and _ASCII_ALPHA_RE.fullmatch(parts[idx]))
        or _REGION_DIGITS_RE.fullmatch(parts[idx])
    ):
        output.append(parts[idx].upper())
        idx += 1

    # 4. Zero or more unique variant subtags.
    seen_variants: set[str] = set()
    while idx < total and _VARIANT_RE.fullmatch(parts[idx]):
        variant = parts[idx].lower()
        if variant in seen_variants:
            return None
        seen_variants.add(variant)
        output.append(variant)
        idx += 1

    # 5. Zero or more extensions: singleton (not x/X) + one or more 2-8 alnum subtags.
    seen_singletons: set[str] = set()
    while idx < total and len(parts[idx]) == 1 and parts[idx].lower() != "x":
        singleton = parts[idx].lower()
        if singleton in seen_singletons:
            return None
        seen_singletons.add(singleton)
        output.append(singleton)
        idx += 1
        ext_subtags = 0
        while idx < total and 2 <= len(parts[idx]) <= 8:
            output.append(parts[idx].lower())
            idx += 1
            ext_subtags += 1
        if ext_subtags == 0:
            return None

    # 6. Optional privateuse: 'x' + one or more 1-8 alnum subtags.
    if idx < total and parts[idx].lower() == "x":
        output.append("x")
        idx += 1
        priv_subtags = 0
        while idx < total and 1 <= len(parts[idx]) <= 8:
            output.append(parts[idx].lower())
            idx += 1
            priv_subtags += 1
        if priv_subtags == 0:
            return None

    if idx != total:
        return None
    return "-".join(output)


def parse_language_tag(raw: object) -> str:
    """Parse and canonicalize a BCP 47 language tag, raising ContractError if invalid."""
    if not isinstance(raw, str):
        raise ContractError(
            ErrorDetail(
                code="INVALID_INPUT",
                message="Language tag must be a valid BCP 47 string.",
                retryable=False,
                safe_next_action="Provide a BCP 47 language tag such as 'en' or 'en-US'.",
            )
        )
    normalized = normalize_language_tag(raw)
    if normalized is None:
        raise ContractError(
            ErrorDetail(
                code="INVALID_INPUT",
                message="Invalid BCP 47 language tag.",
                retryable=False,
                safe_next_action="Provide a valid BCP 47 language tag such as 'en', 'en-US', or 'es-419'.",
            )
        )
    return normalized


def language_tag_matches(requested: str, candidate: str | None) -> bool:
    """Return True iff candidate audio language strictly satisfies the requested tag."""
    if candidate is None:
        return False
    norm_requested = normalize_language_tag(requested)
    norm_candidate = normalize_language_tag(candidate)
    if norm_requested is None or norm_candidate is None:
        return False

    req_parts = norm_requested.casefold().split("-")
    cand_parts = norm_candidate.casefold().split("-")
    if req_parts[0] != cand_parts[0]:
        return False
    if any(len(part) == 1 for part in req_parts):
        return req_parts == cand_parts

    qualifiers: list[str] = []
    for part in cand_parts[1:]:
        if len(part) == 1:
            break
        qualifiers.append(part)
    return all(expected in qualifiers for expected in req_parts[1:])
