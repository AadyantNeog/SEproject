from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import webbrowser
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

import anyio

from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.workflow import CancellationToken, Clock
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.http import AccountedHttpExecutor

YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
YOUTUBE_WRITE_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URI = "https://oauth2.googleapis.com/revoke"
LOOPBACK_HOST = "127.0.0.1"
CALLBACK_PATH = "/oauth2callback"


def _auth_error(
    code: ErrorCode,
    message: str,
    *,
    safe_next_action: str,
    retryable: bool = False,
) -> ContractError:
    return ContractError(
        ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            safe_next_action=safe_next_action,
        )
    )


def generate_pkce_pair() -> tuple[str, str]:
    """Generate an RFC 7636 PKCE (code_verifier, S256 code_challenge) pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_loopback_redirect_uri(port: int) -> str:
    """Build a loopback-only OAuth redirect URI on 127.0.0.1."""
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise _auth_error(
            "INVALID_INPUT",
            "OAuth loopback callback port must be an unprivileged TCP port (1024-65535).",
            safe_next_action="Use an ephemeral loopback port bound to 127.0.0.1.",
        )
    return f"http://{LOOPBACK_HOST}:{port}{CALLBACK_PATH}"


def validate_loopback_redirect_uri(redirect_uri: str) -> str:
    """Validate that an OAuth redirect URI binds strictly to local 127.0.0.1 loopback."""
    parsed = urlsplit(redirect_uri)
    if (
        parsed.scheme != "http"
        or parsed.hostname != LOOPBACK_HOST
        or parsed.port is None
        or not 1024 <= parsed.port <= 65535
        or parsed.path != CALLBACK_PATH
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query != ""
        or parsed.fragment != ""
    ):
        raise _auth_error(
            "UNSUPPORTED_IDENTIFIER",
            "OAuth redirect URI must use local loopback http://127.0.0.1:<port>/oauth2callback.",
            safe_next_action="Bind the OAuth callback strictly to 127.0.0.1 on an ephemeral port; OOB copy/paste is disabled.",
        )
    return redirect_uri


@dataclass(frozen=True, slots=True)
class OAuthClientConfig:
    """Local operator OAuth desktop client configuration (kept outside git/logs)."""

    client_id: str
    client_secret: str | None = None

    def __repr__(self) -> str:
        return f"OAuthClientConfig(client_id={self.client_id!r}, client_secret='[REDACTED]')"


@dataclass(frozen=True, slots=True)
class PendingAuthRequest:
    """Ephemeral state and PKCE verifier held locally while awaiting browser callback."""

    authorization_url: str
    state: str
    code_verifier: str
    redirect_uri: str
    requested_scopes: tuple[str, ...]

    def __repr__(self) -> str:
        return (
            "PendingAuthRequest("
            f"redirect_uri={self.redirect_uri!r}, "
            f"requested_scopes={self.requested_scopes!r}, "
            "state='[REDACTED]', code_verifier='[REDACTED]')"
        )


@dataclass(frozen=True, slots=True)
class OAuthTokenSet:
    """Stored OAuth credentials with redacted repr and explicit granted scopes."""

    access_token: str
    refresh_token: str | None
    expires_at: datetime
    granted_scopes: tuple[str, ...]
    token_type: str = "Bearer"

    def __repr__(self) -> str:
        return (
            "OAuthTokenSet("
            f"expires_at={self.expires_at.isoformat()!r}, "
            f"granted_scopes={self.granted_scopes!r}, "
            "access_token='[REDACTED]', refresh_token='[REDACTED]')"
        )

    def to_vault_bytes(self) -> bytes:
        payload = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.astimezone(UTC).isoformat(),
            "granted_scopes": list(self.granted_scopes),
            "token_type": self.token_type,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )

    @classmethod
    def from_vault_bytes(cls, data: bytes) -> OAuthTokenSet:
        raw = json.loads(data.decode("utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("vault payload must be a JSON object")
        access = raw.get("access_token")
        refresh = raw.get("refresh_token")
        expires_raw = raw.get("expires_at")
        scopes_raw = raw.get("granted_scopes")
        token_type = raw.get("token_type", "Bearer")
        if (
            not isinstance(access, str)
            or not access
            or (refresh is not None and not isinstance(refresh, str))
            or not isinstance(expires_raw, str)
            or not isinstance(scopes_raw, list)
            or not all(isinstance(s, str) and s for s in scopes_raw)
            or not isinstance(token_type, str)
        ):
            raise ValueError("malformed token set in vault")
        expires_at = datetime.fromisoformat(expires_raw)
        if expires_at.tzinfo is None:
            raise ValueError("expires_at must be timezone-aware")
        return cls(
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at.astimezone(UTC),
            granted_scopes=tuple(dict.fromkeys(scopes_raw)),
            token_type=token_type,
        )


def verify_oauth_callback(
    pending: PendingAuthRequest, callback_params: Mapping[str, str]
) -> str:
    """Verify OAuth loopback callback state and return the one-time auth code."""
    error = callback_params.get("error")
    if error:
        if error == "access_denied":
            raise _auth_error(
                "SCOPE_REQUIRED",
                "Google authorisation was declined by the user.",
                safe_next_action="Run the local CLI auth command again and approve the requested YouTube scope.",
            )
        raise _auth_error(
            "AUTH_REQUIRED",
            f"Google authorisation failed ({error}).",
            safe_next_action="Retry the local CLI auth command.",
        )

    returned_state = callback_params.get("state", "")
    if not returned_state or not hmac.compare_digest(returned_state, pending.state):
        raise _auth_error(
            "AUTH_REQUIRED",
            "OAuth callback state validation failed; possible CSRF or stale flow.",
            safe_next_action="Restart the local CLI auth command from the beginning.",
        )

    code = callback_params.get("code", "").strip()
    if not code:
        raise _auth_error(
            "AUTH_REQUIRED",
            "OAuth callback did not include an authorisation code.",
            safe_next_action="Restart the local CLI auth command and complete sign-in.",
        )
    return code


def _parse_scopes(
    raw_scope: object, *, fallback: Sequence[str] = ()
) -> tuple[str, ...]:
    if isinstance(raw_scope, str) and raw_scope.strip():
        return tuple(dict.fromkeys(raw_scope.strip().split()))
    return tuple(dict.fromkeys(fallback))


def scopes_for_auth_mode(*, enable_writes: bool) -> tuple[str, ...]:
    """Return explicit YouTube OAuth scopes for read-only or write-enabled desktop auth."""
    if enable_writes:
        return (YOUTUBE_READONLY_SCOPE, YOUTUBE_WRITE_SCOPE)
    return (YOUTUBE_READONLY_SCOPE,)


def load_oauth_client_config(path: Path) -> OAuthClientConfig:
    """Load local desktop OAuth client credentials from a JSON file outside the repo."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise _auth_error(
            "INVALID_INPUT",
            "Could not read local OAuth desktop client configuration JSON.",
            safe_next_action="Provide a valid local Google Desktop OAuth JSON file outside the repository.",
        ) from None
    if not isinstance(raw, Mapping):
        raise _auth_error(
            "INVALID_INPUT",
            "OAuth client configuration JSON must be an object.",
            safe_next_action="Export a Desktop App OAuth JSON file from Google Cloud Console.",
        )
    installed = raw.get("installed")
    section: Mapping[object, object] = (
        installed if isinstance(installed, Mapping) else raw
    )
    client_id = section.get("client_id")
    client_secret = section.get("client_secret")
    if not isinstance(client_id, str) or not client_id.strip():
        raise _auth_error(
            "INVALID_INPUT",
            "OAuth client configuration JSON is missing a valid client_id.",
            safe_next_action="Use a Desktop App OAuth client JSON containing client_id.",
        )
    secret_val = (
        client_secret.strip()
        if isinstance(client_secret, str) and client_secret.strip()
        else None
    )
    return OAuthClientConfig(client_id=client_id.strip(), client_secret=secret_val)


