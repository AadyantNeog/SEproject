from contextlib import asynccontextmanager
from hashlib import sha256

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
        "test": "skipped",
        "start": "skipped",
        "fetch": "skipped",
        "cleanup": "passed",
    }


@pytest.mark.anyio
async def test_reports_test_failure_as_its_own_stage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        local_checks, "_build", lambda root, output: output / "fake.whl"
    )

    def fail_test(root):
        assert root == tmp_path
        raise RuntimeError("synthetic pytest failure")

    monkeypatch.setattr(local_checks, "_test", fail_test)
    report = await local_checks.check_local(tmp_path)
    assert {stage: entry["status"] for stage, entry in report.items()} == {
        "build": "passed",
        "test": "failed",
        "start": "skipped",
        "fetch": "skipped",
        "cleanup": "passed",
    }


@pytest.mark.anyio
async def test_benchmark_uses_wheel_built_from_requested_checkout(
    tmp_path, monkeypatch
):
    def build(root, output):
        assert root == tmp_path
        wheel = output / "built.whl"
        wheel.write_bytes(b"fixture wheel")
        return wheel

    @asynccontextmanager
    async def session(root, state, *, wheel):
        assert root == tmp_path
        assert wheel == state.parent / "built.whl"
        yield object()

    async def fetch(client):
        pass

    monkeypatch.setattr(local_checks, "_build", build)
    monkeypatch.setattr(local_checks, "fixture_session", session)
    monkeypatch.setattr(local_checks, "fetch_fixture_video", fetch)
    report = await local_checks.benchmark_fixture(tmp_path, 30)
    assert report["wheel_sha256"] == sha256(b"fixture wheel").hexdigest()
