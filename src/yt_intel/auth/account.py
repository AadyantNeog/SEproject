from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, timedelta

import anyio

from yt_intel.contracts.account import (
    AccountService,
    AccountStatus,
    DisconnectResult,
    TokenVault,
)
from yt_intel.contracts.common import AccountBinding, ChannelId, Label, Mode, OpaqueId
from yt_intel.contracts.errors import ContractError, ErrorCode, ErrorDetail
from yt_intel.contracts.provider import YouTubeReadProvider
from yt_intel.contracts.repositories import AccountDataRepository
from yt_intel.contracts.workflow import CancellationToken, Clock, RequestContext
from yt_intel.infrastructure.clock import SystemClock
from yt_intel.infrastructure.http import AuthHeaderProvider

from .oauth import (
    YOUTUBE_READONLY_SCOPE,
    YOUTUBE_WRITE_SCOPE,
    OAuthClient,
    OAuthTokenSet,
    PendingAuthRequest,
)

_REFRESH_SKEW = timedelta(seconds=60)
_DEFAULT_AUTH_TIMEOUT = timedelta(seconds=30)


class _NeverCancelled:
    def is_cancelled(self) -> bool:
        return False

    async def wait(self) -> None:
        await anyio.sleep_forever()


@dataclass(frozen=True, slots=True)
class AccountRecord:
    """Non-secret active account metadata; tokens live exclusively in TokenVault."""

    binding: AccountBinding
    channel_title: Label
    vault_reference: OpaqueId
    granted_scopes: tuple[Label, ...]


