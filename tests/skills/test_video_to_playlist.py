import sys
from datetime import timedelta
from pathlib import Path

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp_types import TextResourceContents

from yt_intel.contracts.errors import ContractError
from yt_intel.contracts.models import CandidateSet, Coverage, Video
from yt_intel.contracts.proposals import PlaylistProposal
from yt_intel.domain.constraints import parse_playlist_request
from yt_intel.domain.language import normalize_language_tag
from yt_intel.domain.proposals import PlaylistPlanner
from yt_intel.mcp.resources import CREATION_PREVIEW_URI
from yt_intel.presentation.previews import render_proposal

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/contracts"
SKILL_URI = "yt-intel://skills/video-to-playlist"
REQUEST: dict[str, object] = {
    "title": "Indexing walkthrough",
    "topic": "database indexing",
    "total_seconds": 1800,
    "max_video_seconds": 1200,
    "language": "en",
}


@pytest.fixture
def planning_inputs() -> CandidateSet:
    seed = Video.model_validate_json((FIXTURES / "video.json").read_bytes())
    preview = PlaylistProposal.model_validate_json(
        (FIXTURES / "playlist_proposal.json").read_bytes()
    )
    videos = [seed]
    for index, seconds, language in (
        (2, 600, "en-US"),
        (3, 480, "en-US"),
        (4, 1201, "en-US"),
        (5, 600, None),
    ):
        video_id = f"fixture{index:04d}"
        videos.append(
            Video.model_validate(
                {
                    **seed.model_dump(),
                    "video_id": video_id,
                    "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
                    "title": "Database indexing examples",
                    "duration_seconds": seconds,
                    "default_audio_language": language,
                    "default_metadata_language": "en",
                    "language_evidence": "audio" if language else "metadata_only",
                }
            )
        )
    return CandidateSet(
        candidate_set_id="walkthrough-candidates",
        binding=preview.binding,
        videos=tuple(videos),
        source="synthetic",
        seed_video_id=seed.video_id,
        topic=None,
        coverage=Coverage(
            complete=True,
            paginated=False,
            sampled=False,
            truncated=False,
            retrieved=len(videos),
            usable=len(videos),
            inaccessible=0,
            unknown=0,
            limits={"candidates": 5},
            completeness_basis="Synthetic walkthrough candidate set",
        ),
        ranking_version="fixture",
        config_version="fixture",
        created_at=preview.created_at,
        expires_at=preview.created_at + timedelta(minutes=20),
    )


def test_walkthrough_preview_keeps_exact_constraints_and_evidence(
    planning_inputs: CandidateSet,
) -> None:
    proposal = PlaylistPlanner(normalize_language_tag).plan(
        parse_playlist_request(REQUEST),
        planning_inputs,
        binding=planning_inputs.binding,
        destination_channel_title="Synthetic Database Lessons",
        proposal_id="walkthrough-proposal",
        now=planning_inputs.created_at,
    )
    assert [item.video_id for item in proposal.items] == ["fixture0002", "fixture0003"]
    assert proposal.exclusions == {
        "audio_language_unverified": 1,
        "individual_duration_limit": 1,
        "seed_not_requested": 1,
    }
    assert (proposal.total_seconds, proposal.unused_seconds) == (1080, 720)
    assert proposal.body.privacy == "private"
    assert proposal.state == "proposed"

    preview = render_proposal(proposal)
    assert "Destination: Synthetic Database Lessons" in preview
    assert "Total duration: 1080 s (0:18:00)" in preview
    assert "Unused time: 720 s (0:12:00)" in preview
    assert preview.count("Audio language (API evidence): en-US") == 2
    assert preview.index("watch?v=fixture0002") < preview.index("watch?v=fixture0003")


def test_exact_fill_request_requires_clarification() -> None:
    with pytest.raises(ContractError) as error:
        parse_playlist_request({**REQUEST, "duration_mode": "exact"})
    assert error.value.detail.code == "CLARIFICATION_REQUIRED"


def test_infeasible_request_returns_no_proposal(planning_inputs: CandidateSet) -> None:
    with pytest.raises(ContractError) as error:
        PlaylistPlanner(normalize_language_tag).plan(
            parse_playlist_request({**REQUEST, "language": "ja"}),
            planning_inputs,
            binding=planning_inputs.binding,
            destination_channel_title="Synthetic Database Lessons",
            proposal_id="walkthrough-proposal",
            now=planning_inputs.created_at,
        )
    assert error.value.detail.code == "NO_FEASIBLE_PLAYLIST"


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_skill_and_synthetic_preview_are_available_over_fixture_stdio() -> None:
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "yt_intel",
            "serve",
            "--provider",
            "fixture",
            "--project-root",
            str(ROOT),
        ],
    )
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=10) as client:
            await client.initialize()
            resources = {item.uri for item in (await client.list_resources()).resources}
            assert {SKILL_URI, CREATION_PREVIEW_URI} <= resources
            skill = (await client.read_resource(SKILL_URI)).contents[0]
            assert isinstance(skill, TextResourceContents)
            assert skill.mime_type == "text/markdown"
            assert (
                skill.text
                == (ROOT / ".agents/skills/video-to-playlist/SKILL.md")
                .read_bytes()
                .decode()
            )
            example = (await client.read_resource(CREATION_PREVIEW_URI)).contents[0]
            assert isinstance(example, TextResourceContents)
            assert "Mode: fixture (synthetic data)" in example.text
            assert "Total duration: 1320 s (0:22:00)" in example.text
            assert "Unused time: 480 s (0:08:00)" in example.text
