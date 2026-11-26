"""Check local Codex MCP interoperability and optionally observe manual dismissal."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
SERVER = "yt-intel-fixture"
LAUNCHER = ROOT / "scripts" / "show_fixture_approval.py"
DISMISSED = "Fixture launcher exit code 0. Dialog rejected or closed. No grant issued."


def serve() -> None:
    from mcp_types import ToolAnnotations

    from yt_intel.mcp.server import build_fixture_server

    server = build_fixture_server(ROOT)

    @server.tool(annotations=ToolAnnotations(open_world_hint=False))
    async def observe_fixture_dismissal() -> str:
        """Open a synthetic proposal using the local native dialog."""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(LAUNCHER),
            cwd=ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await process.communicate()
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        detail = (stdout or stderr).decode(errors="replace").strip()
        return f"Fixture launcher exit code {process.returncode}. {detail}"

    server.run(transport="stdio")


async def check(codex: str, dialog: bool, state: str) -> None:
    if dialog and not LAUNCHER.is_file():
        raise SystemExit("The native fixture launcher from P2-03 is required.")
    args = (
        [str(Path(__file__).resolve()), "--serve"]
        if dialog
        else [
            "-m",
            "yt_intel",
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(ROOT),
        ]
    )
    python_path = str(ROOT / "src")
    server_config = (
        "mcp_servers={"
        f"{SERVER}={{command={json.dumps(sys.executable)},args={json.dumps(args)},"
        f"cwd={json.dumps(str(ROOT))},env={{PYTHONPATH={json.dumps(python_path)}}},"
        "startup_timeout_sec=20,tool_timeout_sec=180,required=true}}"
    )
    process = await asyncio.create_subprocess_exec(
        codex,
        "app-server",
        "--stdio",
        "-c",
        server_config,
        "-c",
        "sqlite_home=" + json.dumps(state),
        "-c",
        "log_dir=" + json.dumps(state),
        "--disable",
        "shell_tool",
        "--disable",
        "computer_use",
        "--disable",
        "apps",
        "--disable",
        "plugins",
        "--disable",
        "shell_snapshot",
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": python_path},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None
    request_id = 0

    async def send(message: dict) -> None:
        process.stdin.write((json.dumps({"jsonrpc": "2.0", **message}) + "\n").encode())
        await process.stdin.drain()

    async def call(method: str, params: dict, *, timeout: int = 35) -> dict:
        nonlocal request_id
        request_id += 1
        await send({"id": request_id, "method": method, "params": params})
        try:
            async with asyncio.timeout(timeout):
                while line := await process.stdout.readline():
                    message = json.loads(line)
                    if message.get("id") != request_id or "method" in message:
                        continue
                    if "error" in message:
                        raise RuntimeError(message["error"])
                    return message["result"]
        except TimeoutError as error:
            raise RuntimeError(f"Codex timed out during {method}") from error
        raise RuntimeError(f"Codex closed the connection during {method}")

    try:
        initialized = await call(
            "initialize",
            {
                "clientInfo": {"name": "yt_intel_fixture_check", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        print(initialized["userAgent"], flush=True)
        await send({"method": "initialized"})
        inventory = await call("mcpServerStatus/list", {"serverName": SERVER})
        catalog = next(
            server for server in inventory["data"] if server["name"] == SERVER
        )
        print(
            f"Discovered {len(catalog['tools'])} fixture tools and "
            f"{len(catalog['resources'])} resources.",
            flush=True,
        )
        for uri, expected in (
            ("yt-intel://fixture/previews/create", "Title: Database indexing practice"),
            ("yt-intel://skills/brain-ingest", "name: brain-ingest"),
        ):
            result = await call(
                "mcpServer/resource/read", {"server": SERVER, "uri": uri}
            )
            if not any(
                expected in content.get("text", "") for content in result["contents"]
            ):
                raise RuntimeError(f"Unexpected fixture resource {uri}")
            print(f"Verified {uri}", flush=True)
        if dialog:
            opened = await call(
                "thread/start",
                {
                    "cwd": str(ROOT),
                    "ephemeral": True,
                    "sandbox": "read-only",
                    "approvalPolicy": "never",
                },
            )
            for action in ("Close (X)", "Reject"):
                print(f"Verify the preview and manually choose {action}.", flush=True)
                result = await call(
                    "mcpServer/tool/call",
                    {
                        "threadId": opened["thread"]["id"],
                        "server": SERVER,
                        "tool": "observe_fixture_dismissal",
                        "arguments": {},
                    },
                    timeout=190,
                )
                observed = result.get("structuredContent", {}).get("result")
                if result.get("isError") or observed != DISMISSED:
                    raise RuntimeError(f"{action} returned {result}")
                print(f"{action}: {observed}", flush=True)
    finally:
        process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codex", default="codex.exe", help="Codex app-server executable"
    )
    parser.add_argument(
        "--dialog", action="store_true", help="Run the two manual checks"
    )
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.serve:
        serve()
    else:
        with TemporaryDirectory(prefix="yt-intel-codex-check-") as state:
            asyncio.run(check(options.codex, options.dialog, state))


if __name__ == "__main__":
    main()
