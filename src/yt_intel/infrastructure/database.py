import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from threading import Lock
from time import monotonic, sleep

from platformdirs import user_data_path

from yt_intel.contracts.common import Mode

SCHEMA_VERSION = 1
_MIGRATION_LOCK = Lock()
_MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE accounts (
        binding_key TEXT PRIMARY KEY,
        installation_id TEXT NOT NULL,
        credential_binding_id TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        mode TEXT NOT NULL CHECK (mode IN ('fixture', 'live')),
        created_at TEXT NOT NULL,
        UNIQUE (installation_id, credential_binding_id, channel_id, mode)
    );
    CREATE TABLE snapshots (
        snapshot_id TEXT PRIMARY KEY,
        binding_key TEXT NOT NULL REFERENCES accounts(binding_key) ON DELETE CASCADE,
        fetched_at TEXT NOT NULL,
        retained_until TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE INDEX snapshots_expiry ON snapshots(retained_until);
    CREATE TABLE proposals (
        proposal_id TEXT NOT NULL,
        version INTEGER NOT NULL CHECK (version > 0),
        binding_key TEXT NOT NULL REFERENCES accounts(binding_key) ON DELETE CASCADE,
        digest TEXT NOT NULL,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        retained_until TEXT NOT NULL,
        payload TEXT NOT NULL,
        PRIMARY KEY (proposal_id, version)
    );
    CREATE INDEX proposals_expiry ON proposals(retained_until);
    CREATE TABLE cache_entries (
        binding_key TEXT NOT NULL REFERENCES accounts(binding_key) ON DELETE CASCADE,
        cache_key TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        retained_until TEXT NOT NULL,
        payload BLOB NOT NULL,
        PRIMARY KEY (binding_key, cache_key)
    );
    CREATE INDEX cache_entries_expiry ON cache_entries(expires_at, retained_until);
    CREATE TABLE operations (
        operation_id TEXT PRIMARY KEY,
        binding_key TEXT NOT NULL REFERENCES accounts(binding_key) ON DELETE CASCADE,
        digest TEXT NOT NULL,
        state TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        retained_until TEXT NOT NULL,
        payload TEXT NOT NULL
    );
    CREATE INDEX operations_expiry ON operations(retained_until);
    CREATE TABLE operation_tombstones (
        operation_id TEXT PRIMARY KEY,
        digest TEXT NOT NULL,
        expired_at TEXT NOT NULL,
        status TEXT NOT NULL
    );
    """,
)


def default_database_path(mode: Mode) -> Path:
    """Return a per-user, per-mode path outside the repository checkout."""
    return (
        user_data_path("YouTubeIntelligence", appauthor=False) / mode / "state.sqlite3"
    )


class Database:
    """Short-lived SQLite connections with explicit, forward-only migrations."""

    def __init__(self, path: Path | None = None, *, mode: Mode = "fixture") -> None:
        self.path = (path or default_database_path(mode)).expanduser().resolve()
        self._prepare_parent()
        self.migrate()

    def _prepare_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            self.path.parent.chmod(0o700)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA secure_delete = ON")
        if sys.platform != "win32":
            self.path.chmod(0o600)
        return connection

    def migrate(self) -> None:
        with _MIGRATION_LOCK, closing(self.connect()) as connection:
            self._enable_wal(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS schema_migrations "
                    "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
                version = connection.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
                ).fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise RuntimeError("database schema is newer than this application")
                for next_version in range(version + 1, SCHEMA_VERSION + 1):
                    for statement in _MIGRATIONS[next_version - 1].split(";"):
                        if statement.strip():
                            connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) "
                        "VALUES (?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
                        (next_version,),
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _enable_wal(connection: sqlite3.Connection) -> None:
        deadline = monotonic() + 10
        while True:
            try:
                mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                if mode.lower() != "wal":
                    raise RuntimeError("SQLite refused write-ahead logging mode")
                return
            except sqlite3.OperationalError as error:
                if not any(word in str(error).lower() for word in ("locked", "busy")):
                    raise
                if monotonic() >= deadline:
                    raise
                sleep(0.025)

    @contextmanager
    def transaction(self, *, immediate: bool = True) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def checkpoint_and_truncate(self) -> None:
        with closing(self.connect()) as connection:
            busy, _, _ = connection.execute(
                "PRAGMA wal_checkpoint(TRUNCATE)"
            ).fetchone()
            if busy:
                raise StorageCleanupPending(
                    "SQLite data is deleted, but an open reader prevents WAL truncation"
                )

    def close(self) -> None:
        """Compatibility hook; connections are scoped to each operation."""


class StorageCleanupPending(RuntimeError):
    """Rows were deleted, but an open SQLite reader delays physical cleanup."""
