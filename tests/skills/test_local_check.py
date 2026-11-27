import pytest

from yt_intel import local_checks


@pytest.mark.anyio
async def test_measure_runs_one_warmup_and_computes_nearest_rank_p95(monkeypatch):
    calls = 0

    async def sample():
        nonlocal calls
        calls += 1

    readings = iter(value for seconds in range(1, 31) for value in (0, seconds))
    monkeypatch.setattr(local_checks, "perf_counter", lambda: next(readings))
    timing = await local_checks.measure(sample)
    assert calls == 31
    assert timing["median_ms"] == 15_500
    assert timing["p95_ms"] == 29_000
    assert timing["warmups"] == 1
    assert timing["runs"] == 30


@pytest.mark.anyio
async def test_rejects_insufficient_sample_count():
    async def sample():
        pytest.fail("invalid run count must be rejected before sampling")

    with pytest.raises(ValueError, match="At least 30"):
        await local_checks.measure(sample, runs=29)


@pytest.mark.anyio
async def test_reports_failed_build_and_cleanup_separately(tmp_path, monkeypatch):
    def fail_build(root, output):
        raise RuntimeError("fake build failure")

    monkeypatch.setattr(local_checks, "_build", fail_build)
    report = await local_checks.check_local(tmp_path)
    assert {stage: entry["status"] for stage, entry in report.items()} == {
        "build": "failed",
        "start": "skipped",
        "fetch": "skipped",
        "cleanup": "passed",
    }
