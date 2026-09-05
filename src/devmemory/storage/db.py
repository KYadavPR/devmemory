"""SQLite connection management and a forward-only schema migration runner.

Migrations are plain ``.sql`` files in ``migrations/`` named ``NNNN_slug.sql``.
They are applied in numeric order inside a transaction, and each is recorded in
``schema_migrations`` so re-running ``migrate()`` is a no-op.
"""

from __future__ import annotations

import contextlib
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from devmemory.domain.errors import MigrationError
from devmemory.logging import get_logger

_log = get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Return every migration file, ordered by version, validating the sequence."""
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _MIGRATION_RE.match(path.name)
        if match is None:
            raise MigrationError(
                f"Migration file {path.name!r} does not match NNNN_slug.sql.",
            )
        migrations.append(Migration(int(match.group(1)), match.group(2), path))

    for expected, migration in enumerate(migrations, start=1):
        if migration.version != expected:
            raise MigrationError(
                f"Migration numbering gap: expected {expected:04d}, found "
                f"{migration.version:04d} ({migration.name}).",
            )
    return migrations


class Database:
    """Access to a project's metadata database.

    A single connection, shared. Every read and write goes through the helpers
    below, each guarded by a re-entrant lock, so the web server (uvicorn's
    threadpool) and the CLI both use it safely. ``check_same_thread=False`` is set
    for the server; access is still fully serialized by ``_lock``.
    """

    def __init__(
        self,
        path: Path,
        *,
        migrations_dir: Path = MIGRATIONS_DIR,
        check_same_thread: bool = True,
    ) -> None:
        self.path = path
        self._migrations_dir = migrations_dir
        self._check_same_thread = check_same_thread
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    # -- connection ------------------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                self.path,
                isolation_level=None,  # autocommit; transactions are explicit
                timeout=30.0,
                check_same_thread=self._check_same_thread,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 30000")
            self._conn = conn
        return self._conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                with contextlib.suppress(sqlite3.Error):
                    self._conn.close()
                self._conn = None

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- guarded access -----------------------------------------------------

    def query(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        with self._lock:
            rows: list[sqlite3.Row] = self.connection.execute(sql, params).fetchall()
            return rows

    def query_one(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        with self._lock:
            row: sqlite3.Row | None = self.connection.execute(sql, params).fetchone()
            return row

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        with self._lock:
            self.connection.execute(sql, params)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block inside ``BEGIN``/``COMMIT``, rolling back on any exception."""
        with self._lock:
            conn = self.connection
            conn.execute("BEGIN")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    # -- migrations ----------------------------------------------------------

    def _ensure_migrations_table(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    INTEGER PRIMARY KEY,
                name       TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )

    def applied_versions(self) -> set[int]:
        self._ensure_migrations_table()
        return {int(row["version"]) for row in self.query("SELECT version FROM schema_migrations")}

    def migrate(self) -> list[Migration]:
        """Apply every pending migration atomically. Returns the ones applied, in order.

        Each migration's DDL and its ``schema_migrations`` row are committed together
        inside a single ``BEGIN``/``COMMIT`` so a failure leaves no partial schema.
        ``executescript`` is used (not per-statement ``execute``) so multi-statement
        DDL - triggers, ``CREATE VIRTUAL TABLE``, FTS shadow tables - works.
        """
        with self._lock:
            self._ensure_migrations_table()
            applied = self.applied_versions()
            pending = [
                m for m in discover_migrations(self._migrations_dir) if m.version not in applied
            ]
            conn = self.connection
            return self._apply_pending(conn, pending)

    def _apply_pending(self, conn: sqlite3.Connection, pending: list[Migration]) -> list[Migration]:
        for migration in pending:
            _log.info("migration.apply", version=migration.version, name=migration.name)
            applied_at = datetime.now(UTC).isoformat()
            script = (
                "BEGIN;\n"
                f"{migration.sql.strip().rstrip(';')};\n"
                "INSERT INTO schema_migrations (version, name, applied_at) "
                f"VALUES ({migration.version}, '{migration.name}', '{applied_at}');\n"
                "COMMIT;\n"
            )
            try:
                conn.executescript(script)
            except sqlite3.Error as exc:
                with contextlib.suppress(sqlite3.Error):
                    conn.executescript("ROLLBACK;")
                raise MigrationError(
                    f"Migration {migration.version:04d}_{migration.name} failed: {exc}",
                ) from exc
        return pending

    def schema_version(self) -> int:
        """Highest applied migration version, or 0 if none."""
        versions = self.applied_versions()
        return max(versions) if versions else 0


__all__ = ["Database", "Migration", "discover_migrations"]