class LoopbackCallbackServer:
    """Ephemeral 127.0.0.1 HTTP server capturing one OAuth redirect callback."""

    def __init__(self) -> None:
        self._done = threading.Event()
        self._params: dict[str, str] | None = None
        parent = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urlsplit(self.path)
                if parsed.path != CALLBACK_PATH:
                    self.send_response(404)
                    self.end_headers()
                    return
                parent._params = dict(parse_qsl(parsed.query, keep_blank_values=True))
                body = (
                    b"<!doctype html><html><body>"
                    b"<h3>Authorisation received. You may close this browser tab.</h3>"
                    b"</body></html>"
                )
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                parent._done.set()

            def log_message(self, format: str, *args: object) -> None:
                # Never log query strings containing OAuth codes or state.
                return

        self._server = HTTPServer((LOOPBACK_HOST, 0), _Handler)
        self._server.timeout = 0.25
        self._port = int(self._server.server_address[1])
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve_until_done, daemon=True)

    @property
    def port(self) -> int:
        return self._port

    @property
    def redirect_uri(self) -> str:
        return build_loopback_redirect_uri(self._port)

    def _serve_until_done(self) -> None:
        while not self._stop.is_set() and not self._done.is_set():
            self._server.handle_request()

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._done.set()
        self._server.server_close()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    async def wait_for_callback(
        self,
        *,
        timeout_seconds: float,
        cancellation: CancellationToken,
    ) -> dict[str, str]:
        if timeout_seconds <= 0:
            raise _auth_error(
                "WORKFLOW_TIMEOUT",
                "OAuth callback wait timed out.",
                safe_next_action="Retry the local CLI auth command.",
            )
        if cancellation.is_cancelled():
            raise _auth_error(
                "WORKFLOW_TIMEOUT",
                "OAuth sign-in was cancelled before receiving the browser callback.",
                safe_next_action="Re-run the local CLI auth command when ready.",
            )

        cancelled = False
        timed_out = False

        async def _watch_cancel(scope: anyio.CancelScope) -> None:
            nonlocal cancelled
            await cancellation.wait()
            cancelled = True
            self._stop.set()
            scope.cancel()

        async def _wait_event(scope: anyio.CancelScope) -> None:
            nonlocal timed_out
            got = await anyio.to_thread.run_sync(self._done.wait, timeout_seconds)
            if not got:
                timed_out = True
            scope.cancel()

        async with anyio.create_task_group() as tg:
            tg.start_soon(_watch_cancel, tg.cancel_scope)
            tg.start_soon(_wait_event, tg.cancel_scope)

        if cancelled or cancellation.is_cancelled():
            raise _auth_error(
                "WORKFLOW_TIMEOUT",
                "OAuth sign-in was cancelled while waiting for the browser callback.",
                safe_next_action="Re-run the local CLI auth command when ready.",
            )
        if timed_out or self._params is None:
            raise _auth_error(
                "WORKFLOW_TIMEOUT",
                "Timed out waiting for the Google OAuth browser callback.",
                safe_next_action="Complete sign-in in the opened browser window and retry.",
            )
        return dict(self._params)


