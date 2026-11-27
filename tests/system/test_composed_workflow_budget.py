import sys
from pathlib import Path

import anyio
import httpx
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from yt_intel.contracts.errors import ContractError
from yt_intel.infrastructure.http import AccountedHttpExecutor
from yt_intel.mcp.workflows import fixture_workflow_runtime


class Cancellation:
    def __init__(self):
        self._event = anyio.Event()

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
                async with service.stage(
                    session.workflow_id, "get_video", video=seed, **stage_args
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
async def test_begin_workflow_reserves_composed_budget_over_stdio():
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
