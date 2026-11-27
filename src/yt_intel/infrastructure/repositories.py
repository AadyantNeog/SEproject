import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, TypeAdapter

from yt_intel.contracts.approval import ApprovableProposal, ApprovalGrant
from yt_intel.contracts.common import (
    AccountBinding,
    Contract,
    Digest,
    NonNegative,
    OpaqueId,
    PlaylistId,
    Positive,
    UtcDateTime,
    VideoId,
)
from yt_intel.contracts.models import LibrarySnapshot
from yt_intel.contracts.proposals import PlaylistProposal, ProposalRef, ResumeProposal
from yt_intel.contracts.repositories import (
    AccountDataRepository,
    CacheRepository,
    OperationRepository,
    ProposalRepository,
    SnapshotRepository,
)
from yt_intel.contracts.workflow import BucketVector, Clock

from .clock import SystemClock
from .database import Database

_MAX_RETENTION = timedelta(days=30)
DEFAULT_CACHE_TTL = timedelta(hours=24)
_PROPOSAL_ADAPTER = TypeAdapter(ApprovableProposal)


class RepositoryConflict(RuntimeError):
    """An immutable or account-bound repository identity was reused."""


class OperationConflict(RepositoryConflict):
    """An operation ID was reused for different content or account state."""


class OperationResultExpired(RuntimeError):
    """Only an expired operation tombstone remains; execution cannot be replayed."""


class StaleOperationUpdate(RuntimeError):
    """An operation update was based on an earlier persisted revision."""


class WriteStep(Contract):
    endpoint: Literal["playlists.insert", "playlistItems.insert"]
    position: NonNegative | None = None
    planned_cost: BucketVector
    remote_id: OpaqueId | None = None
    outcome: Literal["pending", "saved", "refused", "unknown"] = "pending"


class OperationItem(Contract):
    video_id: VideoId
    duration_seconds: Positive


