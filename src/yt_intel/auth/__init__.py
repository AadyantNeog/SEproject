"""Installed-app OAuth 2.0 PKCE flow, protected OS token vault, and account lifecycle."""

from .account import AccountRecord, LocalAccountService
from .oauth import (
    GOOGLE_AUTH_URI,
    GOOGLE_REVOKE_URI,
    GOOGLE_TOKEN_URI,
    YOUTUBE_READONLY_SCOPE,
    YOUTUBE_WRITE_SCOPE,
    OAuthClient,
    OAuthClientConfig,
    OAuthTokenSet,
    PendingAuthRequest,
    build_loopback_redirect_uri,
    generate_pkce_pair,
    validate_loopback_redirect_uri,
    verify_oauth_callback,
)
from .vault import (
    DEFAULT_SERVICE_NAME,
    KeyringTokenVault,
    VaultBackendError,
    verify_protected_keyring_backend,
)

__all__ = [
    "AccountRecord",
    "DEFAULT_SERVICE_NAME",
    "GOOGLE_AUTH_URI",
    "GOOGLE_REVOKE_URI",
    "GOOGLE_TOKEN_URI",
    "KeyringTokenVault",
    "LocalAccountService",
    "OAuthClient",
    "OAuthClientConfig",
    "OAuthTokenSet",
    "PendingAuthRequest",
    "VaultBackendError",
    "YOUTUBE_READONLY_SCOPE",
    "YOUTUBE_WRITE_SCOPE",
    "build_loopback_redirect_uri",
    "generate_pkce_pair",
    "validate_loopback_redirect_uri",
    "verify_oauth_callback",
    "verify_protected_keyring_backend",
]
