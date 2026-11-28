"""Live serve mode over MCP stdio, offline.

The server under test is the real live composition: the saved account
record, LocalAccountService with a vault, OAuth and API executors with
bearer auth, the SQLite quota ledger and the official read provider. Only
the edges are replaced. The vault is in memory, and Google is an httpx mock
that serves the API-shaped synthetic library catalogue. Nothing reaches the
network.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from yt_intel.infrastructure.database import Database

ROOT = Path(__file__).resolve().parents[2]
CHANNEL = "UClivetest00000000000001"

LAUNCHER = r"""
import json, os
from datetime import UTC, datetime, timedelta
from pathlib import Path
import httpx
from yt_intel.auth.account import AccountRecord, JsonAccountStateStore
from yt_intel.auth.oauth import OAuthTokenSet, YOUTUBE_READONLY_SCOPE
from yt_intel.contracts.common import AccountBinding
from yt_intel.mcp.live import build_live_runtime, build_live_server
from yt_intel.providers.fixture import FixtureDataset, FixtureYouTubeProvider

config = json.loads(os.environ["YT_TEST_LIVE_CONFIG"])
root = Path(config["root"])
binding = AccountBinding(
    installation_id="local-cli", credential_binding_id="live-test-binding",
    channel_id=config["channel"], mode="live",
)

class MemoryVault:
    def __init__(self):
        self.data = {}
    async def read(self, reference):
        return self.data.get(reference)
    async def store(self, reference, payload):
        self.data[reference] = payload
    async def delete(self, reference):
        self.data.pop(reference, None)

vault = MemoryVault()
reference = f"yt-intel-live-{binding.credential_binding_id}"
vault.data[reference] = OAuthTokenSet(
    access_token="ya29.fake", refresh_token="1//fake",
    expires_at=datetime.now(UTC) + timedelta(hours=1),
    granted_scopes=(YOUTUBE_READONLY_SCOPE,),
).to_vault_bytes()
state = Path(config["state"])
if config["connected"]:
    JsonAccountStateStore(state).save(AccountRecord(
        binding=binding, channel_title="Live Test Channel", vault_reference=reference,
        granted_scopes=(YOUTUBE_READONLY_SCOPE,),
    ))

dataset = FixtureDataset.from_json_file(root / config["catalog"])

class Ledger:
    async def reserve(self, plan): raise AssertionError("unused")
    async def debit_attempt(self, ctx, endpoint, attempt_id): raise AssertionError("unused")
    async def release(self, reservation_id): raise AssertionError("unused")

google = FixtureYouTubeProvider(dataset, quota_ledger=Ledger())
audit = Path(config["audit"])

def api(request):
    with audit.open("a", encoding="utf-8") as target:
        target.write(json.dumps({
            "path": request.url.path,
            "method": request.method,
            "auth": request.headers.get("authorization", ""),
        }) + "\n")
    return google._handle_request(request)

def oauth(request):
    if request.url.path == "/revoke":
        return httpx.Response(200, json={})
    return httpx.Response(400, json={"error": "invalid_grant"})

