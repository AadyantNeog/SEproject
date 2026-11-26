from __future__ import annotations

import hashlib
import json
import random
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import anyio
import httpx

from yt_intel.contracts.approval import ApprovedWriteContext
from yt_intel.contracts.common import AccountBinding, OpaqueId
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.workflow import (
    CancellationToken,
    Clock,
    Endpoint,
    QuotaLedger,
    RequestContext,
)
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.redaction import redact_text, redact_url

type HttpMethod = Literal["GET", "POST"]
type OAuthEndpoint = Literal["oauth.token", "oauth.revoke"]

YOUTUBE_API_HOST = "www.googleapis.com"
GOOGLE_OAUTH_HOST = "oauth2.googleapis.com"
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_QUOTA_ERROR_REASONS = frozenset(
    {"quotaExceeded", "dailyLimitExceeded", "dailyLimitExceededUnreg"}
)
_CHANNEL_ERROR_REASONS = frozenset({"youtubeSignupRequired", "channelNotFound"})
_SCOPE_ERROR_REASONS = frozenset(
    {"insufficientPermissions", "forbidden", "accessNotConfigured"}
)
_RATE_LIMIT_REASONS = frozenset({"rateLimitExceeded", "userRateLimitExceeded"})


@dataclass(frozen=True, slots=True)
class RouteSpec:
    host: str
    path: str
    method: HttpMethod
    is_write: bool

    @property
    def url(self) -> str:
        return f"https://{self.host}{self.path}"


YOUTUBE_ROUTES: Mapping[Endpoint, RouteSpec] = {
    "videos.list": RouteSpec(YOUTUBE_API_HOST, "/youtube/v3/videos", "GET", False),
    "channels.list": RouteSpec(YOUTUBE_API_HOST, "/youtube/v3/channels", "GET", False),
    "search.list": RouteSpec(YOUTUBE_API_HOST, "/youtube/v3/search", "GET", False),
    "subscriptions.list": RouteSpec(
        YOUTUBE_API_HOST, "/youtube/v3/subscriptions", "GET", False
    ),
    "playlists.list": RouteSpec(
        YOUTUBE_API_HOST, "/youtube/v3/playlists", "GET", False
    ),
    "playlistItems.list": RouteSpec(
        YOUTUBE_API_HOST, "/youtube/v3/playlistItems", "GET", False
    ),
    "videoCategories.list": RouteSpec(
        YOUTUBE_API_HOST, "/youtube/v3/videoCategories", "GET", False
    ),
    "playlists.insert": RouteSpec(
        YOUTUBE_API_HOST, "/youtube/v3/playlists", "POST", True
    ),
    "playlistItems.insert": RouteSpec(
        YOUTUBE_API_HOST, "/youtube/v3/playlistItems", "POST", True
    ),
}

OAUTH_ROUTES: Mapping[OAuthEndpoint, RouteSpec] = {
    "oauth.token": RouteSpec(GOOGLE_OAUTH_HOST, "/token", "POST", False),
    "oauth.revoke": RouteSpec(GOOGLE_OAUTH_HOST, "/revoke", "POST", False),
}

_ALLOWLISTED_TUPLES: frozenset[tuple[str, str, str]] = frozenset(
    (spec.host, spec.path, spec.method)
    for spec in (*YOUTUBE_ROUTES.values(), *OAUTH_ROUTES.values())
)


class AuthHeaderProvider(Protocol):
    async def get_headers(self, binding: AccountBinding) -> Mapping[str, str]: ...


@dataclass(frozen=True, slots=True)
class HttpJsonResponse:
    status_code: int
    payload: Mapping[str, object]
    attempts: int
    request_url: str


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt_id: OpaqueId
    endpoint: str
    method: HttpMethod
    url: str
    status_code: int | None
    outcome: Literal["ok", "http_error", "timeout", "network_error", "cancelled"]
    error_code: ErrorCode | None = None


def _safe_label(text: str, *, fallback: str) -> str:
    cleaned = redact_text(text).strip()
    if not cleaned:
        return fallback
    if len(cleaned) > 256:
        return cleaned[:253] + "..."
    return cleaned


