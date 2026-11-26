# P2-01 SQLite storage adapter

P2-01 implements the A2-01 repository protocols in `yt_intel.infrastructure`.
It stores only normalized metadata and operation identity; OAuth secrets remain
in the protected token vault. SQLite is partitioned by fixture/live mode under
the OS user-data directory and never defaults to a path in the checkout.

## Public adapters

- `Database` applies numbered migrations, enables foreign keys, WAL, a busy
  timeout and secure deletion, and keeps each transaction short.
- `SqliteSnapshotRepository` and `SqliteProposalRepository` implement the
  account-bound A2-01 protocols. IDs/versions are immutable and expired or
  foreign objects read as absent.
- `SqliteCacheRepository` implements the byte cache protocol. Callers set the
  configured TTL (24 hours by default) and a hard expiry no later than 30 days.
- `SqliteOperationRepository.claim_operation` atomically stores intent before
  a caller can dispatch a write. Same ID and digest returns the existing intent;
  different content/account conflicts. `update_operation` durably advances
  its safe status. Expiry reduces the row to an operation ID/digest/status
  tombstone, so a later call cannot silently create a new operation.
- `SqliteAccountDataRepository.delete_account` cascades account-owned rows,
  checkpoints/truncates WAL, and retains only minimal write replay tombstones.
  Project quota tables are intentionally independent and are not cleared.

Repositories receive the existing `Clock` protocol. Tests inject a synthetic
clock and use temporary databases to cover restart, expiry, account isolation,
and replay behavior. Startup migrations serialize in-process, use SQLite's
write lock across processes, and retry transient WAL-mode contention. An open
reader may keep old pages visible in its snapshot; deletion commits account
row removal but raises `StorageCleanupPending` until WAL truncation can finish.
Callers must report that cleanup is pending and retry after readers close.
Operation updates use monotonic revisions and cannot overwrite a newer or
completed state. A revalidated approved proposal can transition to
`superseded`; the replacement is stored as a new immutable version. The real
quota ledger and OAuth disconnect caller are later integrations; their work is
not claimed by this task.

## Retention

Snapshots and cache entries cannot live beyond 30 days. Cache reads also stop
at the configured TTL, with a 24-hour default. Proposal reads stop at proposal
expiry, and proposal payloads are removed by their 30-day hard-retention point.
Operation payloads are similarly removed after 30 days while a minimal
tombstone prevents replay. `purge_expired(now)` is the explicit cleanup hook;
startup/periodic scheduling belongs to application composition.

## Verification

The storage suite covers fixture loading, database restart, cache and object
expiry, account isolation, tombstones, process-level concurrent startup,
deletion while a reader is open, stale completed-operation updates, and
superseding an approved proposal after revalidation. Run from the repository
root with an isolated Python 3.13 environment and the hashed dev lock:

```powershell
wsl -d Ubuntu-22.04 -- bash -lc 'uv python install 3.13'
wsl -d Ubuntu-22.04 -- bash -lc 'uv venv ~/.venvs/seproject-p2-01 --python 3.13'
wsl -d Ubuntu-22.04 -- bash -lc 'uv pip install --python ~/.venvs/seproject-p2-01/bin/python --require-hashes -r "/mnt/c/mei/SE Lab/SEproject/requirements-dev.lock"'
wsl -d Ubuntu-22.04 -- bash -lc 'uv pip install --python ~/.venvs/seproject-p2-01/bin/python --no-deps --editable "/mnt/c/mei/SE Lab/SEproject"'
wsl -d Ubuntu-22.04 --cd "/mnt/c/mei/SE Lab/SEproject" -- ~/.venvs/seproject-p2-01/bin/python -m pytest -m "not live" -q
wsl -d Ubuntu-22.04 --cd "/mnt/c/mei/SE Lab/SEproject" -- ~/.venvs/seproject-p2-01/bin/ruff check src/yt_intel/infrastructure tests/security/test_retention_and_deletion.py
wsl -d Ubuntu-22.04 --cd "/mnt/c/mei/SE Lab/SEproject" -- ~/.venvs/seproject-p2-01/bin/ruff format --check src/yt_intel/infrastructure tests/security/test_retention_and_deletion.py
```

Issue and PR URLs are recorded in the repository's GitHub conversation; add
their exact links to the brain log when available in the checkout.
