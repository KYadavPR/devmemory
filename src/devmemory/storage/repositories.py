"""Data-access objects. Every SQL statement in DevMemory lives in this module.

Repositories take a :class:`~devmemory.storage.db.Database` and expose typed
methods returning :mod:`devmemory.domain.models`. Services depend on repositories;
nothing else touches the connection.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from devmemory.domain.models import Project
from devmemory.storage.db import Database


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class ProjectRepository:
    """The single ``projects`` row for a repository."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self) -> Project | None:
        row = self._db.connection.execute("SELECT * FROM projects LIMIT 1").fetchone()
        return _project_from_row(row) if row else None

    def get_by_id(self, project_id: str) -> Project | None:
        row = self._db.connection.execute(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return _project_from_row(row) if row else None

    def create(self, *, project_id: str, name: str, repo_path: str) -> Project:
        now = _utcnow()
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO projects (project_id, name, repo_path, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (project_id, name, repo_path, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"project {project_id!r} already exists") from exc
        created = self.get_by_id(project_id)
        assert created is not None  # noqa: S101 - just inserted
        return created

    def set_current_version(self, project_id: str, version_id: int | None) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE projects SET current_version_id = ?, updated_at = ? WHERE project_id = ?",
                (version_id, _utcnow(), project_id),
            )

    def touch(self, project_id: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE project_id = ?",
                (_utcnow(), project_id),
            )


def _project_from_row(row: sqlite3.Row) -> Project:
    return Project(
        project_id=row["project_id"],
        name=row["name"],
        repo_path=row["repo_path"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
        current_version_id=row["current_version_id"],
    )


__all__ = ["ProjectRepository"]