class OperationIntent(Contract):
    """Small durable operation identity persisted before any external write."""

    operation_id: OpaqueId
    binding: AccountBinding
    digest: Digest
    state: Literal[
        "not_started",
        "awaiting_approval",
        "preflighting",
        "creating",
        "completed",
        "partial",
        "unknown",
        "verification_pending",
        "rejected",
        "expired",
        "failed_preflight",
        "failed",
    ]
    revision: NonNegative = 0
    created_at: UtcDateTime
    updated_at: UtcDateTime
    retained_until: UtcDateTime
    proposal_ref: ProposalRef | None = None
    workflow_id: OpaqueId | None = None
    resume_ref: ProposalRef | None = None
    last_resume_ref: ProposalRef | None = None
    playlist_id: PlaylistId | None = None
    planned_items: tuple[OperationItem, ...] = ()
    write_steps: tuple[WriteStep, ...] = ()

    def to_json(self) -> str:
        return json.dumps(
            {
                "operation_id": self.operation_id,
                "binding": self.binding.model_dump(mode="json"),
                "digest": self.digest,
                "state": self.state,
                "revision": self.revision,
                "created_at": _timestamp(self.created_at),
                "updated_at": _timestamp(self.updated_at),
                "retained_until": _timestamp(self.retained_until),
                "proposal_ref": self.proposal_ref.model_dump(mode="json")
                if self.proposal_ref
                else None,
                "workflow_id": self.workflow_id,
                "resume_ref": self.resume_ref.model_dump(mode="json")
                if self.resume_ref
                else None,
                "last_resume_ref": self.last_resume_ref.model_dump(mode="json")
                if self.last_resume_ref
                else None,
                "playlist_id": self.playlist_id,
                "planned_items": [
                    item.model_dump(mode="json") for item in self.planned_items
                ],
                "write_steps": [
                    step.model_dump(mode="json") for step in self.write_steps
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, value: str) -> "OperationIntent":
        return cls.model_validate_json(value)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _binding_key(binding: AccountBinding) -> str:
    stable = json.dumps(
        binding.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(stable).hexdigest()


def _canonical(model: BaseModel) -> str:
    return json.dumps(
        model.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )


def _ensure_account(
    connection: sqlite3.Connection, binding: AccountBinding, now: datetime
) -> str:
    key = _binding_key(binding)
    connection.execute(
        "INSERT OR IGNORE INTO accounts "
        "(binding_key, installation_id, credential_binding_id, channel_id, mode, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            key,
            binding.installation_id,
            binding.credential_binding_id,
            binding.channel_id,
            binding.mode,
            _timestamp(now),
        ),
    )
    return key


class SqliteAccountDataRepository(AccountDataRepository):
    def __init__(self, database: Database, clock: Clock | None = None) -> None:
        self.database = database
        self.clock = clock or SystemClock()

    async def delete_account(self, binding: AccountBinding) -> None:
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT operation_id, digest FROM operations WHERE binding_key = ?",
                (_binding_key(binding),),
            ).fetchall()
            for row in rows:
                connection.execute(
                    "INSERT OR IGNORE INTO operation_tombstones "
                    "(operation_id, digest, expired_at, status) VALUES (?, ?, ?, 'disconnected')",
                    (row["operation_id"], row["digest"], _timestamp(self.clock.now())),
                )
            connection.execute(
                "DELETE FROM accounts WHERE binding_key = ?", (_binding_key(binding),)
            )
        self.database.checkpoint_and_truncate()

    async def purge_expired(self, now: UtcDateTime) -> None:
        stamp = _timestamp(now)
        with self.database.transaction() as connection:
            expired_operations = connection.execute(
                "SELECT operation_id, digest FROM operations WHERE retained_until <= ?",
                (stamp,),
            ).fetchall()
            for row in expired_operations:
                connection.execute(
                    "INSERT OR IGNORE INTO operation_tombstones "
                    "(operation_id, digest, expired_at, status) VALUES (?, ?, ?, 'expired')",
                    (row["operation_id"], row["digest"], stamp),
                )
            connection.execute(
                "DELETE FROM snapshots WHERE retained_until <= ?", (stamp,)
            )
            connection.execute(
                "DELETE FROM proposals WHERE retained_until <= ?", (stamp,)
            )
            connection.execute(
                "DELETE FROM cache_entries WHERE retained_until <= ?", (stamp,)
            )
            connection.execute(
                "DELETE FROM operations WHERE retained_until <= ?", (stamp,)
            )
        self.database.checkpoint_and_truncate()


class SqliteSnapshotRepository(SnapshotRepository):
    def __init__(self, database: Database, clock: Clock | None = None) -> None:
        self.database = database
        self.clock = clock or SystemClock()

    async def save_snapshot(self, snapshot: LibrarySnapshot) -> None:
        if snapshot.retained_until > snapshot.fetched_at + _MAX_RETENTION:
            raise ValueError("snapshot retention cannot exceed 30 days from fetch")
        payload = snapshot.model_dump_json()
        with self.database.transaction() as connection:
            key = _ensure_account(connection, snapshot.binding, self.clock.now())
            prior = connection.execute(
                "SELECT binding_key, payload FROM snapshots WHERE snapshot_id = ?",
                (snapshot.snapshot_id,),
            ).fetchone()
            if prior is not None:
                if prior["binding_key"] != key or prior["payload"] != payload:
                    raise RepositoryConflict(
                        "snapshot ID is immutable and account-bound"
                    )
                return
            connection.execute(
                "INSERT INTO snapshots(snapshot_id, binding_key, fetched_at, retained_until, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    snapshot.snapshot_id,
                    key,
                    _timestamp(snapshot.fetched_at),
                    _timestamp(snapshot.retained_until),
                    payload,
                ),
            )

    async def get_snapshot(
        self, binding: AccountBinding, snapshot_id: OpaqueId, *, now: UtcDateTime
    ) -> LibrarySnapshot | None:
        with self.database.transaction(immediate=False) as connection:
            row = connection.execute(
                "SELECT payload FROM snapshots WHERE binding_key = ? AND snapshot_id = ? "
                "AND retained_until > ?",
                (_binding_key(binding), snapshot_id, _timestamp(now)),
            ).fetchone()
        return LibrarySnapshot.model_validate_json(row["payload"]) if row else None