def _account_error(
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


def _vault_ref_for(binding: AccountBinding) -> OpaqueId:
    return f"yt-intel-{binding.mode}-{binding.credential_binding_id}"


class LocalAccountService(AccountService, AuthHeaderProvider):
    """Single-account OAuth lifecycle, scope enforcement, refresh, and disconnect."""

    def __init__(
        self,
        *,
        installation_id: OpaqueId,
        mode: Mode,
        vault: TokenVault,
        oauth_client: OAuthClient,
        account_data: AccountDataRepository,
        clock: Clock | None = None,
        initial_record: AccountRecord | None = None,
    ) -> None:
        self._installation_id = installation_id
        self._mode: Mode = mode
        self._vault = vault
        self._oauth = oauth_client
        self._account_data = account_data
        self._clock: Clock = clock if clock is not None else SystemClock()
        self._record: AccountRecord | None = initial_record
        self._refresh_lock = anyio.Lock()
        self._lifecycle_lock = anyio.Lock()
        self._disconnecting = False

    @property
    def active_record(self) -> AccountRecord | None:
        return self._record

    async def current(self) -> AccountStatus | None:
        if self._record is None or self._disconnecting:
            return None
        return AccountStatus(
            binding=self._record.binding,
            channel_title=self._record.channel_title,
            scopes=self._record.granted_scopes,
        )

    async def require_binding(
        self, *, required_scopes: tuple[Label, ...] = ()
    ) -> AccountBinding:
        if self._disconnecting or self._record is None:
            raise _account_error(
                "AUTH_REQUIRED",
                "No authorised YouTube account is connected.",
                safe_next_action="Run `yt-intel auth --read` in your local terminal to connect an account.",
            )
        missing = [
            scope
            for scope in required_scopes
            if scope not in self._record.granted_scopes
        ]
        if missing:
            needs_write = YOUTUBE_WRITE_SCOPE in missing
            cmd = (
                "yt-intel auth --enable-writes"
                if needs_write
                else "yt-intel auth --read"
            )
            raise _account_error(
                "SCOPE_REQUIRED",
                "Authorised account is missing required YouTube OAuth scope.",
                safe_next_action=f"Grant the required scope locally with `{cmd}`.",
            )
        return self._record.binding

    async def complete_authorization(
        self,
        pending: PendingAuthRequest,
        callback_params: Mapping[str, str],
        *,
        read_provider: YouTubeReadProvider,
        reservation_id: OpaqueId,
        required_scopes: Sequence[str] = (YOUTUBE_READONLY_SCOPE,),
        selected_channel_id: ChannelId | None = None,
        require_same_channel: bool = False,
        cancellation: CancellationToken | None = None,
    ) -> AccountStatus:
        """Complete PKCE exchange, inspect granted scopes, bind channel, and store tokens."""
        async with self._lifecycle_lock:
            if self._disconnecting:
                raise _account_error(
                    "OPERATION_CONFLICT",
                    "Account disconnect is in progress.",
                    safe_next_action="Wait for disconnect to finish before authenticating.",
                )
            cancel = cancellation if cancellation is not None else _NeverCancelled()
            now = self._clock.now().astimezone(UTC)
            deadline = now + _DEFAULT_AUTH_TIMEOUT

            tokens = await self._oauth.exchange_code(
                pending,
                callback_params,
                deadline=deadline,
                cancellation=cancel,
            )

            missing = [
                scope for scope in required_scopes if scope not in tokens.granted_scopes
            ]
            if missing:
                # Best-effort revoke unused token when required scope was not granted.
                await self._oauth.revoke_token(
                    tokens.refresh_token or tokens.access_token,
                    deadline=deadline,
                    cancellation=cancel,
                )
                raise _account_error(
                    "SCOPE_REQUIRED",
                    "Google sign-in did not grant all required YouTube scopes.",
                    safe_next_action="Re-run the local CLI auth command and approve the required scope.",
                )

            existing = self._record
            cred_id = (
                existing.binding.credential_binding_id
                if require_same_channel and existing is not None
                else f"cred-{uuid.uuid4().hex[:16]}"
            )
            probe_cred_id = f"probe-{uuid.uuid4().hex[:16]}"
            probe_binding = AccountBinding(
                installation_id=self._installation_id,
                credential_binding_id=probe_cred_id,
                channel_id=(
                    existing.binding.channel_id
                    if existing is not None
                    else "UC0000000000000000000000"
                ),
                mode=self._mode,
            )
            probe_vault_ref = _vault_ref_for(probe_binding)
            await self._vault.store(probe_vault_ref, tokens.to_vault_bytes())

            previous_record = self._record
            self._record = AccountRecord(
                binding=probe_binding,
                channel_title="(resolving channel)",
                vault_reference=probe_vault_ref,
                granted_scopes=tokens.granted_scopes,
            )
            try:
                probe_ctx = RequestContext(
                    request_id=f"auth-channel-{uuid.uuid4().hex[:12]}",
                    binding=probe_binding,
                    reservation_id=reservation_id,
                    deadline=self._clock.now().astimezone(UTC) + _DEFAULT_AUTH_TIMEOUT,
                    cancellation=cancel,
                )
                channels = await read_provider.get_my_channels(probe_ctx)

                if not channels:
                    raise _account_error(
                        "CHANNEL_REQUIRED",
                        "This Google account does not have an active YouTube channel.",
                        safe_next_action="Create a YouTube channel for this account, then re-run `yt-intel auth --read`.",
                    )

                chosen = None
                if selected_channel_id is not None:
                    for ch in channels:
                        if ch.channel_id == selected_channel_id:
                            chosen = ch
                            break
                    if chosen is None:
                        raise _account_error(
                            "CHANNEL_REQUIRED",
                            "Selected YouTube channel was not found on this Google account.",
                            safe_next_action="Choose one of the channels returned for your authorised account.",
                        )
                elif len(channels) == 1:
                    chosen = channels[0]
                else:
                    raise _account_error(
                        "CLARIFICATION_REQUIRED",
                        f"Multiple YouTube channels ({len(channels)}) found; operator selection is required.",
                        safe_next_action="Re-run local CLI auth with the specific channel ID you want to bind.",
                    )

                if (
                    require_same_channel
                    and previous_record is not None
                    and chosen.channel_id != previous_record.binding.channel_id
                ):
                    await self._oauth.revoke_token(
                        tokens.refresh_token or tokens.access_token,
                        deadline=self._clock.now().astimezone(UTC)
                        + _DEFAULT_AUTH_TIMEOUT,
                        cancellation=cancel,
                    )
                    raise _account_error(
                        "ACCOUNT_MISMATCH",
                        "Scope upgrade signed into a different YouTube channel than the active account.",
                        safe_next_action="Authorise the same YouTube channel or disconnect before switching accounts.",
                    )

                final_binding = AccountBinding(
                    installation_id=self._installation_id,
                    credential_binding_id=cred_id,
                    channel_id=chosen.channel_id,
                    mode=self._mode,
                )
                final_vault_ref = _vault_ref_for(final_binding)
                await self._vault.store(final_vault_ref, tokens.to_vault_bytes())
                final_record = AccountRecord(
                    binding=final_binding,
                    channel_title=chosen.title,
                    vault_reference=final_vault_ref,
                    granted_scopes=tokens.granted_scopes,
                )
                self._record = final_record
                return AccountStatus(
                    binding=final_record.binding,
                    channel_title=final_record.channel_title,
                    scopes=final_record.granted_scopes,
                )
            except Exception:
                self._record = previous_record
                raise
            finally:
                await self._vault.delete(probe_vault_ref)

    async def get_headers(self, binding: AccountBinding) -> Mapping[str, str]:
        """AuthHeaderProvider implementation: returns Bearer header, refreshing if needed."""
        record = self._record
        if self._disconnecting or record is None:
            raise _account_error(
                "AUTH_REQUIRED",
                "No authorised account is available for provider requests.",
                safe_next_action="Run `yt-intel auth --read` locally.",
            )
        if record.binding != binding:
            raise _account_error(
                "ACCOUNT_MISMATCH",
                "Requested account binding does not match the active authorised account.",
                safe_next_action="Use objects belonging to the currently connected account.",
            )

        tokens = await self._load_tokens(record)
        now = self._clock.now().astimezone(UTC)
        if tokens.expires_at > now + _REFRESH_SKEW:
            return {"Authorization": f"{tokens.token_type} {tokens.access_token}"}

        # Serialize concurrent refresh calls so only one refresh hits Google OAuth.
        async with self._refresh_lock:
            current_record = self._record
            if (
                self._disconnecting
                or current_record is None
                or current_record.binding != binding
            ):
                raise _account_error(
                    "AUTH_REQUIRED",
                    "Account was disconnected while refreshing credentials.",
                    safe_next_action="Re-authorise the account locally if needed.",
                )
            fresh_tokens = await self._load_tokens(current_record)
            now = self._clock.now().astimezone(UTC)
            if fresh_tokens.expires_at > now + _REFRESH_SKEW:
                return {
                    "Authorization": f"{fresh_tokens.token_type} {fresh_tokens.access_token}"
                }
            if not fresh_tokens.refresh_token:
                raise _account_error(
                    "AUTH_REVOKED",
                    "Access token expired and no refresh token is stored.",
                    safe_next_action="Re-authorise the account locally with `yt-intel auth --read`.",
                )
            refreshed = await self._oauth.refresh_access_token(
                fresh_tokens.refresh_token,
                existing_scopes=fresh_tokens.granted_scopes,
                deadline=now + _DEFAULT_AUTH_TIMEOUT,
                cancellation=_NeverCancelled(),
            )
            await self._vault.store(
                current_record.vault_reference, refreshed.to_vault_bytes()
            )
            if refreshed.granted_scopes != current_record.granted_scopes:
                self._record = AccountRecord(
                    binding=current_record.binding,
                    channel_title=current_record.channel_title,
                    vault_reference=current_record.vault_reference,
                    granted_scopes=refreshed.granted_scopes,
                )
            return {"Authorization": f"{refreshed.token_type} {refreshed.access_token}"}

    async def _load_tokens(self, record: AccountRecord) -> OAuthTokenSet:
        raw = await self._vault.read(record.vault_reference)
        if raw is None:
            raise _account_error(
                "AUTH_REVOKED",
                "Stored credentials are missing from the protected OS vault.",
                safe_next_action="Re-authorise the account locally with `yt-intel auth --read`.",
            )
        try:
            return OAuthTokenSet.from_vault_bytes(raw)
        except Exception:
            raise _account_error(
                "AUTH_REVOKED",
                "Stored credentials in the protected vault are corrupted.",
                safe_next_action="Disconnect and re-authorise the account locally.",
            ) from None

    async def disconnect(self, binding: AccountBinding) -> DisconnectResult:
        """Disable new workflows, revoke token best-effort, and delete vault + SQLite data."""
        async with self._lifecycle_lock:
            record = self._record
            if record is None:
                raise _account_error(
                    "AUTH_REQUIRED",
                    "No authorised account is currently connected.",
                    safe_next_action="Nothing to disconnect.",
                )
            if record.binding != binding:
                raise _account_error(
                    "ACCOUNT_MISMATCH",
                    "Cannot disconnect a foreign or inactive account binding.",
                    safe_next_action="Inspect `get_account_status` for the active account.",
                )

            self._disconnecting = True
            warnings: list[ErrorDetail] = []
            revoked = False
            tokens_removed = False
            local_data_removed = False

            try:
                now = self._clock.now().astimezone(UTC)
                deadline = now + _DEFAULT_AUTH_TIMEOUT
                cancel = _NeverCancelled()

                # 1. Best-effort remote token revocation.
                token_to_revoke: str | None = None
                try:
                    raw = await self._vault.read(record.vault_reference)
                    if raw is not None:
                        parsed = OAuthTokenSet.from_vault_bytes(raw)
                        token_to_revoke = parsed.refresh_token or parsed.access_token
                except Exception:
                    token_to_revoke = None

                if token_to_revoke is not None:
                    revoked = await self._oauth.revoke_token(
                        token_to_revoke, deadline=deadline, cancellation=cancel
                    )
                    if not revoked:
                        warnings.append(
                            ErrorDetail(
                                code="PROVIDER_UNAVAILABLE",
                                message="Best-effort Google token revocation did not succeed.",
                                retryable=True,
                                safe_next_action="You may also revoke access from your Google Account security settings.",
                            )
                        )

                # 2. Delete tokens from protected OS vault.
                try:
                    await self._vault.delete(record.vault_reference)
                    tokens_removed = True
                except Exception:
                    warnings.append(
                        ErrorDetail(
                            code="LOCAL_DELETION_FAILED",
                            message="Failed to remove credentials from the protected OS vault.",
                            retryable=True,
                            safe_next_action="Remove the credential entry from Windows Credential Manager and retry disconnect.",
                        )
                    )

                # 3. Delete account-bound SQLite records via Paul's repository
                # (project-level quota accounting is preserved by P2-01).
                try:
                    await self._account_data.delete_account(binding)
                    local_data_removed = True
                except Exception:
                    warnings.append(
                        ErrorDetail(
                            code="LOCAL_DELETION_FAILED",
                            message="Failed to delete local account records from SQLite storage.",
                            retryable=True,
                            safe_next_action="Close any process holding the runtime database and retry disconnect.",
                        )
                    )

                if tokens_removed and local_data_removed:
                    self._record = None
            finally:
                self._disconnecting = False

            return DisconnectResult(
                local_data_removed=local_data_removed,
                tokens_removed=tokens_removed,
                revoked=revoked,
                warnings=tuple(warnings),
            )
