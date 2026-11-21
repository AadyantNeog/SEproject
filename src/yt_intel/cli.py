import argparse
from collections.abc import Sequence

from .bootstrap import create_fixture_server


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yt-intel")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the local MCP server over stdio")
    serve.add_argument("--provider", choices=("fixture",), default="fixture")
    parser.parse_args(argv)

    create_fixture_server().run(transport="stdio")
    return 0