class SqliteProposalRepository(ProposalRepository):
    def __init__(self, database: Database, clock: Clock | None = None) -> None:
        self.database = database
        self.clock = clock or SystemClock()

    async def save_proposal(self, proposal: ApprovableProposal) -> None:
        retained_until = proposal.created_at + _MAX_RETENTION
        payload = _canonical(proposal)
        with self.database.transaction() as connection:
            key = _ensure_account(connection, proposal.binding, self.clock.now())
            prior = connection.execute(
                "SELECT binding_key, digest, payload FROM proposals "
                "WHERE proposal_id = ? AND version = ?",
                (proposal.ref.proposal_id, proposal.ref.version),
            ).fetchone()
            if prior is not None:
                if prior["binding_key"] != key or prior["digest"] != proposal.digest:
                    raise RepositoryConflict(
                        "proposal versions are immutable and account-bound"
                    )
                previous_fields = json.loads(prior["payload"])
                new_fields = json.loads(payload)
                previous_state = previous_fields.pop("state")
                new_state = new_fields.pop("state")
                if previous_fields != new_fields:
                    raise RepositoryConflict("proposal version content is immutable")
                if previous_state == new_state:
                    return
                allowed = {
                    "proposed": {"approved", "rejected", "expired", "superseded"},
                    "approved": {"expired", "superseded"},
                    "rejected": set(),
                    "expired": set(),
                    "superseded": set(),
                }
                if new_state not in allowed[previous_state]:
                    raise RepositoryConflict("proposal state transition is not allowed")
                connection.execute(
                    "UPDATE proposals SET state = ?, payload = ? "
                    "WHERE proposal_id = ? AND version = ? AND binding_key = ?",
                    (
                        new_state,
                        payload,
                        proposal.ref.proposal_id,
                        proposal.ref.version,
                        key,
                    ),
                )
                return
            connection.execute(
                "INSERT INTO proposals "
                "(proposal_id, version, binding_key, digest, state, created_at, expires_at, retained_until, payload) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    proposal.ref.proposal_id,
                    proposal.ref.version,
                    key,
                    proposal.digest,
                    proposal.state,
                    _timestamp(proposal.created_at),
                    _timestamp(proposal.expires_at),
                    _timestamp(retained_until),
                    payload,
                ),
            )

    async def get_proposal(
        self,
        binding: AccountBinding,
        ref: ProposalRef,
        *,
        now: UtcDateTime,
    ) -> ApprovableProposal | None:
        with self.database.transaction(immediate=False) as connection:
            row = connection.execute(
                "SELECT payload FROM proposals WHERE binding_key = ? AND proposal_id = ? "
                "AND version = ? AND expires_at > ? AND retained_until > ?",
                (
                    _binding_key(binding),
                    ref.proposal_id,
                    ref.version,
                    _timestamp(now),
                    _timestamp(now),
                ),
            ).fetchone()
        return _PROPOSAL_ADAPTER.validate_json(row["payload"]) if row else None

    async def get_current_proposal(
        self, binding: AccountBinding, proposal_id: OpaqueId, *, now: UtcDateTime
    ) -> ApprovableProposal | None:
        with self.database.transaction(immediate=False) as connection:
            row = connection.execute(
                "SELECT payload FROM ("
                "SELECT payload, expires_at, retained_until FROM proposals "
                "WHERE binding_key = ? AND proposal_id = ? "
                "ORDER BY version DESC LIMIT 1"
                ") WHERE expires_at > ? AND retained_until > ?",
                (_binding_key(binding), proposal_id, _timestamp(now), _timestamp(now)),
            ).fetchone()
        return _PROPOSAL_ADAPTER.validate_json(row["payload"]) if row else None

    async def get_retained_creation(
        self,
        binding: AccountBinding,
        ref: ProposalRef,
        digest: Digest,
        *,
        now: UtcDateTime,
    ) -> PlaylistProposal | None:
        """Read exact historical evidence for recovery, independent of approval expiry."""
        with self.database.transaction(immediate=False) as connection:
            row = connection.execute(
                "SELECT payload FROM proposals WHERE binding_key = ? AND proposal_id = ? "
                "AND version = ? AND digest = ? AND retained_until > ?",
                (
                    _binding_key(binding),
                    ref.proposal_id,
                    ref.version,
                    digest,
                    _timestamp(now),
                ),
            ).fetchone()
        proposal = _PROPOSAL_ADAPTER.validate_json(row["payload"]) if row else None
        return proposal if isinstance(proposal, PlaylistProposal) else None


