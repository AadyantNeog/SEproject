from __future__ import annotations

import base64
from typing import Protocol

import anyio

from yt_intel.contracts.account import TokenVault
from yt_intel.contracts.common import OpaqueId
from yt_intel.contracts.errors import ContractError, ErrorDetail

DEFAULT_SERVICE_NAME = "RandomStuff.YouTubeIntelligence"

_TRUSTED_BACKEND_NAMES = frozenset(
    {
        "WinVaultKeyring",
        "Keyring",  # keyring.backends.macOS.Keyring
        "SecretServiceKeyring",
        "KWalletKeyring",
    }
)
_TRUSTED_BACKEND_MODULES = (
    "keyring.backends.Windows",
    "keyring.backends.macOS",
    "keyring.backends.SecretService",
    "keyring.backends.kwallet",
)
_FORBIDDEN_NAME_MARKERS = ("plain", "fail", "null", "memory", "file", "json")


class KeyringBackendLike(Protocol):
    """Minimal subset of a keyring.backend.KeyringBackend object."""

    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class VaultBackendError(ContractError):
    """Raised when no verified OS-protected credential backend is available."""


def _vault_error(message: str, safe_next_action: str) -> VaultBackendError:
    return VaultBackendError(
        ErrorDetail(
            code="AUTH_REQUIRED",
            message=message,
            retryable=False,
            safe_next_action=safe_next_action,
        )
    )


def _is_backend_protected(backend: object) -> bool:
    cls = type(backend)
    name = cls.__name__
    module = cls.__module__
    lowered = f"{module}.{name}".casefold()

    if any(marker in lowered for marker in _FORBIDDEN_NAME_MARKERS):
        return False

    # Inspect ChainerBackend recursively: all active sub-backends must be protected.
    if name == "ChainerBackend":
        backends = getattr(backend, "backends", None)
        if not backends:
            return False
        return all(_is_backend_protected(child) for child in backends)

    if name in _TRUSTED_BACKEND_NAMES and any(
        module.startswith(prefix) for prefix in _TRUSTED_BACKEND_MODULES
    ):
        return True
    return False


def verify_protected_keyring_backend(backend: object) -> KeyringBackendLike:
    """Verify that a keyring backend is a protected OS credential store.

    Refuses plaintext, null, fail, or unverified backends — never falls back
    silently to plaintext storage.
    """
    if backend is None or not _is_backend_protected(backend):
        backend_name = type(backend).__name__ if backend is not None else "None"
        raise _vault_error(
            f"Credential backend '{backend_name}' is not a verified OS-protected vault.",
            "Enable Windows Credential Manager (or a supported OS keyring) before storing live tokens.",
        )
    return backend  # type: ignore[return-value]


class KeyringTokenVault(TokenVault):
    """OS-protected TokenVault backed by a verified keyring backend."""

    def __init__(
        self,
        *,
        backend: KeyringBackendLike | None = None,
        service_name: str = DEFAULT_SERVICE_NAME,
    ) -> None:
        if not service_name.strip():
            raise ValueError("service_name must be non-empty")
        resolved: object = backend
        if resolved is None:
            try:
                import keyring

                resolved = keyring.get_keyring()
            except Exception as exc:
                raise _vault_error(
                    "OS credential storage is unavailable in this environment.",
                    "Install and enable the OS protected credential backend before authenticating.",
                ) from exc
        self._backend = verify_protected_keyring_backend(resolved)
        self._service_name = service_name

    async def read(self, reference: OpaqueId) -> bytes | None:
        encoded = await anyio.to_thread.run_sync(
            self._backend.get_password, self._service_name, reference
        )
        if encoded is None:
            return None
        try:
            return base64.b64decode(encoded.encode("ascii"), validate=True)
        except Exception as exc:
            raise _vault_error(
                "Stored credential payload could not be decoded from the protected vault.",
                "Disconnect and re-authorise the account using the local CLI auth command.",
            ) from exc

    async def store(self, reference: OpaqueId, sealed_payload: bytes) -> None:
        encoded = base64.b64encode(sealed_payload).decode("ascii")
        await anyio.to_thread.run_sync(
            self._backend.set_password, self._service_name, reference, encoded
        )

    async def delete(self, reference: OpaqueId) -> None:
        def _delete() -> None:
            try:
                self._backend.delete_password(self._service_name, reference)
            except Exception as exc:
                # Missing entry during cleanup is idempotent; other backend errors propagate.
                if type(exc).__name__ == "PasswordDeleteError":
                    return
                raise

        await anyio.to_thread.run_sync(_delete)