def open_system_browser(url: str) -> bool:
    """Open the official Google OAuth URL in the operator's local browser."""
    return bool(webbrowser.open(url, new=1, autoraise=True))


class OAuthClient:
    """Installed-app OAuth 2.0 PKCE/state client routed through AccountedHttpExecutor."""

    def __init__(
        self,
        config: OAuthClientConfig,
        executor: AccountedHttpExecutor,
        *,
        clock: Clock | None = None,
    ) -> None:
        if not config.client_id.strip():
            raise ValueError("client_id must be non-empty")
        self._config = config
        self._executor = executor
        self._clock: Clock = clock if clock is not None else SystemClock()

    def build_authorization_request(
        self,
        *,
        scopes: Sequence[str],
        redirect_uri: str,
        include_granted_scopes: bool = False,
    ) -> PendingAuthRequest:
        validated_uri = validate_loopback_redirect_uri(redirect_uri)
        unique_scopes = tuple(dict.fromkeys(s.strip() for s in scopes if s.strip()))
        if not unique_scopes:
            raise _auth_error(
                "INVALID_INPUT",
                "At least one YouTube OAuth scope must be requested.",
                safe_next_action="Request youtube.readonly for reads or youtube.force-ssl for writes.",
            )
        verifier, challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self._config.client_id,
            "redirect_uri": validated_uri,
            "response_type": "code",
            "scope": " ".join(unique_scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true" if include_granted_scopes else "false",
        }
        url = f"{GOOGLE_AUTH_URI}?{urlencode(params)}"
        return PendingAuthRequest(
            authorization_url=url,
            state=state,
            code_verifier=verifier,
            redirect_uri=validated_uri,
            requested_scopes=unique_scopes,
        )

    async def exchange_code(
        self,
        pending: PendingAuthRequest,
        callback_params: Mapping[str, str],
        *,
        deadline: datetime,
        cancellation: CancellationToken,
    ) -> OAuthTokenSet:
        code = verify_oauth_callback(pending, callback_params)
        form: dict[str, str] = {
            "client_id": self._config.client_id,
            "code": code,
            "code_verifier": pending.code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": pending.redirect_uri,
        }
        if self._config.client_secret:
            form["client_secret"] = self._config.client_secret

        resp = await self._executor.execute_oauth(
            "oauth.token",
            form_data=form,
            deadline=deadline,
            cancellation=cancellation,
        )
        return self._parse_token_response(resp.payload, existing_refresh_token=None)

    async def refresh_access_token(
        self,
        refresh_token: str,
        *,
        existing_scopes: Sequence[str],
        deadline: datetime,
        cancellation: CancellationToken,
    ) -> OAuthTokenSet:
        if not refresh_token.strip():
            raise _auth_error(
                "AUTH_REVOKED",
                "No refresh token is available for this account.",
                safe_next_action="Re-authorise the account using the local CLI auth command.",
            )
        form: dict[str, str] = {
            "client_id": self._config.client_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        if self._config.client_secret:
            form["client_secret"] = self._config.client_secret

        try:
            resp = await self._executor.execute_oauth(
                "oauth.token",
                form_data=form,
                deadline=deadline,
                cancellation=cancellation,
            )
        except ContractError as exc:
            if exc.detail.code in {"INVALID_INPUT", "AUTH_REVOKED"}:
                raise _auth_error(
                    "AUTH_REVOKED",
                    "Stored OAuth refresh token was rejected or expired.",
                    safe_next_action="Re-authorise the local account with `yt-intel auth --read`.",
                ) from None
            raise

        return self._parse_token_response(
            resp.payload,
            existing_refresh_token=refresh_token,
            fallback_scopes=existing_scopes,
        )

    async def revoke_token(
        self,
        token: str,
        *,
        deadline: datetime,
        cancellation: CancellationToken,
    ) -> bool:
        if not token.strip():
            return False
        try:
            await self._executor.execute_oauth(
                "oauth.revoke",
                form_data={"token": token},
                deadline=deadline,
                cancellation=cancellation,
            )
            return True
        except ContractError:
            return False

    def _parse_token_response(
        self,
        payload: Mapping[str, object],
        *,
        existing_refresh_token: str | None,
        fallback_scopes: Sequence[str] = (),
    ) -> OAuthTokenSet:
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise _auth_error(
                "PROVIDER_UNAVAILABLE",
                "Google OAuth response did not contain an access token.",
                safe_next_action="Retry the local CLI auth command.",
            )
        expires_in_raw = payload.get("expires_in")
        if (
            isinstance(expires_in_raw, bool)
            or not isinstance(expires_in_raw, int)
            or expires_in_raw <= 0
        ):
            expires_in = 3600
        else:
            expires_in = expires_in_raw

        refresh_raw = payload.get("refresh_token")
        refresh_token = (
            refresh_raw
            if isinstance(refresh_raw, str) and refresh_raw
            else existing_refresh_token
        )
        # Always inspect actual granted scopes from the token response rather than
        # assuming every requested scope was approved.
        granted_scopes = _parse_scopes(payload.get("scope"), fallback=fallback_scopes)
        token_type_raw = payload.get("token_type")
        token_type = (
            token_type_raw
            if isinstance(token_type_raw, str) and token_type_raw
            else "Bearer"
        )
        now = self._clock.now().astimezone(UTC)
        return OAuthTokenSet(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=now + timedelta(seconds=expires_in),
            granted_scopes=granted_scopes,
            token_type=token_type,
        )