def _http_error(
    code: ErrorCode,
    message: str,
    *,
    retryable: bool,
    safe_next_action: str,
) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=_safe_label(message, fallback="Provider request failed."),
            retryable=retryable,
            safe_next_action=_safe_label(
                safe_next_action, fallback="Inspect configuration and try again."
            ),
        )
    )


def validate_allowlisted_url(url: str | httpx.URL, method: str) -> httpx.URL:
    """Verify an outbound URL is HTTPS, has no userinfo, and matches the exact allowlist."""
    parsed = httpx.URL(url)
    normalized_method = method.upper()
    if parsed.scheme != "https":
        raise _http_error(
            "UNSUPPORTED_IDENTIFIER",
            "Only HTTPS requests to allowlisted Google API routes are permitted.",
            retryable=False,
            safe_next_action="Use an official allowlisted HTTPS YouTube or Google OAuth endpoint.",
        )
    if parsed.username or parsed.password:
        raise _http_error(
            "UNSUPPORTED_IDENTIFIER",
            "Outbound URLs containing userinfo are forbidden.",
            retryable=False,
            safe_next_action="Remove credentials from the URL and use internal auth headers.",
        )
    if parsed.port is not None and parsed.port != 443:
        raise _http_error(
            "UNSUPPORTED_IDENTIFIER",
            "Outbound requests must use standard HTTPS port 443.",
            retryable=False,
            safe_next_action="Use the standard allowlisted HTTPS API endpoint.",
        )
    host = (parsed.host or "").casefold()
    if (host, parsed.path, normalized_method) not in _ALLOWLISTED_TUPLES:
        raise _http_error(
            "UNSUPPORTED_IDENTIFIER",
            "Destination host, path, or HTTP method is not on the official API allowlist.",
            retryable=False,
            safe_next_action="Restrict provider traffic to official allowlisted YouTube Data API v3 or Google OAuth routes.",
        )
    return parsed


def compute_write_request_digest(
    endpoint: Endpoint,
    *,
    params: Mapping[str, str] | None = None,
    json_body: Mapping[str, object] | None = None,
) -> str:
    """Compute a deterministic SHA-256 digest binding a write endpoint, params, and body."""
    route = YOUTUBE_ROUTES.get(endpoint)
    if route is None or not route.is_write:
        raise _http_error(
            "INVALID_INPUT",
            "Write request digests apply only to allowlisted write endpoints.",
            retryable=False,
            safe_next_action="Use playlists.insert or playlistItems.insert for write digests.",
        )
    canonical = {
        "endpoint": endpoint,
        "method": route.method,
        "path": route.path,
        "params": sorted((params or {}).items()),
        "body": json_body,
    }
    encoded = json.dumps(
        canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parse_retry_after(header_value: str | None) -> float | None:
    if not header_value:
        return None
    stripped = header_value.strip()
    try:
        seconds = float(stripped)
    except ValueError:
        return None
    if seconds < 0 or seconds != seconds:
        return None
    return seconds


def _extract_google_reason(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, Mapping):
        return None
    error_obj = body.get("error")
    if isinstance(error_obj, Mapping):
        errors = error_obj.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, Mapping):
                reason = first.get("reason")
                if isinstance(reason, str):
                    return reason
        status = error_obj.get("status")
        if isinstance(status, str):
            return status
    elif isinstance(error_obj, str):
        return error_obj
    return None


