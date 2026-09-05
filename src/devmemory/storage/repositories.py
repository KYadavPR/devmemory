"""Data-access objects. Every SQL statement in DevMemory lives in this module.

Repositories take a :class:`~devmemory.storage.db.Database` and expose typed
methods returning :mod:`devmemory.domain.models`. Services depend on repositories;
nothing else touches the connection.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from devmemory.domain.enums import AssociationMethod, FeatureStatus
from devmemory.domain.models import (
    CheckpointReference,
    CheckpointSession,
    Feature,
    Project,
    TokenUsage,
)
from devmemory.storage.db import Database


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _json_or_none(value: object) -> str | None:
    return json.dumps(value) if value is not None else None


def _load_json(value: str | None) -> object:
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


# --- projects -----------------------------------------------------------------------


class ProjectRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self) -> Project | None:
        row = self._db.query_one("SELECT * FROM projects LIMIT 1")
        return _project_from_row(row) if row else None

    def get_by_id(self, project_id: str) -> Project | None:
        row = self._db.query_one("SELECT * FROM projects WHERE project_id = ?", (project_id,))
        return _project_from_row(row) if row else None

    def create(self, *, project_id: str, name: str, repo_path: str) -> Project:
        now = _utcnow()
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    "INSERT INTO projects (project_id, name, repo_path, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
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


# --- entire checkpoints ------------------------------------------------------------


class CheckpointRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert(self, project_id: str, ref: CheckpointReference) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO entire_checkpoints (
                    checkpoint_id, project_id, ref, agent, model, intent, strategy,
                    created_at, git_commit, association_method, association_confidence,
                    tokens_json, imported, sessions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(checkpoint_id) DO UPDATE SET
                    ref = COALESCE(excluded.ref, entire_checkpoints.ref),
                    agent = COALESCE(excluded.agent, entire_checkpoints.agent),
                    model = COALESCE(excluded.model, entire_checkpoints.model),
                    intent = COALESCE(excluded.intent, entire_checkpoints.intent),
                    strategy = COALESCE(excluded.strategy, entire_checkpoints.strategy),
                    created_at = COALESCE(excluded.created_at, entire_checkpoints.created_at),
                    git_commit = COALESCE(excluded.git_commit, entire_checkpoints.git_commit),
                    association_method = excluded.association_method,
                    association_confidence = excluded.association_confidence,
                    tokens_json = excluded.tokens_json,
                    imported = excluded.imported,
                    sessions_json = excluded.sessions_json
                """,
                (
                    ref.checkpoint_id,
                    project_id,
                    ref.ref,
                    ref.agent,
                    ref.model,
                    ref.intent,
                    ref.strategy,
                    ref.created_at.isoformat() if ref.created_at else None,
                    ref.commit_sha,
                    ref.association_method.value,
                    ref.association_confidence,
                    json.dumps(ref.tokens.model_dump()),
                    1 if ref.imported else 0,
                    json.dumps([s.model_dump(mode="json") for s in ref.sessions]),
                ),
            )

    def get(self, checkpoint_id: str) -> CheckpointReference | None:
        row = self._db.query_one(
            "SELECT * FROM entire_checkpoints WHERE checkpoint_id = ?", (checkpoint_id,)
        )
        return _checkpoint_from_row(row) if row else None

    def link(self, version_id: str, checkpoint_id: str, *, is_primary: bool) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO version_checkpoints (version_id, checkpoint_id, is_primary) "
                "VALUES (?, ?, ?)",
                (version_id, checkpoint_id, 1 if is_primary else 0),
            )

    def for_version(self, version_id: str) -> list[tuple[CheckpointReference, bool]]:
        rows = self._db.query(
            """
            SELECT c.*, vc.is_primary FROM entire_checkpoints c
            JOIN version_checkpoints vc ON vc.checkpoint_id = c.checkpoint_id
            WHERE vc.version_id = ?
            ORDER BY vc.is_primary DESC
            """,
            (version_id,),
        )
        return [(_checkpoint_from_row(r), bool(r["is_primary"])) for r in rows]


def _checkpoint_from_row(row: sqlite3.Row) -> CheckpointReference:
    tokens_raw = _load_json(row["tokens_json"])
    sessions_raw = _load_json(row["sessions_json"])
    method_value = row["association_method"] or AssociationMethod.NONE.value
    return CheckpointReference(
        checkpoint_id=row["checkpoint_id"],
        commit_sha=row["git_commit"],
        intent=row["intent"],
        agent=row["agent"],
        model=row["model"],
        strategy=row["strategy"],
        created_at=_dt(row["created_at"]),
        sessions=[CheckpointSession.model_validate(s) for s in sessions_raw]
        if isinstance(sessions_raw, list)
        else [],
        tokens=TokenUsage.model_validate(tokens_raw)
        if isinstance(tokens_raw, dict)
        else TokenUsage(),
        association_method=AssociationMethod(method_value),
        association_confidence=row["association_confidence"] or 0.0,
        ref=row["ref"],
        imported=bool(row["imported"]),
    )


# --- features ---------------------------------------------------------------------


class FeatureRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def upsert(
        self,
        project_id: str,
        name: str,
        *,
        status: FeatureStatus,
        derived_from: str | None = None,
    ) -> Feature:
        now = _utcnow()
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO features (feature_id, project_id, name, status, derived_from,
                                      created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id, name) DO UPDATE SET
                    status = excluded.status,
                    derived_from = COALESCE(excluded.derived_from, features.derived_from),
                    updated_at = excluded.updated_at
                """,
                (
                    _feature_id(project_id, name),
                    project_id,
                    name,
                    status.value,
                    derived_from,
                    now,
                    now,
                ),
            )
        feature = self.get_by_name(project_id, name)
        assert feature is not None  # noqa: S101
        return feature

    def get_by_name(self, project_id: str, name: str) -> Feature | None:
        row = self._db.query_one(
            "SELECT * FROM features WHERE project_id = ? AND name = ?", (project_id, name)
        )
        return _feature_from_row(row) if row else None

    def get(self, feature_id: str) -> Feature | None:
        row = self._db.query_one("SELECT * FROM features WHERE feature_id = ?", (feature_id,))
        return _feature_from_row(row) if row else None

    def list_all(self, project_id: str) -> list[Feature]:
        rows = self._db.query(
            "SELECT * FROM features WHERE project_id = ? ORDER BY name", (project_id,)
        )
        return [_feature_from_row(r) for r in rows]


def _feature_id(project_id: str, name: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "feature"
    return f"{project_id}:{slug}"


def _feature_from_row(row: sqlite3.Row) -> Feature:
    return Feature(
        feature_id=row["feature_id"],
        project_id=row["project_id"],
        name=row["name"],
        status=FeatureStatus(row["status"]),
        derived_from=row["derived_from"],
        created_at=_dt(row["created_at"]),
        updated_at=_dt(row["updated_at"]),
    )


__all__ = [
    "CheckpointRepository",
    "FeatureRepository",
    "ProjectRepository",
]
