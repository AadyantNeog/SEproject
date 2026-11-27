from pathlib import Path

import pytest

from yt_intel.feature_benchmarks import CANDIDATES, run, workload

ROOT = Path(__file__).resolve().parents[2]


def test_workload_exercises_the_srs_candidate_bound() -> None:
    shape = workload()
    assert shape["candidates"] == CANDIDATES == 200
    assert shape["channels"] == 20
    assert shape["profile_sources"] == ["likes", "playlists", "subscriptions"]
    assert shape["similar_videos_ranked"] == 50
    assert shape["recommendations_ranked"] == 50
    assert 1 <= shape["proposal_items"] <= 50
    assert shape["proposal_total_seconds"] <= 7200


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_feature_targets_meet_nfr_08_over_fixtures() -> None:
    report = await run(ROOT, 30)
    assert report["mode"] == "fixture" and report["live_quota"] == 0
    rows = {**report["in_process"], **report["stdio"]}
    assert set(rows) == {
        "validate_inputs",
        "rank_similar_videos_200",
        "rank_similar_channels_200",
        "rank_recommendations_200",
        "construct_proposal_200",
        "find_similar_videos",
        "find_similar_channels",
        "recommend_videos",
        "propose_playlist",
        "find_similar_videos_invalid_input",
    }
    for row in rows.values():
        assert row["warmups"] == 1 and row["runs"] == 30
        assert len(row["samples_ms"]) == 30
        assert row["passed"] is True, row
    assert report["stdio"]["find_similar_videos_invalid_input"]["observed"] == {
        "input": {"video": "https://example.com/watch?v=vidIndex001"},
        "error_code": "UNSUPPORTED_IDENTIFIER",
    }
    assert report["all_targets_passed"] is True


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_feature_benchmarks_refuse_fewer_than_30_runs() -> None:
    with pytest.raises(ValueError, match="30"):
        await run(ROOT, 29, stdio=False)
