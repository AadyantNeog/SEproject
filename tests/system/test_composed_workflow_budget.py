import sys
from pathlib import Path

import anyio
import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from yt_intel.contracts.errors import ContractError
from yt_intel.infrastructure.database import Database
from yt_intel.infrastructure.http import AccountedHttpExecutor
from yt_intel.mcp.workflows import fixture_workflow_runtime


class Cancellation:
    def __init__(self, *, cancelled=False):
        self._event = anyio.Event()
        if cancelled:
            self._event.set()

    def is_cancelled(self):
        return self._event.is_set()

    async def wait(self):
        await self._event.wait()


@pytest.mark.anyio
async def test_seed_discovery_and_preview_share_one_reservation():
    runtime = fixture_workflow_runtime(Path(__file__).resolve().parents[2])
    assert runtime is not None
    service = runtime.service
    seed = "dQw4w9WgXcQ"
    session = await service.begin_video_to_playlist(
        runtime.binding, "fixture-project", seed
    )
    stage_args = {
        "binding": runtime.binding,
        "request_id": "fixture-request",
        "cancellation": Cancellation(),
    }
    sent = []

    def handler(request):
        sent.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"items": []})

    async with AccountedHttpExecutor(
        quota_ledger=runtime.ledger, transport=httpx.MockTransport(handler)
    ) as executor:
        with pytest.raises(ContractError, match="out of order"):
            async with service.stage(
                session.workflow_id, "find_similar_videos", video=seed, **stage_args
            ):
                pytest.fail("discovery ran before seed")
        with pytest.raises(ContractError, match="another account"):
            foreign_args = stage_args | {
                "binding": runtime.binding.model_copy(
                    update={"credential_binding_id": "other"}
                )
            }
            async with service.stage(
                session.workflow_id, "get_video", video=seed, **foreign_args
            ):
                pytest.fail("foreign account used the reservation")
        with pytest.raises(ContractError, match="does not match"):
            async with service.stage(
                session.workflow_id, "get_video", video="AAAAAAAAAAA", **stage_args
            ):
                pytest.fail("a different seed was accepted")
        async with service.stage(
            session.workflow_id, "get_video", video=seed, **stage_args
        ) as access:
            assert access.context.reservation_id == session.reservation_id
            with pytest.raises(ContractError, match="busy"):
                cancelled_args = stage_args | {
                    "cancellation": Cancellation(cancelled=True)
                }
                async with service.stage(
                    session.workflow_id, "get_video", video=seed, **cancelled_args
                ):
                    pytest.fail("concurrent seed stage was accepted")
            await executor.execute_youtube(
                access.context, "videos.list", params={"id": seed}
            )
        async with service.stage(
            session.workflow_id, "find_similar_videos", video=seed, **stage_args
        ) as access:
            assert access.context.reservation_id == session.reservation_id
            await executor.execute_youtube(
                access.context, "search.list", params={"q": "fixture"}
            )
            access.candidate_set_id = "fixture-candidates"
        with pytest.raises(ContractError, match="does not belong"):
            async with service.stage(
                session.workflow_id,
                "propose_playlist",
                candidate_set_id="foreign-candidates",
                **stage_args,
            ):
                pytest.fail("preview used another candidate set")
        async with service.stage(
            session.workflow_id,
            "propose_playlist",
            candidate_set_id="fixture-candidates",
            **stage_args,
        ) as access:
            assert access.context.reservation_id == session.reservation_id
            assert access.context.workflow_id == session.workflow_id
        with pytest.raises(ContractError, match="out of order"):
            async with service.stage(
                session.workflow_id, "get_video", video=seed, **stage_args
            ):
                pytest.fail("already-completed stage was replayed")
    assert sent == ["videos", "search"]


@pytest.mark.anyio
@pytest.mark.parametrize("cancel_before_entry", [True, False])
async def test_cancelled_stage_releases_quota_immediately(cancel_before_entry):
    runtime = fixture_workflow_runtime(Path(__file__).resolve().parents[2])
    assert runtime is not None
    service = runtime.service
    seed = "vidIndex001"
    args = (runtime.binding, "fixture-project", seed)
    session = await service.begin_video_to_playlist(*args)
    await service.begin_video_to_playlist(*args)
    await service.begin_video_to_playlist(*args)
    with pytest.raises(ContractError) as full:
        await service.begin_video_to_playlist(*args)
    assert full.value.detail.code == "QUOTA_INSUFFICIENT"

    stage_args = {
        "binding": runtime.binding,
        "request_id": "fixture-cancellation",
        "cancellation": Cancellation(cancelled=cancel_before_entry),
        "video": seed,
    }
    if cancel_before_entry:
        with pytest.raises(ContractError) as cancelled:
            async with service.stage(session.workflow_id, "get_video", **stage_args):
                pytest.fail("cancelled stage entered")
        assert cancelled.value.detail.code == "WORKFLOW_TIMEOUT"
    else:
        with anyio.CancelScope() as scope:
            async with service.stage(session.workflow_id, "get_video", **stage_args):
                scope.cancel()
                await anyio.lowlevel.checkpoint()

    replacement = await service.begin_video_to_playlist(*args)
    assert replacement.reservation_id != session.reservation_id
    assert replacement.plan.buckets == session.plan.buckets
    with pytest.raises(ContractError, match="session is unavailable"):
        async with service.stage(session.workflow_id, "get_video", **stage_args):
            pytest.fail("cancelled workflow was reused")