runtime = build_live_runtime(
    project_root=root, database_path=Path(config["db"]),
    client_secrets_path=Path(config["secrets"]), account_state_path=state,
    vault=vault, policy_path=Path(config["policy"]),
    oauth_transport=httpx.MockTransport(oauth), api_transport=httpx.MockTransport(api),
)
build_live_server(runtime).run(transport="stdio")
"""


class LiveHarness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        connected: bool = True,
        resolved: bool = False,
        catalog: str = "tests/fixtures/libraries/library_catalog.json",
    ):
        self.db = tmp_path / "live.sqlite3"
        self.audit = tmp_path / "google.jsonl"
        secrets = tmp_path / "client_secret.json"
        secrets.write_text(json.dumps({"installed": {"client_id": "cid"}}), "utf-8")
        self.policy = policy = tmp_path / "d02.json"
        policy.write_text(
            json.dumps(
                {
                    "state": "resolved",
                    "evidence_url": "https://example.edu/d02",
                    "recorded_by": "Test operator",
                }
                if resolved
                else {"state": "unresolved", "evidence_url": None, "recorded_by": None}
            ),
            "utf-8",
        )
        self.config = {
            "root": str(ROOT),
            "db": str(self.db),
            "state": str(tmp_path / "account-live.json"),
            "secrets": str(secrets),
            "policy": str(policy),
            "audit": str(self.audit),
            "channel": CHANNEL,
            "connected": connected,
            "catalog": catalog,
        }

    def google_calls(self) -> list[dict[str, str]]:
        if not self.audit.exists():
            return []
        lines = self.audit.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    async def session(self, steps: Any) -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", LAUNCHER],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
                "YT_TEST_LIVE_CONFIG": json.dumps(self.config),
            },
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=30) as c:
                await c.initialize()
                await steps(c)


def _content(result: Any) -> dict[str, Any]:
    assert result.structured_content is not None, result.content
    assert result.structured_content["mode"] == "live"
    return result.structured_content


def test_live_reads_use_the_saved_account_bearer_auth_and_ledger(
    tmp_path: Path,
) -> None:
    harness = LiveHarness(tmp_path)

    async def steps(client: ClientSession) -> None:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        assert {
            "live_status",
            "get_video",
            "get_library",
            "find_similar_videos",
        } <= tools
        assert not tools & {"create_playlist", "resume_operation", "fixture_status"}

        status = _content(await client.call_tool("get_account_status", {}))
        assert status["data"]["binding"]["channel_id"] == CHANNEL
        assert status["data"]["binding"]["mode"] == "live"

        video = await client.call_tool("get_video", {"video": "libVid00001"})
        assert not video.is_error, video.content
        data = _content(video)["data"]
        assert (data["video_id"], data["duration_seconds"]) == ("libVid00001", 600)
        assert "Mode: live" in video.content[0].text

        library = await client.call_tool("get_library", {"sources": ["likes"]})
        assert not library.is_error, library.content
        summary = _content(library)["data"]
        assert summary["likes_count"] == 2
        assert summary["sources"]["likes"]["state"] == "retrieved"

        bad = await client.call_tool(
            "get_video", {"video": "https://example.com/watch?v=libVid00001"}
        )
        assert bad.is_error
        assert _content(bad)["error"]["code"] == "UNSUPPORTED_IDENTIFIER"

    anyio.run(harness.session, steps)
    calls = harness.google_calls()
    assert calls and all(call["auth"] == "Bearer ya29.fake" for call in calls)
    assert {call["path"] for call in calls} == {"/youtube/v3/videos"}
    with Database(harness.db).transaction(immediate=False) as connection:
        attempts = connection.execute(
            "SELECT quota_attempts.endpoint, quota_reservations.project_id "
            "FROM quota_attempts JOIN quota_reservations USING (reservation_id)"
        ).fetchall()
    assert len(attempts) == len(calls)
    assert {row["project_id"] for row in attempts} == {"default-project"}


DERIVED_CALLS = [
    ("find_similar_videos", {"video": "libVid00001"}),
    ("find_similar_channels", {"channel": "@SystemsStudyLab"}),
    ("recommend_videos", {"language": "en", "snapshot_id": "snap-1"}),
    ("analyse_library", {}),
    ("begin_workflow", {"kind": "video_to_playlist", "video": "libVid00001"}),
    ("propose_playlist", {"title": "x", "topic": "database indexing"}),
]
PLAN_FIELDS = {
    "title": "Indexing from live discovery",
    "topic": "database indexing",
    "total_seconds": 1800,
    "max_video_seconds": 1200,
    "language": "en",
}
READ_INDEX = "tests/fixtures/youtube_reads/catalog.json"


def _ledger_rows(db: Path) -> tuple[list[Any], list[Any]]:
    with Database(db).transaction(immediate=False) as connection:
        attempts = connection.execute(
            "SELECT quota_attempts.endpoint, quota_reservations.project_id "
            "FROM quota_attempts JOIN quota_reservations USING (reservation_id)"
        ).fetchall()
        reservations = connection.execute(
            "SELECT project_id, released FROM quota_reservations"
        ).fetchall()
    return attempts, reservations


def test_derived_tools_refuse_with_zero_provider_calls_until_d02_is_resolved(
    tmp_path: Path,
) -> None:
    harness = LiveHarness(tmp_path, resolved=False)

    async def steps(client: ClientSession) -> None:
        status = _content(await client.call_tool("live_status", {}))["data"]
        assert status["d02_resolved"] is False
        assert status["account_connected"] is True
        assert "find_similar_videos" in status["blocked_tools"]
        for tool, args in DERIVED_CALLS:
            result = await client.call_tool(tool, args)
            assert result.is_error
            assert _content(result)["error"]["code"] == "POLICY_BLOCKED", tool

    anyio.run(harness.session, steps)
    assert harness.google_calls() == []


def test_resolved_d02_runs_live_discovery_and_a_preview_only_proposal(
    tmp_path: Path,
) -> None:
    harness = LiveHarness(tmp_path, resolved=True, catalog=READ_INDEX)

    async def steps(client: ClientSession) -> None:
        status = _content(await client.call_tool("live_status", {}))["data"]
        assert status["d02_resolved"] is True
        assert status["blocked_tools"] == ["begin_workflow"]
        assert "propose_playlist" in status["available_tools"]

        found = await client.call_tool(
            "find_similar_videos", {"video": "vidIndex002", "limit": 1}
        )
        assert not found.is_error, found.content
        discovery = _content(found)
        assert discovery["data"][0]["video"]["video_id"] == "vidIndex001"
        candidate_set_id = discovery["candidate_set_id"]
        assert candidate_set_id.startswith("discovery-")
        assert "Mode: live" in found.content[0].text

        channels = await client.call_tool(
            "find_similar_channels", {"channel": "@SystemsStudyLab"}
        )
        assert not channels.is_error, channels.content
        assert _content(channels)["status"] in {"ok", "empty"}

        missing = await client.call_tool("propose_playlist", PLAN_FIELDS)
        assert _content(missing)["error"]["code"] == "CONTENT_UNAVAILABLE"
        workflow = await client.call_tool(
            "find_similar_videos", {"video": "vidIndex002", "workflow_id": "wf-1"}
        )
        assert _content(workflow)["error"]["code"] == "INVALID_INPUT"
        begin = await client.call_tool(
            "begin_workflow", {"kind": "video_to_playlist", "video": "vidIndex002"}
        )
        assert _content(begin)["error"]["code"] == "PROVIDER_UNAVAILABLE"

        preview = await client.call_tool(
            "propose_playlist", {**PLAN_FIELDS, "candidate_set_id": candidate_set_id}
        )
        assert not preview.is_error, preview.content
        envelope = _content(preview)
        proposal = envelope["data"]
        assert proposal["binding"]["mode"] == "live"
        assert proposal["binding"]["channel_id"] == CHANNEL
        assert proposal["destination_channel_title"] == "Live Test Channel"
        assert proposal["candidate_set_id"] == candidate_set_id
        assert [item["video_id"] for item in proposal["items"]] == ["vidIndex001"]
        assert any("Preview only" in warning for warning in envelope["warnings"])
        assert "nothing is written to YouTube" in preview.content[0].text

    anyio.run(harness.session, steps)
    calls = harness.google_calls()
    assert calls and all(call["auth"] == "Bearer ya29.fake" for call in calls)
    assert "/youtube/v3/search" in {call["path"] for call in calls}
    assert {call["method"] for call in calls} == {"GET"}
    attempts, reservations = _ledger_rows(harness.db)
    assert len(attempts) == len(calls)
    assert {row["project_id"] for row in attempts} == {"default-project"}
    assert reservations and all(row["released"] == 1 for row in reservations)


def test_resolved_d02_runs_live_recommendations_and_analysis(tmp_path: Path) -> None:
    harness = LiveHarness(tmp_path, resolved=True)

    async def steps(client: ClientSession) -> None:
        unknown = await client.call_tool("recommend_videos", {"language": "en"})
        assert _content(unknown)["error"]["code"] == "CONTENT_UNAVAILABLE"

        library = await client.call_tool("get_library", {})
        assert not library.is_error, library.content
        snapshot_id = _content(library)["data"]["snapshot_id"]

        ranked = await client.call_tool(
            "recommend_videos", {"snapshot_id": snapshot_id, "language": "en"}
        )
        assert not ranked.is_error, ranked.content
        assert _content(ranked)["status"] in {"ok", "empty"}
        assert "Mode: live" in ranked.content[0].text

        report = await client.call_tool("analyse_library", {"snapshot_id": snapshot_id})
        assert not report.is_error, report.content
        assert _content(report)["data"]["snapshot_id"] == snapshot_id
        assert "Mode: live" in report.content[0].text

    anyio.run(harness.session, steps)
    attempts, reservations = _ledger_rows(harness.db)
    assert len(attempts) == len(harness.google_calls())
    assert reservations and all(row["released"] == 1 for row in reservations)


def test_reverting_the_d02_record_closes_the_gate_without_a_restart(
    tmp_path: Path,
) -> None:
    harness = LiveHarness(tmp_path, resolved=True, catalog=READ_INDEX)

    async def steps(client: ClientSession) -> None:
        opened = await client.call_tool("find_similar_videos", {"video": "vidIndex002"})
        assert not opened.is_error, opened.content
        before = len(harness.google_calls())
        harness.policy.write_text(
            json.dumps(
                {"state": "unresolved", "evidence_url": None, "recorded_by": None}
            ),
            "utf-8",
        )
        for tool, args in DERIVED_CALLS:
            closed = await client.call_tool(tool, args)
            assert _content(closed)["error"]["code"] == "POLICY_BLOCKED", tool
        assert len(harness.google_calls()) == before

    anyio.run(harness.session, steps)


def test_live_mode_without_an_account_requires_auth(tmp_path: Path) -> None:
    harness = LiveHarness(tmp_path, connected=False)

    async def steps(client: ClientSession) -> None:
        status = _content(await client.call_tool("get_account_status", {}))
        assert status["status"] == "empty" and status["data"] is None
        for tool, args in (
            ("get_video", {"video": "libVid00001"}),
            ("get_library", {}),
            ("disconnect_account", {}),
        ):
            result = await client.call_tool(tool, args)
            assert result.is_error
            assert _content(result)["error"]["code"] == "AUTH_REQUIRED"

    anyio.run(harness.session, steps)
    assert harness.google_calls() == []


def test_live_disconnect_revokes_and_blocks_further_reads(tmp_path: Path) -> None:
    harness = LiveHarness(tmp_path)

    async def steps(client: ClientSession) -> None:
        result = _content(await client.call_tool("disconnect_account", {}))["data"]
        assert (result["revoked"], result["tokens_removed"]) == (True, True)
        assert result["local_data_removed"] is True
        after = await client.call_tool("get_video", {"video": "libVid00001"})
        assert _content(after)["error"]["code"] == "AUTH_REQUIRED"

    anyio.run(harness.session, steps)
    assert harness.google_calls() == []


def test_live_serve_refuses_to_start_without_an_oauth_client(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from yt_intel.cli import main

    monkeypatch.delenv("YT_INTEL_OAUTH_CLIENT_SECRETS", raising=False)
    assert main(["serve", "--provider", "live", "--project-root", str(ROOT)]) == 2
    assert "AUTH_REQUIRED" in capsys.readouterr().err