class SqliteCacheRepository(CacheRepository):
    def __init__(self, database: Database, clock: Clock | None = None) -> None:
        self.database = database
        self.clock = clock or SystemClock()

    async def get(
        self, binding: AccountBinding, key: Digest, *, now: UtcDateTime
    ) -> bytes | None:
        with self.database.transaction(immediate=False) as connection:
            row = connection.execute(
                "SELECT payload FROM cache_entries WHERE binding_key = ? AND cache_key = ? "
                "AND expires_at > ? AND retained_until > ?",
                (_binding_key(binding), key, _timestamp(now), _timestamp(now)),
            ).fetchone()
        return bytes(row["payload"]) if row else None

    async def put(
        self,
        binding: AccountBinding,
        key: Digest,
        value: bytes,
        *,
        expires_at: UtcDateTime,
        retained_until: UtcDateTime,
    ) -> None:
        now = self.clock.now()
        if not now < expires_at <= retained_until <= now + _MAX_RETENTION:
            raise ValueError(
                "cache expiry must be future and hard retention at most 30 days"
            )
        with self.database.transaction() as connection:
            binding_key = _ensure_account(connection, binding, now)
            connection.execute(
                "INSERT INTO cache_entries(binding_key, cache_key, expires_at, retained_until, payload) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(binding_key, cache_key) DO UPDATE SET "
                "expires_at=excluded.expires_at, retained_until=excluded.retained_until, payload=excluded.payload",
                (
                    binding_key,
                    key,
                    _timestamp(expires_at),
                    _timestamp(retained_until),
                    value,
                ),
            )

    async def put_with_default_ttl(
        self,
        binding: AccountBinding,
        key: Digest,
        value: bytes,
        *,
        fetched_at: UtcDateTime | None = None,
        ttl: timedelta = DEFAULT_CACHE_TTL,
    ) -> None:
        now = fetched_at or self.clock.now()
        if ttl <= timedelta(0) or ttl > _MAX_RETENTION:
            raise ValueError("cache TTL must be positive and no more than 30 days")
        await self.put(
            binding,
            key,
            value,
            expires_at=now + ttl,
            retained_until=now + _MAX_RETENTION,
        )


