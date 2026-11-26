import json
from contextlib import closing
from datetime import datetime, timedelta
from multiprocessing import get_context
from pathlib import Path
from typing import Any

import pytest

from yt_intel.contracts.models import LibrarySnapshot
from yt_intel.contracts.proposals import PlaylistProposal
from yt_intel.infrastructure.database import (
    SCHEMA_VERSION,
    Database,
    StorageCleanupPending,
)
from yt_intel.infrastructure.repositories import (
    OperationConflict,
    OperationResultExpired,
    SqliteAccountDataRepository,
    SqliteCacheRepository,
    SqliteOperationRepository,
    SqliteProposalRepository,
    SqliteSnapshotRepository,
    StaleOperationUpdate,
)

CONTRACT_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


def load_contract_fixture(name: str) -> str:
    """Load raw JSON so Pydantic validates it in JSON mode, including timestamps."""
    return (CONTRACT_FIXTURES / f"{name}.json").read_text(encoding="utf-8")


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


def snapshot_fixture() -> LibrarySnapshot:
    return LibrarySnapshot.model_validate_json(
        load_contract_fixture("library_snapshot")
    )


def _startup_worker(database_path: str, barrier: Any, results: Any) -> None:
    try:
        barrier.wait(timeout=15)
        database = Database(Path(database_path))
        with closing(database.connect()) as connection:
            version = connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()[0]
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        results.put(("ok", version, integrity))
    except BaseException as error:
        results.put(("error", repr(error)))


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_snapshot_is_account_bound_and_survives_database_restart(tmp_path):
    snapshot = snapshot_fixture()
    now = snapshot.fetched_at
    clock = FakeClock(now)
    path = tmp_path / "private" / "state.sqlite3"
    first = Database(path)
    repo = SqliteSnapshotRepository(first, clock)
    await repo.save_snapshot(snapshot)
    first.close()

    reopened = Database(path)
    repo = SqliteSnapshotRepository(reopened, clock)
    assert (
        await repo.get_snapshot(snapshot.binding, snapshot.snapshot_id, now=now)
        == snapshot
    )
    foreign = snapshot.binding.model_copy(update={"channel_id": "UC" + "B" * 22})
    assert await repo.get_snapshot(foreign, snapshot.snapshot_id, now=now) is None
    reopened.close()


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_cache_expiry_and_account_deletion_preserve_replay_tombstone(tmp_path):
    snapshot = snapshot_fixture()
    clock = FakeClock(snapshot.fetched_at)
    database = Database(tmp_path / "state.sqlite3")
    cache = SqliteCacheRepository(database, clock)
    key = "a" * 64
    expiry = clock.now() + timedelta(hours=24)
    hard_expiry = clock.now() + timedelta(days=30)
    await cache.put(
        snapshot.binding,
        key,
        b"synthetic cache payload",
        expires_at=expiry,
        retained_until=hard_expiry,
    )
    assert (
        await cache.get(snapshot.binding, key, now=clock.now())
        == b"synthetic cache payload"
    )
    clock.value = expiry
    assert await cache.get(snapshot.binding, key, now=clock.now()) is None

    operations = SqliteOperationRepository(database, clock)
    digest = "b" * 64
    await operations.claim_operation(snapshot.binding, "operation-fixture-1", digest)
    await SqliteAccountDataRepository(database, clock).delete_account(snapshot.binding)
    assert (
        await operations.get_operation(snapshot.binding, "operation-fixture-1") is None
    )
    with pytest.raises(OperationResultExpired):
        await operations.claim_operation(
            snapshot.binding, "operation-fixture-1", digest
        )
    with pytest.raises(OperationConflict):
        await operations.claim_operation(
            snapshot.binding, "operation-fixture-1", "c" * 64
        )


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_expired_snapshot_is_removed_and_operation_cannot_be_replayed(tmp_path):
    snapshot = snapshot_fixture()
    clock = FakeClock(snapshot.fetched_at)
    database = Database(tmp_path / "state.sqlite3")
    snapshots = SqliteSnapshotRepository(database, clock)
    await snapshots.save_snapshot(snapshot)
    operations = SqliteOperationRepository(database, clock)
    await operations.claim_operation(snapshot.binding, "operation-expired-1", "d" * 64)

    clock.value += timedelta(days=31)
    await SqliteAccountDataRepository(database, clock).purge_expired(clock.now())
    assert (
        await snapshots.get_snapshot(
            snapshot.binding, snapshot.snapshot_id, now=clock.now()
        )
        is None
    )
    with pytest.raises(OperationResultExpired):
        await operations.claim_operation(
            snapshot.binding, "operation-expired-1", "d" * 64
        )
    with closing(database.connect()) as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
    assert version == SCHEMA_VERSION


