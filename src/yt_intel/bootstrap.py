from pathlib import Path

from mcp.server import MCPServer

from .mcp.resources import HELP_URI as HELP_URI
from .mcp.server import FixtureStatus as FixtureStatus
from .mcp.server import build_fixture_server


def create_fixture_server(project_root: Path | None = None) -> MCPServer[None]:
    return build_fixture_server(project_root)