def _translate_http_error(
    response: httpx.Response, *, is_write: bool
) -> tuple[ContractError, bool]:
    """Translate an HTTP error status into a typed ContractError and retryable flag."""
    status = response.status_code
    reason = _extract_google_reason(response)

    if 300 <= status < 400:
        if is_write:
            return (
                _http_error(
                    "OPERATION_UNKNOWN",
                    f"Write returned unexpected HTTP redirect ({status}); remote state is unknown.",
                    retryable=False,
                    safe_next_action="Reconcile the operation before taking further action.",
                ),
                False,
            )
        return (
            _http_error(
                "PROVIDER_UNAVAILABLE",
                f"Provider returned unexpected HTTP redirect ({status}); redirects are disabled.",
                retryable=False,
                safe_next_action="Verify official API endpoint configuration; do not follow off-host redirects.",
            ),
            False,
        )

    if status == 400:
        return (
            _http_error(
                "INVALID_INPUT",
                "YouTube API rejected the request parameters.",
                retryable=False,
                safe_next_action="Verify identifiers, limits, and request fields before retrying.",
            ),
            False,
        )

    if status == 401:
        return (
            _http_error(
                "AUTH_REVOKED",
                "Authorisation credentials were rejected or expired.",
                retryable=False,
                safe_next_action="Re-authorise the local account using the CLI auth command.",
            ),
            False,
        )

    if status == 403:
        if reason in _QUOTA_ERROR_REASONS:
            return (
                _http_error(
                    "QUOTA_EXHAUSTED",
                    "YouTube API reported that the project quota bucket is exhausted.",
                    retryable=False,
                    safe_next_action="Wait for Pacific midnight quota reset or check local quota status.",
                ),
                False,
            )
        if reason in _CHANNEL_ERROR_REASONS:
            return (
                _http_error(
                    "CHANNEL_REQUIRED",
                    "The authorised Google account does not have an eligible YouTube channel.",
                    retryable=False,
                    safe_next_action="Create or select a YouTube channel for this account and re-check status.",
                ),
                False,
            )
        if reason in _RATE_LIMIT_REASONS:
            can_retry = not is_write
            return (
                _http_error(
                    "RATE_LIMITED",
                    "YouTube API rate limit exceeded.",
                    retryable=can_retry,
                    safe_next_action="Wait briefly and retry the request."
                    if can_retry
                    else "Do not automatically retry writes; reconcile the operation first.",
                ),
                can_retry,
            )
        if reason in _SCOPE_ERROR_REASONS or reason is None:
            return (
                _http_error(
                    "SCOPE_REQUIRED",
                    "Authorised account lacks permission or required YouTube API scope.",
                    retryable=False,
                    safe_next_action="Grant the required read or write scope via the local CLI auth flow.",
                ),
                False,
            )

    if status == 404:
        return (
            _http_error(
                "CONTENT_UNAVAILABLE",
                "Requested YouTube resource was not found or is unavailable.",
                retryable=False,
                safe_next_action="Verify the video, channel, or playlist is accessible.",
            ),
            False,
        )

    if status == 429:
        can_retry = not is_write
        return (
            _http_error(
                "RATE_LIMITED",
                "YouTube API rate limited the request (HTTP 429).",
                retryable=can_retry,
                safe_next_action="Wait before retrying."
                if can_retry
                else "Reconcile the write operation before taking further action.",
            ),
            can_retry,
        )

    if status >= 500:
        if is_write:
            return (
                _http_error(
                    "OPERATION_UNKNOWN",
                    f"Write received ambiguous server error (HTTP {status}); remote state is unknown.",
                    retryable=False,
                    safe_next_action="Reconcile the operation before retrying any writes.",
                ),
                False,
            )
        can_retry = status in {500, 502, 503, 504}
        return (
            _http_error(
                "PROVIDER_UNAVAILABLE",
                f"YouTube API returned transient server error (HTTP {status}).",
                retryable=can_retry,
                safe_next_action="Retry the read request shortly."
                if can_retry
                else "Inspect the request and try again later.",
            ),
            can_retry,
        )

    return (
        _http_error(
            "PROVIDER_UNAVAILABLE",
            f"Provider request failed with HTTP status {status}.",
            retryable=False,
            safe_next_action="Inspect the request and try again later.",
        ),
        False,
    )


