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
and replay behavior. The real quota ledger and OAuth disconnect caller are
later integrations; their work is not claimed by this task.

## Retention

Snapshots and cache entries cannot live beyond 30 days. Cache reads also stop
at the configured TTL, with a 24-hour default. Proposal reads stop at proposal
expiry, and proposal payloads are removed by their 30-day hard-retention point.
Operation payloads are similarly removed after 30 days while a minimal
tombstone prevents replay. `purge_expired(now)` is the explicit cleanup hook;
startup/periodic scheduling belongs to application composition.

Issue: pending. Draft PR: pending. Aadyant human review: pending.