def test_concurrent_database_startup_applies_migrations_once(tmp_path):
    path = tmp_path / "shared" / "state.sqlite3"
    process_count = 4
    context = get_context("spawn")
    barrier = context.Barrier(process_count)
    results = context.Queue()
    workers = [
        context.Process(target=_startup_worker, args=(str(path), barrier, results))
        for _ in range(process_count)
    ]
    for worker in workers:
        worker.start()
    results_seen = [results.get(timeout=30) for _ in workers]
    for worker in workers:
        worker.join(timeout=15)
    assert all(worker.exitcode == 0 for worker in workers)
    assert results_seen == [("ok", SCHEMA_VERSION, "ok")] * process_count


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_delete_with_open_reader_reports_pending_cleanup_then_completes(tmp_path):
    snapshot = snapshot_fixture()
    database = Database(tmp_path / "state.sqlite3")
    snapshots = SqliteSnapshotRepository(database, FakeClock(snapshot.fetched_at))
    await snapshots.save_snapshot(snapshot)
    reader = database.connect()
    reader.execute("BEGIN")
    assert (
        reader.execute(
            "SELECT payload FROM snapshots WHERE snapshot_id = ?",
            (snapshot.snapshot_id,),
        ).fetchone()
        is not None
    )

    deletion = SqliteAccountDataRepository(database, FakeClock(snapshot.fetched_at))
    with pytest.raises(StorageCleanupPending):
        await deletion.delete_account(snapshot.binding)
    assert (
        reader.execute(
            "SELECT payload FROM snapshots WHERE snapshot_id = ?",
            (snapshot.snapshot_id,),
        ).fetchone()
        is not None
    )
    reader.rollback()
    reader.close()

    await deletion.delete_account(snapshot.binding)
    with closing(database.connect()) as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM snapshots WHERE snapshot_id = ?", (snapshot.snapshot_id,)
            ).fetchone()
            is None
        )


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_stale_update_cannot_revert_completed_operation(tmp_path):
    snapshot = snapshot_fixture()
    clock = FakeClock(snapshot.fetched_at)
    repository = SqliteOperationRepository(Database(tmp_path / "state.sqlite3"), clock)
    original = await repository.claim_operation(
        snapshot.binding, "operation-completed-1", "e" * 64
    )
    completed = original.model_copy(
        update={"state": "completed", "updated_at": clock.now() + timedelta(seconds=1)}
    )
    saved = await repository.update_operation(completed)
    assert saved.revision == original.revision + 1

    stale = original.model_copy(
        update={"state": "creating", "updated_at": clock.now() + timedelta(seconds=2)}
    )
    with pytest.raises(StaleOperationUpdate):
        await repository.update_operation(stale)
    current = await repository.get_operation(snapshot.binding, original.operation_id)
    assert current is not None
    assert current.state == "completed"
    assert current.revision == saved.revision


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_revalidation_supersedes_approved_proposal_before_replacement(tmp_path):
    base = PlaylistProposal.model_validate_json(
        load_contract_fixture("playlist_proposal")
    )
    clock = FakeClock(base.created_at)
    repository = SqliteProposalRepository(Database(tmp_path / "state.sqlite3"), clock)
    approved = base.model_copy(update={"state": "approved"})
    await repository.save_proposal(approved)

    superseded = base.model_copy(update={"state": "superseded"})
    await repository.save_proposal(superseded)
    old_version = await repository.get_proposal(base.binding, base.ref, now=clock.now())
    assert old_version is not None and old_version.state == "superseded"

    replacement_data = base.model_dump(mode="json")
    replacement_data["ref"]["version"] = base.ref.version + 1
    replacement_data["digest"] = "f" * 64
    replacement_data["items"][0]["title"] = "Revalidated fixture title"
    replacement = PlaylistProposal.model_validate_json(json.dumps(replacement_data))
    await repository.save_proposal(replacement)
    current = await repository.get_proposal(
        base.binding, replacement.ref, now=clock.now()
    )
    assert current is not None
    assert current.state == "proposed"
    assert current.digest != old_version.digest
