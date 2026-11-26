from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"

_AUTH_SCHEME_RE = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_AUTH_HEADER_RE = re.compile(
    r"(?im)^(Authorization|Proxy-Authorization|X-Goog-Api-Key|X-Api-Key)\s*:\s*[^\r\n]+"
)
_GOOGLE_TOKEN_RE = re.compile(
    r"\b(?:ya29\.[A-Za-z0-9._-]+|1//[A-Za-z0-9._-]+|AIza[0-9A-Za-z_-]{20,}|GOCSPX-[A-Za-z0-9_-]+)"
)
_SENSITIVE_PARAM_RE = re.compile(
    r"(?i)(\b(?:access_token|refresh_token|id_token|client_secret|code|code_verifier|token|api_key|key)=)([^&\s'\"<>]+)"
)
_SENSITIVE_HEADER_NAMES = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-goog-api-key",
        "x-api-key",
    }
)
_SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "token",
        "authorization",
        "proxy_authorization",
        "api_key",
        "key",
        "code",
        "code_verifier",
        "password",
        "secret",
        "cookie",
        "set_cookie",
    }
)


def redact_text(text: str, *, extra_secrets: Sequence[str] = ()) -> str:
    """Remove tokens, credentials, API keys, and sensitive query values from text."""
    result = text
    for secret in sorted(
        (item for item in extra_secrets if item), key=len, reverse=True
    ):
        result = result.replace(secret, REDACTED)
    result = _AUTH_HEADER_RE.sub(lambda m: f"{m.group(1)}: {REDACTED}", result)
    result = _AUTH_SCHEME_RE.sub(lambda m: f"{m.group(1)} {REDACTED}", result)
    result = _GOOGLE_TOKEN_RE.sub(REDACTED, result)
    result = _SENSITIVE_PARAM_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", result)
    return result


def redact_url(url: str, *, extra_secrets: Sequence[str] = ()) -> str:
    """Redact userinfo and sensitive query parameters from a URL string."""
    parsed = urlsplit(url)
    netloc = parsed.netloc
    if "@" in netloc:
        _, _, host_part = netloc.rpartition("@")
        netloc = f"{REDACTED}@{host_part}"

    if parsed.query:
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        safe_pairs = [
            (
                key,
                REDACTED
                if key.casefold() in _SENSITIVE_KEYS
                else redact_text(val, extra_secrets=extra_secrets),
            )
            for key, val in pairs
        ]
        safe_query = urlencode(safe_pairs, doseq=True)
    else:
        safe_query = ""

    rebuilt = urlunsplit((parsed.scheme, netloc, parsed.path, safe_query, ""))
    return redact_text(rebuilt, extra_secrets=extra_secrets)


def redact_headers(
    headers: Mapping[str, str], *, extra_secrets: Sequence[str] = ()
) -> dict[str, str]:
    """Return a copy of HTTP headers with credential headers masked."""
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        if key.casefold() in _SENSITIVE_HEADER_NAMES:
            sanitized[key] = REDACTED
        else:
            sanitized[key] = redact_text(value, extra_secrets=extra_secrets)
    return sanitized


def _redact_value(value: object, *, extra_secrets: Sequence[str]) -> object:
    if isinstance(value, str):
        return redact_text(value, extra_secrets=extra_secrets)
    if isinstance(value, Mapping):
        return redact_mapping(value, extra_secrets=extra_secrets)
    if isinstance(value, list):
        return [_redact_value(item, extra_secrets=extra_secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item, extra_secrets=extra_secrets) for item in value)
    return value


def redact_mapping(
    data: Mapping[object, object], *, extra_secrets: Sequence[str] = ()
) -> dict[str, object]:
    """Recursively mask sensitive keys and token patterns inside a mapping."""
    sanitized: dict[str, object] = {}
    for raw_key, value in data.items():
        key = str(raw_key)
        if key.casefold() in _SENSITIVE_KEYS:
            sanitized[key] = REDACTED
        else:
            sanitized[key] = _redact_value(value, extra_secrets=extra_secrets)
    return sanitized
