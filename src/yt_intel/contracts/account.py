from typing import Protocol

from .common import AccountBinding, Contract, Label, OpaqueId
from .errors import ErrorDetail


class AccountStatus(Contract):
    binding: AccountBinding
    channel_title: Label
    scopes: tuple[Label, ...]


class DisconnectResult(Contract):
    local_data_removed: bool
    tokens_removed: bool
    revoked: bool
    warnings: tuple[ErrorDetail, ...] = ()


class AccountService(Protocol):
    async def current(self) -> AccountStatus | None: ...
    async def require_binding(
        self, *, required_scopes: tuple[Label, ...] = ()
    ) -> AccountBinding: ...
    async def disconnect(self, binding: AccountBinding) -> DisconnectResult: ...


class TokenVault(Protocol):
    async def read(self, reference: OpaqueId) -> bytes | None: ...
    async def store(self, reference: OpaqueId, sealed_payload: bytes) -> None: ...
    async def delete(self, reference: OpaqueId) -> None: ...
