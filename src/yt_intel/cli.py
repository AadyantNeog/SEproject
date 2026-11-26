import argparse
from collections.abc import Sequence
from pathlib import Path

from .bootstrap import create_fixture_server
from .client_skills import sync_claude_skills


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
    args = parser.parse_args(argv)

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