class AccountedHttpExecutor:
    """Single quota-accounted, allowlisted, deadline-bound HTTPS executor."""

    def __init__(
        self,
        *,
        quota_ledger: QuotaLedger,
        auth_headers: AuthHeaderProvider | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Clock | None = None,
        attempt_timeout_seconds: float = 15.0,
        max_read_attempts: int = 3,
        base_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 8.0,
        sleep: Callable[[float], Awaitable[None]] = anyio.sleep,
        jitter: Callable[[], float] | None = None,
        attempt_id_factory: Callable[[], OpaqueId] | None = None,
        on_attempt: Callable[[AttemptRecord], None] | None = None,
    ) -> None:
        if attempt_timeout_seconds <= 0:
            raise ValueError("attempt_timeout_seconds must be positive")
        if not 1 <= max_read_attempts <= 3:
            raise ValueError("max_read_attempts must be between 1 and 3")
        if base_backoff_seconds < 0 or max_backoff_seconds < 0:
            raise ValueError("backoff values must be non-negative")

        self._quota_ledger = quota_ledger
        self._auth_headers = auth_headers
        self._clock: Clock = clock if clock is not None else SystemClock()
        self._attempt_timeout_seconds = attempt_timeout_seconds
        self._max_read_attempts = max_read_attempts
        self._base_backoff_seconds = base_backoff_seconds
        self._max_backoff_seconds = max_backoff_seconds
        self._sleep = sleep
        self._jitter: Callable[[], float] = (
            jitter if jitter is not None else (lambda: random.uniform(0.5, 1.0))
        )
        self._attempt_id_factory: Callable[[], OpaqueId] = (
            attempt_id_factory
            if attempt_id_factory is not None
            else (lambda: f"att-{uuid.uuid4().hex}")
        )
        self._on_attempt = on_attempt
        actual_transport = (
            transport if transport is not None else httpx.AsyncHTTPTransport(retries=0)
        )
        self._client = httpx.AsyncClient(
            transport=actual_transport,
            follow_redirects=False,
            trust_env=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> AccountedHttpExecutor:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def _remaining_seconds(self, deadline: datetime) -> float:
        return (deadline - self._clock.now()).total_seconds()

    def _record_attempt(self, record: AttemptRecord) -> None:
        if self._on_attempt is not None:
            self._on_attempt(record)

    async def _send_cancellable(
        self,
        request: httpx.Request,
        *,
        timeout_seconds: float,
        cancellation: CancellationToken,
    ) -> tuple[httpx.Response | None, bool]:
        """Send one HTTP request while watching the cooperative cancellation token."""
        response: httpx.Response | None = None
        send_error: httpx.HTTPError | None = None
        cancelled = False

        async def _watch_cancel(scope: anyio.CancelScope) -> None:
            nonlocal cancelled
            await cancellation.wait()
            cancelled = True
            scope.cancel()

        async def _do_send(scope: anyio.CancelScope) -> None:
            nonlocal response, send_error
            request.extensions["timeout"] = {
                "connect": timeout_seconds,
                "read": timeout_seconds,
                "write": timeout_seconds,
                "pool": timeout_seconds,
            }
            try:
                response = await self._client.send(request)
            except httpx.HTTPError as exc:
                send_error = exc
            finally:
                scope.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(_watch_cancel, tg.cancel_scope)
            tg.start_soon(_do_send, tg.cancel_scope)

        if send_error is not None:
            raise send_error
        if cancelled or cancellation.is_cancelled():
            return None, True
        return response, False

    async def _sleep_cancellable(
        self, delay_seconds: float, *, cancellation: CancellationToken
    ) -> bool:
        """Sleep for delay_seconds unless cancelled; returns True if cancelled."""
        if delay_seconds <= 0:
            return cancellation.is_cancelled()

        cancelled = False

        async def _watch(scope: anyio.CancelScope) -> None:
            nonlocal cancelled
            await cancellation.wait()
            cancelled = True
            scope.cancel()

        async def _wait(scope: anyio.CancelScope) -> None:
            await self._sleep(delay_seconds)
            scope.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(_watch, tg.cancel_scope)
            tg.start_soon(_wait, tg.cancel_scope)

        return cancelled or cancellation.is_cancelled()

    def _compute_backoff(
        self, attempt_number: int, retry_after_header: str | None
    ) -> float:
        retry_after = _parse_retry_after(retry_after_header)
        if retry_after is not None:
            return min(self._max_backoff_seconds, retry_after)
        raw = min(
            self._max_backoff_seconds,
            self._base_backoff_seconds * float(1 << (attempt_number - 1)),
        )
        factor = max(0.0, min(1.0, self._jitter()))
        return min(self._max_backoff_seconds, raw * factor)

    def _verify_and_freeze_write(
        self,
        ctx: RequestContext,
        endpoint: Endpoint,
        authority: ApprovedWriteContext | None,
        params: Mapping[str, str] | None,
        json_body: Mapping[str, object] | None,
    ) -> tuple[tuple[tuple[str, str], ...], bytes]:
        if authority is None:
            raise _http_error(
                "APPROVAL_REQUIRED",
                "Write requests require a verified internal ApprovedWriteContext.",
                retryable=False,
                safe_next_action="Obtain native human approval before dispatching a playlist write.",
            )
        if authority.binding != ctx.binding:
            raise _http_error(
                "ACCOUNT_MISMATCH",
                "Write authority binding does not match the active request account.",
                retryable=False,
                safe_next_action="Re-create the proposal under the active account and obtain fresh approval.",
            )
        if authority.reservation_id != ctx.reservation_id:
            raise _http_error(
                "OPERATION_CONFLICT",
                "Write authority reservation does not match the active request reservation.",
                retryable=False,
                safe_next_action="Use the exact reservation bound to the approved operation.",
            )
        frozen_params = tuple(sorted((params or {}).items()))
        # Freeze the exact JSON body bytes before digest verification so later mutations
        # to caller-owned dicts cannot alter what is sent on the wire.
        canonical_body_bytes = json.dumps(
            json_body, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
        frozen_body = json.loads(canonical_body_bytes.decode("utf-8"))
        actual_digest = compute_write_request_digest(
            endpoint, params=dict(frozen_params), json_body=frozen_body
        )
        if actual_digest != authority.request_digest:
            raise _http_error(
                "PROPOSAL_CHANGED",
                "Write request payload does not match the approved request digest.",
                retryable=False,
                safe_next_action="Rebuild and approve the exact proposal before writing.",
            )
        return frozen_params, canonical_body_bytes

    def _require_within_deadline(
        self, deadline: datetime, cancellation: CancellationToken
    ) -> float:
        if cancellation.is_cancelled():
            raise _http_error(
                "WORKFLOW_TIMEOUT",
                "Workflow was cancelled before dispatching the provider request.",
                retryable=False,
                safe_next_action="Start a new workflow if you still need this data.",
            )
        remaining = self._remaining_seconds(deadline)
        if remaining <= 0:
            raise _http_error(
                "WORKFLOW_TIMEOUT",
                "Workflow deadline expired before dispatching the provider request.",
                retryable=False,
                safe_next_action="Retry with a fresh workflow deadline.",
            )
        return remaining

    async def execute_youtube(
        self,
        ctx: RequestContext,
        endpoint: Endpoint,
        *,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
        authority: ApprovedWriteContext | None = None,
    ) -> HttpJsonResponse:
        """Execute an allowlisted, quota-accounted YouTube Data API v3 request."""
        route = YOUTUBE_ROUTES.get(endpoint)
        if route is None:
            raise _http_error(
                "UNSUPPORTED_IDENTIFIER",
                "Requested YouTube endpoint is not allowlisted.",
                retryable=False,
                safe_next_action="Use an official allowlisted YouTube Data API v3 endpoint.",
            )
        if not route.is_write and json_body is not None:
            raise _http_error(
                "INVALID_INPUT",
                "GET read endpoints do not accept a JSON request body.",
                retryable=False,
                safe_next_action="Send read parameters via query arguments only.",
            )
        frozen_params: tuple[tuple[str, str], ...] | None = None
        frozen_body_bytes: bytes | None = None
        if route.is_write:
            frozen_params, frozen_body_bytes = self._verify_and_freeze_write(
                ctx, endpoint, authority, params, json_body
            )
        elif params is not None:
            frozen_params = tuple(params.items())

        validated_url = validate_allowlisted_url(route.url, route.method)
        max_attempts = 1 if route.is_write else self._max_read_attempts

        for attempt in range(1, max_attempts + 1):
            self._require_within_deadline(ctx.deadline, ctx.cancellation)

            headers: dict[str, str] = {"Accept": "application/json"}
            if self._auth_headers is not None:
                auth_map = await self._auth_headers.get_headers(ctx.binding)
                headers.update(auth_map)
            if route.is_write:
                headers["Content-Type"] = "application/json"

            # Re-verify deadline and cancellation after async auth-header resolution
            # so expired requests never debit quota or start dispatch.
            self._require_within_deadline(ctx.deadline, ctx.cancellation)

            request = self._client.build_request(
                method=route.method,
                url=validated_url,
                params=frozen_params,
                content=frozen_body_bytes if route.is_write else None,
                headers=headers,
            )
            validate_allowlisted_url(request.url, request.method)
            if route.is_write:
                assert authority is not None
                wire_params = dict(request.url.params.multi_items())
                wire_body = json.loads(request.content.decode("utf-8"))
                wire_digest = compute_write_request_digest(
                    endpoint, params=wire_params, json_body=wire_body
                )
                if wire_digest != authority.request_digest:
                    raise _http_error(
                        "PROPOSAL_CHANGED",
                        "Built write request does not match the approved request digest.",
                        retryable=False,
                        safe_next_action="Rebuild and approve the exact proposal before writing.",
                    )
            safe_url = redact_url(str(request.url))

            attempt_id = self._attempt_id_factory()
            # Debit BEFORE dispatch so crashes cannot undercount quota.
            await self._quota_ledger.debit_attempt(ctx, endpoint, attempt_id)

            # Re-verify deadline right before dispatch using fresh remaining time.
            remaining = self._require_within_deadline(ctx.deadline, ctx.cancellation)
            timeout_seconds = min(self._attempt_timeout_seconds, remaining)
            try:
                response, was_cancelled = await self._send_cancellable(
                    request,
                    timeout_seconds=timeout_seconds,
                    cancellation=ctx.cancellation,
                )
            except httpx.TimeoutException:
                code: ErrorCode = (
                    "OPERATION_UNKNOWN" if route.is_write else "WORKFLOW_TIMEOUT"
                )
                self._record_attempt(
                    AttemptRecord(
                        attempt_id=attempt_id,
                        endpoint=endpoint,
                        method=route.method,
                        url=safe_url,
                        status_code=None,
                        outcome="timeout",
                        error_code=code,
                    )
                )
                if route.is_write:
                    raise _http_error(
                        "OPERATION_UNKNOWN",
                        "Write request timed out after dispatch; remote state is unknown.",
                        retryable=False,
                        safe_next_action="Reconcile the operation before retrying any writes.",
                    ) from None
                if attempt < max_attempts:
                    delay = self._compute_backoff(attempt, None)
                    if self._remaining_seconds(ctx.deadline) > delay:
                        if not await self._sleep_cancellable(
                            delay, cancellation=ctx.cancellation
                        ):
                            continue
                raise _http_error(
                    "WORKFLOW_TIMEOUT",
                    "YouTube API read attempt timed out.",
                    retryable=True,
                    safe_next_action="Retry the read request when the provider is responsive.",
                ) from None
            except httpx.HTTPError:
                code = "OPERATION_UNKNOWN" if route.is_write else "PROVIDER_UNAVAILABLE"
                self._record_attempt(
                    AttemptRecord(
                        attempt_id=attempt_id,
                        endpoint=endpoint,
                        method=route.method,
                        url=safe_url,
                        status_code=None,
                        outcome="network_error",
                        error_code=code,
                    )
                )
                if route.is_write:
                    raise _http_error(
                        "OPERATION_UNKNOWN",
                        "Write transport failed after dispatch; remote state is unknown.",
                        retryable=False,
                        safe_next_action="Reconcile the operation before retrying any writes.",
                    ) from None
                if attempt < max_attempts:
                    delay = self._compute_backoff(attempt, None)
                    if self._remaining_seconds(ctx.deadline) > delay:
                        if not await self._sleep_cancellable(
                            delay, cancellation=ctx.cancellation
                        ):
                            continue
                raise _http_error(
                    "PROVIDER_UNAVAILABLE",
                    "Network error while contacting the official YouTube API.",
                    retryable=True,
                    safe_next_action="Check connectivity and retry the read request.",
                ) from None

            if was_cancelled or response is None:
                code = "OPERATION_UNKNOWN" if route.is_write else "WORKFLOW_TIMEOUT"
                self._record_attempt(
                    AttemptRecord(
                        attempt_id=attempt_id,
                        endpoint=endpoint,
                        method=route.method,
                        url=safe_url,
                        status_code=None,
                        outcome="cancelled",
                        error_code=code,
                    )
                )
                if route.is_write:
                    raise _http_error(
                        "OPERATION_UNKNOWN",
                        "Write request was cancelled after dispatch; remote state is unknown.",
                        retryable=False,
                        safe_next_action="Reconcile the operation before taking further action.",
                    )
                raise _http_error(
                    "WORKFLOW_TIMEOUT",
                    "Read request was cancelled before completion.",
                    retryable=False,
                    safe_next_action="Start a new workflow if you still need this data.",
                )

            if 200 <= response.status_code < 300:
                try:
                    data = response.json()
                except ValueError:
                    err_code: ErrorCode = (
                        "OPERATION_UNKNOWN"
                        if route.is_write
                        else "PROVIDER_UNAVAILABLE"
                    )
                    self._record_attempt(
                        AttemptRecord(
                            attempt_id=attempt_id,
                            endpoint=endpoint,
                            method=route.method,
                            url=safe_url,
                            status_code=response.status_code,
                            outcome="http_error",
                            error_code=err_code,
                        )
                    )
                    if route.is_write:
                        raise _http_error(
                            "OPERATION_UNKNOWN",
                            "Write returned an unreadable JSON response; remote state is unknown.",
                            retryable=False,
                            safe_next_action="Reconcile the operation before taking further action.",
                        ) from None
                    raise _http_error(
                        "PROVIDER_UNAVAILABLE",
                        "YouTube API returned an invalid JSON response.",
                        retryable=False,
                        safe_next_action="Retry later or inspect provider diagnostics.",
                    ) from None
                if not isinstance(data, Mapping):
                    err_code = (
                        "OPERATION_UNKNOWN"
                        if route.is_write
                        else "PROVIDER_UNAVAILABLE"
                    )
                    self._record_attempt(
                        AttemptRecord(
                            attempt_id=attempt_id,
                            endpoint=endpoint,
                            method=route.method,
                            url=safe_url,
                            status_code=response.status_code,
                            outcome="http_error",
                            error_code=err_code,
                        )
                    )
                    if route.is_write:
                        raise _http_error(
                            "OPERATION_UNKNOWN",
                            "Write returned an unexpected non-object JSON payload; remote state is unknown.",
                            retryable=False,
                            safe_next_action="Reconcile the operation before taking further action.",
                        )
                    raise _http_error(
                        "PROVIDER_UNAVAILABLE",
                        "YouTube API returned an unexpected non-object JSON payload.",
                        retryable=False,
                        safe_next_action="Retry later or inspect provider diagnostics.",
                    )
                self._record_attempt(
                    AttemptRecord(
                        attempt_id=attempt_id,
                        endpoint=endpoint,
                        method=route.method,
                        url=safe_url,
                        status_code=response.status_code,
                        outcome="ok",
                    )
                )
                return HttpJsonResponse(
                    status_code=response.status_code,
                    payload=data,
                    attempts=attempt,
                    request_url=safe_url,
                )

            translated, should_retry = _translate_http_error(
                response, is_write=route.is_write
            )
            self._record_attempt(
                AttemptRecord(
                    attempt_id=attempt_id,
                    endpoint=endpoint,
                    method=route.method,
                    url=safe_url,
                    status_code=response.status_code,
                    outcome="http_error",
                    error_code=translated.detail.code,
                )
            )
            if should_retry and attempt < max_attempts:
                delay = self._compute_backoff(
                    attempt, response.headers.get("Retry-After")
                )
                if self._remaining_seconds(ctx.deadline) > delay:
                    if not await self._sleep_cancellable(
                        delay, cancellation=ctx.cancellation
                    ):
                        continue
            raise translated

        raise _http_error(
            "PROVIDER_UNAVAILABLE",
            "Provider request exhausted allowed attempts.",
            retryable=False,
            safe_next_action="Retry later.",
        )

    async def execute_oauth(
        self,
        endpoint: OAuthEndpoint,
        *,
        form_data: Mapping[str, str],
        deadline: datetime,
        cancellation: CancellationToken,
    ) -> HttpJsonResponse:
        """Execute an allowlisted Google OAuth token/revocation request (no YouTube quota)."""
        route = OAUTH_ROUTES.get(endpoint)
        if route is None:
            raise _http_error(
                "UNSUPPORTED_IDENTIFIER",
                "Requested OAuth endpoint is not allowlisted.",
                retryable=False,
                safe_next_action="Use official Google OAuth token or revocation endpoints only.",
            )
        if cancellation.is_cancelled():
            raise _http_error(
                "WORKFLOW_TIMEOUT",
                "OAuth request was cancelled before dispatch.",
                retryable=False,
                safe_next_action="Retry the local authorisation flow.",
            )
        remaining = self._remaining_seconds(deadline)
        if remaining <= 0:
            raise _http_error(
                "WORKFLOW_TIMEOUT",
                "OAuth request deadline expired before dispatch.",
                retryable=False,
                safe_next_action="Retry the local authorisation flow.",
            )

        validated_url = validate_allowlisted_url(route.url, route.method)
        request = self._client.build_request(
            method=route.method,
            url=validated_url,
            data=dict(form_data),
            headers={"Accept": "application/json"},
        )
        validate_allowlisted_url(request.url, request.method)
        safe_url = redact_url(str(request.url))
        attempt_id = self._attempt_id_factory()
        timeout_seconds = min(self._attempt_timeout_seconds, remaining)

        try:
            response, was_cancelled = await self._send_cancellable(
                request,
                timeout_seconds=timeout_seconds,
                cancellation=cancellation,
            )
        except httpx.TimeoutException:
            self._record_attempt(
                AttemptRecord(
                    attempt_id=attempt_id,
                    endpoint=endpoint,
                    method=route.method,
                    url=safe_url,
                    status_code=None,
                    outcome="timeout",
                    error_code="WORKFLOW_TIMEOUT",
                )
            )
            raise _http_error(
                "WORKFLOW_TIMEOUT",
                "Google OAuth request timed out.",
                retryable=True,
                safe_next_action="Check connectivity and retry the authorisation action.",
            ) from None
        except httpx.HTTPError:
            self._record_attempt(
                AttemptRecord(
                    attempt_id=attempt_id,
                    endpoint=endpoint,
                    method=route.method,
                    url=safe_url,
                    status_code=None,
                    outcome="network_error",
                    error_code="PROVIDER_UNAVAILABLE",
                )
            )
            raise _http_error(
                "PROVIDER_UNAVAILABLE",
                "Network error while contacting Google OAuth.",
                retryable=True,
                safe_next_action="Check connectivity and retry the authorisation action.",
            ) from None

        if was_cancelled or response is None:
            self._record_attempt(
                AttemptRecord(
                    attempt_id=attempt_id,
                    endpoint=endpoint,
                    method=route.method,
                    url=safe_url,
                    status_code=None,
                    outcome="cancelled",
                    error_code="WORKFLOW_TIMEOUT",
                )
            )
            raise _http_error(
                "WORKFLOW_TIMEOUT",
                "Google OAuth request was cancelled.",
                retryable=False,
                safe_next_action="Retry the authorisation action if needed.",
            )

        if 200 <= response.status_code < 300:
            payload: Mapping[str, object]
            if response.content:
                try:
                    parsed = response.json()
                except ValueError:
                    raise _http_error(
                        "PROVIDER_UNAVAILABLE",
                        "Google OAuth returned an invalid JSON response.",
                        retryable=False,
                        safe_next_action="Retry the authorisation action.",
                    ) from None
                if not isinstance(parsed, Mapping):
                    raise _http_error(
                        "PROVIDER_UNAVAILABLE",
                        "Google OAuth returned a non-object JSON payload.",
                        retryable=False,
                        safe_next_action="Retry the authorisation action.",
                    )
                payload = parsed
            else:
                payload = {}
            self._record_attempt(
                AttemptRecord(
                    attempt_id=attempt_id,
                    endpoint=endpoint,
                    method=route.method,
                    url=safe_url,
                    status_code=response.status_code,
                    outcome="ok",
                )
            )
            return HttpJsonResponse(
                status_code=response.status_code,
                payload=payload,
                attempts=1,
                request_url=safe_url,
            )

        translated, _ = _translate_http_error(response, is_write=True)
        self._record_attempt(
            AttemptRecord(
                attempt_id=attempt_id,
                endpoint=endpoint,
                method=route.method,
                url=safe_url,
                status_code=response.status_code,
                outcome="http_error",
                error_code=translated.detail.code,
            )
        )
        raise translated
