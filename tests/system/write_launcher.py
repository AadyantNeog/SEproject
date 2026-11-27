"""Shared stdio launcher for P2-08 write and authority acceptance tests.

The launcher runs the real fixture server in a subprocess. It injects only
isolated test seams: a scripted fixture approval adapter in place of the
native dialog, optional extra synthetic candidates, optional untrusted
metadata text, an optional scripted write fault, and an audit of POST
writes and approval prompts. None of these seams exists in the shipped
server, and none can be reached from an MCP tool argument.
"""

import json
import os
import sys
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from yt_intel.infrastructure.database import Database

ROOT = Path(__file__).resolve().parents[2]

LAUNCHER = r"""
import json, os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from yt_intel.contracts.approval import HumanDecision
from yt_intel.mcp.server import build_fixture_server
from yt_intel.providers.fixture import FixtureDataset
from yt_intel.providers.fixture_writes import FixturePlaylistWrites

config = json.loads(os.environ["YT_TEST_WRITE_CONFIG"])
load_catalog = FixtureDataset.from_json_file


def patched_catalog(cls, path):
    dataset = load_catalog(path)
    if path.name != "catalog.json" or "vidIndex001" not in dataset.videos:
        return dataset
    videos = dict(dataset.videos)
    search_pages = dict(dataset.search_pages)
    first_page = dict(search_pages[""])
    hits = list(first_page["items"])
    template = videos["vidIndex001"]
    for index in range(config.get("extra_candidates", 0)):
        video = f"vidMore{index + 1:04d}"
        snippet = dict(template["snippet"])
        if config.get("injected_title"):
            snippet["title"] = config["injected_title"]
        videos[video] = {
            **template,
            "id": video,
            "snippet": snippet,
            "contentDetails": {"duration": "PT5M"},
        }
        hits.append(
            {
                "id": {"videoId": video},
                "snippet": {"channelId": template["snippet"]["channelId"]},
            }
        )
    search_pages[""] = {**first_page, "items": hits}
    return replace(dataset, videos=videos, search_pages=search_pages)


FixtureDataset.from_json_file = classmethod(patched_catalog)

if config.get("fail_at") is not None:
    original_init = FixturePlaylistWrites.__init__

    def with_fault(self, *args, **kwargs):
        original_init(
            self,
            *args,
            fail_at=config["fail_at"],
            fault=config.get("fault", "reject"),
            **kwargs,
        )

    FixturePlaylistWrites.__init__ = with_fault


class ScriptedApproval:
    def __init__(self):
        self.decisions = list(config.get("decisions", ["approve"]))

    async def request_decision(self, ctx, proposal, operation_id, challenge_ref):
        decision = self.decisions.pop(0) if self.decisions else "reject"
        binding, digest, ref = ctx.binding, proposal.digest, proposal.ref
        if decision == "forge_account":
            binding = binding.model_copy(
                update={"channel_id": "UCzzzzzzzzzzzzzzzzzzzzzz"}
            )
            decision = "approve"
        elif decision == "forge_digest":
            digest = "0" * len(digest)
            decision = "approve"
        elif decision == "forge_operation":
            operation_id = "forged-operation"
            decision = "approve"
        with Path(config["approval_audit"]).open("a", encoding="utf-8") as target:
            target.write(
                json.dumps({"proposal": ref.model_dump(), "decision": decision}) + "\n"
            )
        return HumanDecision(
            challenge_ref=challenge_ref,
            response_ref="fixture-response",
            operation_id=operation_id,
            proposal=ref,
            proposal_digest=digest,
            binding=binding,
            observed_at=datetime.now(UTC),
            decision=decision,
        )


dispatch = FixturePlaylistWrites._dispatch


def audit(self, request):
    if request.method == "POST":
        with Path(config["write_audit"]).open("a", encoding="utf-8") as target:
            target.write(request.url.path + "\n")
    return dispatch(self, request)


FixturePlaylistWrites._dispatch = audit

build_fixture_server(
    Path(config["root"]),
    fixture_db=Path(config["state"]),
    creation_approval=ScriptedApproval(),
).run(transport="stdio")
"""


class WriteHarness:
    def __init__(self, tmp_path: Path, **config: Any) -> None:
        self.state = tmp_path / "state.sqlite3"
        self.write_audit = tmp_path / "writes.txt"
        self.approval_audit = tmp_path / "approvals.jsonl"
        self.config = {
            "root": str(ROOT),
            "state": str(self.state),
            "write_audit": str(self.write_audit),
            "approval_audit": str(self.approval_audit),
            **config,
        }

    @asynccontextmanager
    async def client(self) -> AsyncIterator[ClientSession]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", LAUNCHER],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
                "YT_TEST_WRITE_CONFIG": json.dumps(self.config),
            },
        )
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=30) as c:
                await c.initialize()
                yield c

    def writes(self) -> list[str]:
        if not self.write_audit.exists():
            return []
        return self.write_audit.read_text(encoding="utf-8").splitlines()

    def approvals(self) -> list[dict[str, Any]]:
        if not self.approval_audit.exists():
            return []
        lines = self.approval_audit.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def attempts(self) -> list[str]:
        with Database(self.state).transaction(immediate=False) as connection:
            rows = connection.execute("SELECT endpoint FROM quota_attempts").fetchall()
        return [row["endpoint"] for row in rows]


async def call(client: ClientSession, tool: str, args: Mapping[str, object]) -> Any:
    result = await client.call_tool(tool, dict(args))
    assert result.structured_content is not None, result.content
    return result


async def prepared(
    client: ClientSession, *, limit: int = 1, total_seconds: int = 1800
) -> dict[str, Any]:
    """Run the composed workflow to an exact stored preview and a prepared operation."""
    workflow = await call(
        client, "begin_workflow", {"kind": "video_to_playlist", "video": "vidIndex002"}
    )
    assert not workflow.is_error, workflow.content
    workflow_id = workflow.structured_content["data"]["workflow_id"]
    seed_args = {"workflow_id": workflow_id, "video": "vidIndex002"}
    seed = await call(client, "get_video", seed_args)
    assert not seed.is_error, seed.content
    discovery = await call(client, "find_similar_videos", {**seed_args, "limit": limit})
    assert not discovery.is_error, discovery.content
    preview = await call(
        client,
        "propose_playlist",
        {
            "workflow_id": workflow_id,
            "candidate_set_id": discovery.structured_content["candidate_set_id"],
            "title": "Indexing from discovery",
            "topic": "database indexing",
            "total_seconds": total_seconds,
            "max_video_seconds": 1200,
            "language": "en",
        },
    )
    assert not preview.is_error, preview.content
    proposal = preview.structured_content["data"]
    approval_args = {**proposal["ref"], "workflow_id": workflow_id}
    prep = await call(client, "prepare_creation", approval_args)
    assert not prep.is_error, prep.content
    return {
        "workflow_id": workflow_id,
        "proposal": proposal,
        "preview_text": preview.content[0].text,
        "creation_args": {
            **approval_args,
            "operation_id": prep.structured_content["data"]["operation_id"],
        },
    }