class SqliteOperationRepository(OperationRepository[OperationIntent]):
    def __init__(self, database: Database, clock: Clock | None = None) -> None:
        self.database = database
        self.clock = clock or SystemClock()

    def claim_approved_creation(
        self,
        intent: OperationIntent,
        proposal: PlaylistProposal,
        consume: Callable[[], ApprovalGrant],
    ) -> OperationIntent:
        """Claim a still-current preview and burn its in-memory grant under the write lock."""
        stamp = _timestamp(self.clock.now())
        if intent.binding != proposal.binding or intent.digest != proposal.digest:
            raise OperationConflict("operation does not match the approved proposal")
        with self.database.transaction() as connection:
            current = connection.execute(
                "SELECT payload, expires_at, retained_until FROM proposals "
                "WHERE binding_key = ? AND proposal_id = ? ORDER BY version DESC LIMIT 1",
                (_binding_key(proposal.binding), proposal.ref.proposal_id),
            ).fetchone()
            if (
                current is None
                or min(current["expires_at"], current["retained_until"]) <= stamp
                or proposal.state != "proposed"
                or _PROPOSAL_ADAPTER.validate_json(current["payload"]) != proposal
            ):
                raise OperationConflict("approval is for a stale proposal")
            claimed = intent.model_copy(
                update={
                    "state": "preflighting",
                    "revision": intent.revision + 1,
                    "updated_at": self.clock.now(),
                }
            )
            changed = connection.execute(
                "UPDATE operations SET state = ?, revision = ?, updated_at = ?, payload = ? "
                "WHERE operation_id = ? AND binding_key = ? AND digest = ? AND revision = ? "
                "AND state = 'not_started' AND retained_until > ?",
                (
                    claimed.state,
                    claimed.revision,
                    stamp,
                    claimed.to_json(),
                    intent.operation_id,
                    _binding_key(intent.binding),
                    intent.digest,
                    intent.revision,
                    stamp,
                ),
            )
            if changed.rowcount != 1:
                raise OperationConflict("operation has already been claimed")
            consume()
            return claimed

    def claim_approved_resume(
        self,
        intent: OperationIntent,
        proposal: ResumeProposal,
        consume: Callable[[], ApprovalGrant],
    ) -> OperationIntent:
        now = self.clock.now()
        stamp = _timestamp(now)
        if (
            intent.binding != proposal.binding
            or intent.operation_id != proposal.original_operation_id
            or intent.digest != proposal.original_digest
            or intent.proposal_ref != proposal.original_proposal
            or intent.resume_ref != proposal.ref
            or intent.playlist_id != proposal.remote_playlist_id
        ):
            raise OperationConflict(
                "resume authority does not match the recorded operation"
            )
        with self.database.transaction() as connection:
            current = connection.execute(
                "SELECT payload, expires_at, retained_until FROM proposals "
                "WHERE binding_key = ? AND proposal_id = ? ORDER BY version DESC LIMIT 1",
                (_binding_key(intent.binding), proposal.ref.proposal_id),
            ).fetchone()
            if (
                current is None
                or min(current["expires_at"], current["retained_until"]) <= stamp
                or proposal.state != "proposed"
                or _PROPOSAL_ADAPTER.validate_json(current["payload"]) != proposal
            ):
                raise OperationConflict("resume preview is no longer current")
            claimed = intent.model_copy(
                update={
                    "state": "creating",
                    "revision": intent.revision + 1,
                    "updated_at": now,
                    "resume_ref": None,
                    "last_resume_ref": proposal.ref,
                }
            )
            changed = connection.execute(
                "UPDATE operations SET state = ?, revision = ?, updated_at = ?, payload = ? "
                "WHERE operation_id = ? AND binding_key = ? AND digest = ? AND revision = ? "
                "AND state IN ('partial', 'unknown', 'verification_pending') AND retained_until > ?",
                (
                    claimed.state,
                    claimed.revision,
                    stamp,
                    claimed.to_json(),
                    intent.operation_id,
                    _binding_key(intent.binding),
                    intent.digest,
                    intent.revision,
                    stamp,
                ),
            )
            if changed.rowcount != 1:
                raise OperationConflict("operation changed before resume")
            consume()
            return claimed

    async def get_operation(
        self, binding: AccountBinding, operation_id: OpaqueId
    ) -> OperationIntent | None:
        now = _timestamp(self.clock.now())
        with self.database.transaction(immediate=False) as connection:
            row = connection.execute(
                "SELECT payload FROM operations WHERE binding_key = ? AND operation_id = ? "
                "AND retained_until > ?",
                (_binding_key(binding), operation_id, now),
            ).fetchone()
        return OperationIntent.from_json(row["payload"]) if row else None

    async def get_recovery_operation(
        self, binding: AccountBinding, operation_id: OpaqueId
    ) -> OperationIntent | None:
        """Report expired detail only when the account can still be verified."""
        now = _timestamp(self.clock.now())
        with self.database.transaction(immediate=False) as connection:
            row = connection.execute(
                "SELECT payload, retained_until FROM operations "
                "WHERE binding_key = ? AND operation_id = ?",
                (_binding_key(binding), operation_id),
            ).fetchone()
        if row is None:
            return None
        if row["retained_until"] <= now:
            raise OperationResultExpired(
                "Operation details expired and cannot be recovered."
            )
        return OperationIntent.from_json(row["payload"])

    async def claim_operation(
        self, binding: AccountBinding, operation_id: OpaqueId, digest: Digest
    ) -> OperationIntent:
        now = self.clock.now()
        stamp = _timestamp(now)
        expired = False
        result: OperationIntent | None = None
        with self.database.transaction() as connection:
            existing = connection.execute(
                "SELECT binding_key, digest, payload, retained_until FROM operations "
                "WHERE operation_id = ?",
                (operation_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["binding_key"] != _binding_key(binding)
                    or existing["digest"] != digest
                ):
                    raise OperationConflict(
                        "operation ID is already bound to different content"
                    )
                if existing["retained_until"] <= stamp:
                    connection.execute(
                        "INSERT OR IGNORE INTO operation_tombstones "
                        "(operation_id, digest, expired_at, status) VALUES (?, ?, ?, 'expired')",
                        (operation_id, digest, stamp),
                    )
                    connection.execute(
                        "DELETE FROM operations WHERE operation_id = ?", (operation_id,)
                    )
                    expired = True
                else:
                    result = OperationIntent.from_json(existing["payload"])
            else:
                tombstone = connection.execute(
                    "SELECT digest FROM operation_tombstones WHERE operation_id = ?",
                    (operation_id,),
                ).fetchone()
                if tombstone is not None:
                    if tombstone["digest"] != digest:
                        raise OperationConflict(
                            "expired operation ID cannot be reused for new content"
                        )
                    expired = True
                else:
                    key = _ensure_account(connection, binding, now)
                    result = OperationIntent(
                        operation_id=operation_id,
                        binding=binding,
                        digest=digest,
                        state="not_started",
                        revision=0,
                        created_at=now,
                        updated_at=now,
                        retained_until=now + _MAX_RETENTION,
                    )
                    connection.execute(
                        "INSERT INTO operations "
                        "(operation_id, binding_key, digest, state, created_at, updated_at, retained_until, payload) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            operation_id,
                            key,
                            digest,
                            result.state,
                            stamp,
                            stamp,
                            _timestamp(result.retained_until),
                            result.to_json(),
                        ),
                    )
        if expired:
            raise OperationResultExpired(
                "operation detail expired; the ID cannot be replayed"
            )
        assert result is not None
        return result

    async def update_operation(self, intent: OperationIntent) -> OperationIntent:
        updated = intent.model_copy(update={"revision": intent.revision + 1})
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE operations SET state = ?, revision = revision + 1, updated_at = ?, payload = ? "
                "WHERE operation_id = ? AND binding_key = ? AND digest = ? AND revision = ? "
                "AND state <> 'completed' AND retained_until > ?",
                (
                    updated.state,
                    _timestamp(updated.updated_at),
                    updated.to_json(),
                    intent.operation_id,
                    _binding_key(intent.binding),
                    intent.digest,
                    intent.revision,
                    _timestamp(self.clock.now()),
                ),
            )
            if cursor.rowcount != 1:
                existing = connection.execute(
                    "SELECT state FROM operations WHERE operation_id = ? AND binding_key = ?",
                    (intent.operation_id, _binding_key(intent.binding)),
                ).fetchone()
                if existing is not None and existing["state"] == "completed":
                    raise StaleOperationUpdate("completed operations cannot be changed")
                raise StaleOperationUpdate(
                    "operation revision is stale or no longer writable"
                )
        return updated
