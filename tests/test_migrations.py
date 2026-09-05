"""Schema migration runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmemory.domain.errors import MigrationError
from devmemory.storage.db import Database, discover_migrations


def test_shipped_migrations_are_sequential() -> None:
    migrations = discover_migrations()
    assert [m.version for m in migrations] == list(range(1, len(migrations) + 1))


def test_migrate_applies_and_is_idempotent(database: Database) -> None:
    applied = database.migrate()
    assert [m.name for m in applied] == ["init"]
    assert database.schema_version() == 1

    tables = {
        row["name"]
        for row in database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {"projects", "schema_migrations"} <= tables

    assert database.migrate() == []  # nothing pending the second time


def test_partial_history_only_applies_the_rest(database: Database) -> None:
    database._ensure_migrations_table()  # exercising internals deliberately
    database.connection.execute(
        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (1, 'init', '2026-01-01')"
    )
    # Pretend 0001 ran elsewhere; the runner must not re-run it (which would fail
    # on CREATE TABLE projects) and must report nothing pending.
    assert database.migrate() == []


def test_bad_filename_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "1_init.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError):
        discover_migrations(tmp_path)


def test_numbering_gap_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "0001_a.sql").write_text("SELECT 1;", encoding="utf-8")
    (tmp_path / "0003_c.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError):
        discover_migrations(tmp_path)


def test_transaction_commits_and_rolls_back(database: Database) -> None:
    database.migrate()
    conn = database.connection

    with database.transaction() as c:
        c.execute(
            "INSERT INTO projects (project_id, name, repo_path, created_at, updated_at) "
            "VALUES ('p', 'P', '/tmp', '2026-01-01', '2026-01-01')"
        )
    assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1

    with pytest.raises(RuntimeError), database.transaction() as c:
        c.execute(
            "INSERT INTO projects (project_id, name, repo_path, created_at, updated_at) "
            "VALUES ('q', 'Q', '/tmp', '2026-01-01', '2026-01-01')"
        )
        raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1  # rolled back


def test_close_is_reentrant(database: Database) -> None:
    database.migrate()
    database.close()
    database.close()  # no error
    assert database.schema_version() == 1  # reconnects transparently


def test_failing_migration_rolls_back(tmp_path: Path) -> None:
    migrations = tmp_path / "m"
    migrations.mkdir()
    (migrations / "0001_ok.sql").write_text("CREATE TABLE a (x INTEGER);", encoding="utf-8")
    (migrations / "0002_boom.sql").write_text("CREATE TABLE b (bad syntax here;", encoding="utf-8")

    db = Database(tmp_path / "db.sqlite", migrations_dir=migrations)
    with pytest.raises(MigrationError):
        db.migrate()

    # 0001 committed, 0002 rolled back and not recorded.
    assert db.schema_version() == 1
    db.close()