@pytest.mark.anyio
async def test_begin_workflow_reserves_composed_budget_over_stdio(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "yt_intel",
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(root),
            "--fixture-db",
            str(tmp_path / "state.sqlite3"),
        ],
    )
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            args = {"kind": "video_to_playlist", "video": "dQw4w9WgXcQ"}
            seen = set()
            for _ in range(3):
                result = await client.call_tool("begin_workflow", args)
                assert not result.is_error
                assert result.structured_content is not None
                data = result.structured_content["data"]
                assert data["reserved"] == {"general": 2583, "search": 12}
                seen.add(data["workflow_id"])
            assert len(seen) == 3
            denied = await client.call_tool("begin_workflow", args)
            assert denied.is_error
            assert denied.structured_content is not None
            assert denied.structured_content["error"]["code"] == "QUOTA_INSUFFICIENT"


@pytest.mark.anyio
async def test_discovery_and_preview_use_the_composed_reservation(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    database_path = tmp_path / "state.sqlite3"
    # The test supplies the seed stage until the library MCP handler is wired.
    # The seed call still goes through the original reservation and fixture executor.
    seed_adapter = """
import sys
from pathlib import Path
from unittest.mock import patch

from yt_intel.cli import main
from yt_intel.mcp import server as composition
from yt_intel.mcp.discovery import FixtureCancellation
from yt_intel.providers.fixture import FixtureDataset, FixtureYouTubeProvider

root = Path(sys.argv[1])
catalog = FixtureDataset.from_json_file(root / 'tests/fixtures/youtube_reads/catalog.json')
register_workflows = composition.register_fixture_workflows

def register_with_seed_stage(server, runtime):
    register_workflows(server, runtime)

    @server.tool()
    async def fixture_test_seed_stage(workflow_id: str, video: str) -> bool:
        async with runtime.service.stage(
            workflow_id, 'get_video', binding=runtime.binding,
            request_id='fixture-seed-stage', cancellation=FixtureCancellation(), video=video,
        ) as access:
            async with FixtureYouTubeProvider(catalog, quota_ledger=runtime.ledger) as provider:
                return video in (await provider.get_videos(access.context, (video,))).videos

with patch.object(composition, 'register_fixture_workflows', register_with_seed_stage):
    raise SystemExit(main(sys.argv[2:]))
"""
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-c",
            seed_adapter,
            str(root),
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(root),
            "--fixture-db",
            str(database_path),
        ],
    )
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            seed = "vidIndex002"
            start = await client.call_tool(
                "begin_workflow", {"kind": "video_to_playlist", "video": seed}
            )
            assert not start.is_error and start.structured_content is not None
            workflow_id = start.structured_content["data"]["workflow_id"]
            discovery_args = {"workflow_id": workflow_id, "video": seed}
            out_of_order = await client.call_tool("find_similar_videos", discovery_args)
            assert out_of_order.is_error and out_of_order.structured_content is not None
            assert out_of_order.structured_content["error"]["code"] == "INVALID_INPUT"

            seed_result = await client.call_tool(
                "fixture_test_seed_stage", discovery_args
            )
            assert not seed_result.is_error and seed_result.structured_content == {
                "result": True
            }
            wrong_seed = await client.call_tool(
                "find_similar_videos", {**discovery_args, "video": "vidIndex001"}
            )
            assert wrong_seed.is_error
            discovered = await client.call_tool("find_similar_videos", discovery_args)
            assert not discovered.is_error and discovered.structured_content is not None
            candidate_set_id = discovered.structured_content["candidate_set_id"]
            preview_args = {
                "workflow_id": workflow_id,
                "title": "Database indexing practice",
                "topic": "database indexing",
                "total_seconds": 1800,
                "max_video_seconds": 1200,
                "language": "en",
            }
            refused = await client.call_tool(
                "propose_playlist",
                {**preview_args, "candidate_set_id": "fixture-recommendations"},
            )
            assert refused.is_error and refused.structured_content is not None
            assert refused.structured_content["error"]["code"] == "INVALID_INPUT"

            preview = await client.call_tool(
                "propose_playlist",
                {**preview_args, "candidate_set_id": candidate_set_id},
            )
            assert not preview.is_error and preview.structured_content is not None
            proposal = preview.structured_content["data"]
            assert proposal["candidate_set_id"] == candidate_set_id
            assert [item["video_id"] for item in proposal["items"]] == ["vidIndex001"]
            assert (proposal["total_seconds"], proposal["unused_seconds"]) == (
                1200,
                600,
            )

    with Database(database_path).transaction(immediate=False) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM quota_reservations").fetchone()[0]
            == 1
        )
        spent = connection.execute(
            "SELECT bucket, spent, released FROM quota_reservation_buckets "
            "JOIN quota_reservations USING (reservation_id) ORDER BY bucket"
        ).fetchall()
        assert [tuple(row) for row in spent] == [("general", 3, 0), ("search", 2, 0)]
