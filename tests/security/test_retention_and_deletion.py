import json
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from yt_intel.contracts.models import LibrarySnapshot
from yt_intel.infrastructure.database import Database, SCHEMA_VERSION
from yt_intel.infrastructure.repositories import (
    OperationConflict,
    OperationResultExpired,
    SqliteAccountDataRepository,
    SqliteCacheRepository,
    SqliteOperationRepository,
    SqliteSnapshotRepository,
)

CONTRACT_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts"


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def now(self) -> datetime:
        return self.value


def snapshot_fixture() -> LibrarySnapshot:
    payload = json.loads((CONTRACT_FIXTURES / "library_snapshot.json").read_text())
    return LibrarySnapshot.model_validate(payload)


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
    assert await repo.get_snapshot(snapshot.binding, snapshot.snapshot_id, now=now) == snapshot
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
    assert await cache.get(snapshot.binding, key, now=clock.now()) == b"synthetic cache payload"
    clock.value = expiry
    assert await cache.get(snapshot.binding, key, now=clock.now()) is None

    operations = SqliteOperationRepository(database, clock)
    digest = "b" * 64
    await operations.claim_operation(snapshot.binding, "operation-fixture-1", digest)
    await SqliteAccountDataRepository(database, clock).delete_account(snapshot.binding)
    assert await operations.get_operation(snapshot.binding, "operation-fixture-1") is None
    with pytest.raises(OperationResultExpired):
        await operations.claim_operation(snapshot.binding, "operation-fixture-1", digest)
    with pytest.raises(OperationConflict):
        await operations.claim_operation(snapshot.binding, "operation-fixture-1", "c" * 64)


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
    assert await snapshots.get_snapshot(snapshot.binding, snapshot.snapshot_id, now=clock.now()) is None
    with pytest.raises(OperationResultExpired):
        await operations.claim_operation(snapshot.binding, "operation-expired-1", "d" * 64)
    with closing(database.connect()) as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
    assert version == SCHEMA_VERSION
