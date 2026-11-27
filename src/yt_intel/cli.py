from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import anyio

from .auth.account import LocalAccountService
from .auth.oauth import (
    OAuthClient,
    load_oauth_client_config,
    open_system_browser,
)
from .auth.vault import KeyringTokenVault
from .bootstrap import create_fixture_server
from .client_skills import sync_claude_skills
from .contracts.account import AccountStatus, TokenVault
from .contracts.errors import ContractError
from .contracts.workflow import (
    Endpoint,
    QuotaLedger,
    QuotaReservation,
    RequestContext,
    WorkflowPlan,
)
from .infrastructure.database import Database, default_database_path
from .infrastructure.http import AccountedHttpExecutor
from .infrastructure.repositories import SqliteAccountDataRepository
from .providers.youtube import LiveYouTubeReadProvider

_OAUTH_SECRETS_ENV = "YT_INTEL_OAUTH_CLIENT_SECRETS"


class _AuthBootstrapLedger(QuotaLedger):
    """Minimal single-channel-probe ledger used by CLI auth until P2-02 integrates."""

    async def reserve(self, plan: WorkflowPlan) -> QuotaReservation:
        raise NotImplementedError

    async def debit_attempt(
        self, ctx: RequestContext, endpoint: Endpoint, attempt_id: str
    ) -> None:
        return None

    async def release(self, reservation_id: str) -> None:
        raise NotImplementedError


async def run_cli_auth(
    *,
    client_secrets_path: Path,
    enable_writes: bool,
    channel_id: str | None = None,
    timeout_seconds: float = 120.0,
    vault: TokenVault | None = None,
    open_browser: Callable[[str], bool] = open_system_browser,
    database_path: Path | None = None,
    quota_ledger: QuotaLedger | None = None,
) -> AccountStatus:
    """Execute the operator CLI browser OAuth sign-in flow for read or write scopes."""
    config = load_oauth_client_config(client_secrets_path)
    resolved_vault = vault if vault is not None else KeyringTokenVault()
    db_path = (
        database_path if database_path is not None else default_database_path("live")
    )
    db = Database(db_path)
    db.migrate()
    account_data = SqliteAccountDataRepository(db)
    ledger = quota_ledger if quota_ledger is not None else _AuthBootstrapLedger()

    # Create executor first for OAuth endpoints, then bind service as its auth header provider.
    oauth_executor = AccountedHttpExecutor(quota_ledger=ledger)
    oauth_client = OAuthClient(config, oauth_executor)
    service = LocalAccountService(
        installation_id="local-cli",
        mode="live",
        vault=resolved_vault,
        oauth_client=oauth_client,
        account_data=account_data,
    )
    read_executor = AccountedHttpExecutor(
        quota_ledger=ledger,
        auth_headers=service,
    )
    read_provider = LiveYouTubeReadProvider(read_executor)
    try:
        return await service.authorize_via_browser(
            enable_writes=enable_writes,
            read_provider=read_provider,
            reservation_id="cli-auth-channel-probe",
            selected_channel_id=channel_id,
            timeout_seconds=timeout_seconds,
            open_browser=open_browser,
        )
    finally:
        await read_executor.aclose()
        await oauth_executor.aclose()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yt-intel")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the local MCP server over stdio")
    serve.add_argument("--provider", choices=("fixture",), default="fixture")
    serve.add_argument(
        "--project-root", type=Path, help="Checkout for fixture previews and skills"
    )
    serve.add_argument(
        "--fixture-db", type=Path, help="Override the local fixture database path"
    )
    skills = commands.add_parser(
        "sync-claude-skills", help="Copy canonical skills to Claude Code"
    )
    skills.add_argument("--project-root", type=Path, default=Path.cwd())
    skills.add_argument(
        "--check", action="store_true", help="Verify the copies without writing"
    )
    auth = commands.add_parser(
        "auth", help="Authorise a local YouTube account through Google browser OAuth"
    )
    mode_group = auth.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--read",
        action="store_true",
        help="Request explicit read-only scope (youtube.readonly)",
    )
    mode_group.add_argument(
        "--enable-writes",
        action="store_true",
        help="Request explicit read + write scopes (youtube.readonly, youtube.force-ssl)",
    )
    auth.add_argument(
        "--client-secrets",
        type=Path,
        default=None,
        help=f"Path to local Google Desktop OAuth JSON (or set {_OAUTH_SECRETS_ENV})",
    )
    auth.add_argument(
        "--channel-id",
        type=str,
        default=None,
        help="Optional UC... channel ID when the Google account owns multiple channels",
    )
    auth.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Browser callback timeout in seconds (default: 120)",
    )
    args = parser.parse_args(argv)

    if args.command == "auth":
        secrets_path: Path | None = args.client_secrets
        if secrets_path is None:
            env_path = os.environ.get(_OAUTH_SECRETS_ENV, "").strip()
            if env_path:
                secrets_path = Path(env_path)
        if secrets_path is None:
            print(
                f"AUTH_REQUIRED: Supply --client-secrets <path> or set {_OAUTH_SECRETS_ENV}.",
                file=sys.stderr,
            )
            return 2
        try:
            status = anyio.run(
                lambda: run_cli_auth(
                    client_secrets_path=secrets_path,
                    enable_writes=bool(args.enable_writes),
                    channel_id=args.channel_id,
                    timeout_seconds=args.timeout,
                )
            )
        except ContractError as exc:
            print(
                f"{exc.detail.code}: {exc.detail.message} Next: {exc.detail.safe_next_action}",
                file=sys.stderr,
            )
            return 1
        print(
            f"Authorised channel {status.channel_title} ({status.binding.channel_id}) "
            f"with scopes: {', '.join(status.scopes)}"
        )
        return 0

    try:
        root = (
            args.project_root.resolve(strict=True)
            if args.project_root is not None
            else None
        )
        if root is not None and not root.is_dir():
            raise ValueError("project root must be a directory")
        if args.command == "sync-claude-skills":
            assert root is not None
            for name, digest in sync_claude_skills(root, check=args.check).items():
                print(f"{name} {digest}")
            return 0
        server = create_fixture_server(root, fixture_db=args.fixture_db)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    server.run(transport="stdio")
    return 0
