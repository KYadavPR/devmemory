"""The development-version repository: persistence + hydration + full-text index.

The heaviest data-access object - a version fans out to changed files, tests,
metrics, regressions, analysis, artifacts, doc flags, and checkpoint links, all
written and read here.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from devmemory.domain.enums import AssociationMethod, ChangeType, MetricDirection, VersionStatus
from devmemory.domain.models import (
    Analysis,
    Artifact,
    ChangedFile,
    DevelopmentEvent,
    DevelopmentVersion,
    DocFlag,
    EnvironmentInfo,
    Metric,
    Regression,
    TestOutcome,
)
from devmemory.storage.db import Database
from devmemory.storage.repositories import CheckpointRepository


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


class VersionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._checkpoints = CheckpointRepository(db)

    # -- numbering / lookup ------------------------------------------------

    def next_version_number(self, project_id: str) -> int:
        row = self._db.connection.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS n FROM versions WHERE project_id = ?",
            (project_id,),
        ).fetchone()
        return int(row["n"])

    def find_by_commit(self, project_id: str, git_commit: str) -> DevelopmentVersion | None:
        row = self._db.connection.execute(
            "SELECT * FROM versions WHERE project_id = ? AND git_commit = ?",
            (project_id, git_commit),
        ).fetchone()
        return self._hydrate(row) if row else None

    def get(self, version_id: str) -> DevelopmentVersion | None:
        row = self._db.connection.execute(
            "SELECT * FROM versions WHERE version_id = ?", (version_id,)
        ).fetchone()
        return self._hydrate(row) if row else None

    def get_by_number(self, project_id: str, number: int) -> DevelopmentVersion | None:
        row = self._db.connection.execute(
            "SELECT * FROM versions WHERE project_id = ? AND version_number = ?",
            (project_id, number),
        ).fetchone()
        return self._hydrate(row) if row else None

    def resolve(self, project_id: str, ref: str) -> DevelopmentVersion | None:
        """Accept ``v7`` / ``V7`` / ``7`` / a git sha prefix."""
        token = ref.strip().lower()
        if token.startswith("v"):
            token = token[1:]
        if token.isdigit():
            return self.get_by_number(project_id, int(token))
        row = self._db.connection.execute(
            "SELECT * FROM versions WHERE project_id = ? AND git_commit LIKE ?",
            (project_id, f"{ref}%"),
        ).fetchone()
        return self._hydrate(row) if row else None

    def latest(self, project_id: str) -> DevelopmentVersion | None:
        row = self._db.connection.execute(
            "SELECT * FROM versions WHERE project_id = ? ORDER BY version_number DESC LIMIT 1",
            (project_id,),
        ).fetchone()
        return self._hydrate(row) if row else None

    def count(self, project_id: str) -> int:
        row = self._db.connection.execute(
            "SELECT COUNT(*) AS c FROM versions WHERE project_id = ?", (project_id,)
        ).fetchone()
        return int(row["c"])

    def page(
        self,
        project_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        ascending: bool = True,
    ) -> list[DevelopmentVersion]:
        order = "ASC" if ascending else "DESC"  # literal, not user input
        rows = self._db.connection.execute(
            "SELECT * FROM versions WHERE project_id = ? "  # noqa: S608
            f"ORDER BY version_number {order} LIMIT ? OFFSET ?",
            (project_id, limit, offset),
        ).fetchall()
        return [self._hydrate(r) for r in rows]

    def previous_relevant(
        self, project_id: str, before_number: int, *, feature_id: str | None = None
    ) -> DevelopmentVersion | None:
        """The version to compare against for regression detection."""
        if feature_id:
            row = self._db.connection.execute(
                "SELECT * FROM versions WHERE project_id = ? AND version_number < ? "
                "AND feature_id = ? ORDER BY version_number DESC LIMIT 1",
                (project_id, before_number, feature_id),
            ).fetchone()
            if row:
                return self._hydrate(row)
        row = self._db.connection.execute(
            "SELECT * FROM versions WHERE project_id = ? AND version_number < ? "
            "ORDER BY version_number DESC LIMIT 1",
            (project_id, before_number),
        ).fetchone()
        return self._hydrate(row) if row else None

    def for_feature(self, feature_id: str) -> list[DevelopmentVersion]:
        rows = self._db.connection.execute(
            "SELECT * FROM versions WHERE feature_id = ? ORDER BY version_number ASC",
            (feature_id,),
        ).fetchall()
        return [self._hydrate(r) for r in rows]

    # -- write ----------------------------------------------------------

    def create(
        self,
        version: DevelopmentVersion,
        *,
        source_event: DevelopmentEvent | None = None,
    ) -> DevelopmentVersion:
        """Persist a fully-assembled version and all its children in one transaction."""
        with self._db.transaction() as conn:
            self._insert_version(conn, version, source_event)
            self._insert_changed_files(conn, version)
            self._insert_tests(conn, version)
            self._insert_metrics(conn, version)
            self._insert_regressions(conn, version)
            self._insert_analysis(conn, version)
            self._insert_doc_flags(conn, version)
            self._index_fts(conn, version)

        if version.primary_checkpoint is not None:
            self._checkpoints.upsert(version.project_id, version.primary_checkpoint)
            self._checkpoints.link(
                version.version_id,
                version.primary_checkpoint.checkpoint_id,
                is_primary=True,
            )
        return self.get(version.version_id) or version

    def replace(
        self,
        version: DevelopmentVersion,
        *,
        source_event: DevelopmentEvent | None = None,
    ) -> DevelopmentVersion:
        """Re-record an existing version in place (same id/number), replacing all
        derived data. Used by ``devmemory checkpoint --force``.
        """
        with self._db.transaction() as conn:
            # Child rows cascade on the version delete; do the version last.
            for table in (
                "changed_files",
                "tests",
                "metrics",
                "regressions",
                "analysis",
                "doc_flags",
                "version_checkpoints",
            ):
                conn.execute(f"DELETE FROM {table} WHERE version_id = ?", (version.version_id,))  # noqa: S608
            conn.execute("DELETE FROM versions WHERE version_id = ?", (version.version_id,))
            self._insert_version(conn, version, source_event)
            self._insert_changed_files(conn, version)
            self._insert_tests(conn, version)
            self._insert_metrics(conn, version)
            self._insert_regressions(conn, version)
            self._insert_analysis(conn, version)
            self._insert_doc_flags(conn, version)
            self._index_fts(conn, version)

        if version.primary_checkpoint is not None:
            self._checkpoints.upsert(version.project_id, version.primary_checkpoint)
            self._checkpoints.link(
                version.version_id,
                version.primary_checkpoint.checkpoint_id,
                is_primary=True,
            )
        return self.get(version.version_id) or version

    def replace_analysis(self, version_id: str, analysis: Analysis) -> None:
        version = self.get(version_id)
        if version is None:
            return
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM analysis WHERE version_id = ?", (version_id,))
            version.analysis = analysis
            self._insert_analysis(conn, version)
            self._index_fts(conn, version)

    def add_artifact(self, artifact: Artifact) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO artifacts "
                "(artifact_id, version_id, path, type, size_bytes, sha256, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact.artifact_id,
                    artifact.version_id,
                    artifact.path,
                    artifact.type,
                    artifact.size_bytes,
                    artifact.sha256,
                    _iso(artifact.created_at or _utcnow()),
                ),
            )

    # -- insert helpers --------------------------------------------

    def _insert_version(
        self,
        conn: sqlite3.Connection,
        v: DevelopmentVersion,
        event: DevelopmentEvent | None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO versions (
                version_number, version_id, project_id, intent, agent, model,
                git_commit, parent_commit, branch, feature_id, status,
                files_changed, lines_added, lines_removed,
                entire_association_method, entire_association_confidence,
                environment_json, source_event_json, run_id, created_at, committed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                v.version_number,
                v.version_id,
                v.project_id,
                v.intent,
                v.agent,
                v.model,
                v.git_commit,
                v.parent_commit,
                v.branch,
                v.feature_id,
                v.status.value,
                v.files_changed,
                v.lines_added,
                v.lines_removed,
                v.entire_association_method.value,
                v.entire_association_confidence,
                v.environment.model_dump_json() if v.environment else None,
                event.model_dump_json() if event else None,
                v.run_id,
                _iso(v.created_at),
                _iso(v.committed_at),
            ),
        )

    def _insert_changed_files(self, conn: sqlite3.Connection, v: DevelopmentVersion) -> None:
        conn.executemany(
            "INSERT INTO changed_files "
            "(version_id, path, old_path, change_type, additions, deletions, binary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    v.version_id,
                    f.path,
                    f.old_path,
                    f.change_type.value,
                    f.additions,
                    f.deletions,
                    1 if f.binary else 0,
                )
                for f in v.changed_files
            ],
        )

    def _insert_tests(self, conn: sqlite3.Connection, v: DevelopmentVersion) -> None:
        if v.tests is None or not v.tests.ran:
            return
        t = v.tests
        conn.execute(
            """
            INSERT INTO tests (version_id, command, framework, total, passed, failed,
                               skipped, errors, exit_code, duration_seconds, failing_json,
                               output, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                v.version_id,
                t.command,
                t.framework,
                t.total,
                t.passed,
                t.failed,
                t.skipped,
                t.errors,
                t.exit_code,
                t.duration_seconds,
                json.dumps(t.failing),
                t.output,
                _iso(_utcnow()),
            ),
        )

    def _insert_metrics(self, conn: sqlite3.Connection, v: DevelopmentVersion) -> None:
        conn.executemany(
            "INSERT INTO metrics (version_id, name, before_value, after_value, unit, "
            "direction, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    v.version_id,
                    m.name,
                    m.before,
                    m.after,
                    m.unit,
                    m.direction.value,
                    json.dumps(m.metadata) if m.metadata else None,
                )
                for m in v.metrics
            ],
        )

    def _insert_regressions(self, conn: sqlite3.Connection, v: DevelopmentVersion) -> None:
        conn.executemany(
            "INSERT INTO regressions (version_id, kind, metric, before_value, after_value, "
            "change_percent, severity, detail) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    v.version_id,
                    r.kind,
                    r.metric,
                    r.before,
                    r.after,
                    r.change_percent,
                    r.severity,
                    r.detail,
                )
                for r in v.regressions
            ],
        )

    def _insert_analysis(self, conn: sqlite3.Connection, v: DevelopmentVersion) -> None:
        if v.analysis is None:
            return
        a = v.analysis
        conn.execute(
            """
            INSERT INTO analysis (version_id, summary, reasoning, recommendation,
                                  warnings_json, risk, provider, model, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                v.version_id,
                a.summary,
                a.reasoning,
                a.recommendation,
                json.dumps(a.warnings),
                a.risk,
                a.provider,
                a.model,
                _iso(a.generated_at or _utcnow()),
            ),
        )

    def _insert_doc_flags(self, conn: sqlite3.Connection, v: DevelopmentVersion) -> None:
        conn.executemany(
            "INSERT INTO doc_flags (version_id, doc_path, reason) VALUES (?, ?, ?)",
            [(v.version_id, d.doc_path, d.reason) for d in v.doc_flags],
        )

    def _index_fts(self, conn: sqlite3.Connection, v: DevelopmentVersion) -> None:
        conn.execute("DELETE FROM version_search WHERE version_id = ?", (v.version_id,))
        files = " ".join(f.path for f in v.changed_files)
        errors = " ".join(
            (v.tests.failing if v.tests else []) + [r.detail or "" for r in v.regressions]
        )
        conn.execute(
            """
            INSERT INTO version_search (version_id, intent, feature, agent, model, status,
                                        files, commit_sha, checkpoint_id, analysis,
                                        recommendation, errors)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                v.version_id,
                v.intent or "",
                v.feature_id or "",
                v.agent or "",
                v.model or "",
                v.status.value,
                files,
                v.git_commit,
                " ".join(v.checkpoint_ids),
                (v.analysis.summary if v.analysis else ""),
                (v.analysis.recommendation if v.analysis and v.analysis.recommendation else ""),
                errors,
            ),
        )

    # -- read: hydration -----------------------------------------

    def _hydrate(self, row: sqlite3.Row) -> DevelopmentVersion:
        vid = row["version_id"]
        conn = self._db.connection

        changed_files = [
            ChangedFile(
                path=r["path"],
                old_path=r["old_path"],
                change_type=ChangeType(r["change_type"]),
                additions=r["additions"],
                deletions=r["deletions"],
                binary=bool(r["binary"]),
            )
            for r in conn.execute(
                "SELECT * FROM changed_files WHERE version_id = ? ORDER BY id", (vid,)
            )
        ]

        test_row = conn.execute(
            "SELECT * FROM tests WHERE version_id = ? ORDER BY id DESC LIMIT 1", (vid,)
        ).fetchone()
        tests = _test_from_row(test_row) if test_row else None

        metrics = [
            Metric(
                name=r["name"],
                before=r["before_value"],
                after=r["after_value"],
                unit=r["unit"],
                direction=MetricDirection(r["direction"] or MetricDirection.HIGHER_IS_BETTER.value),
                metadata=json.loads(r["metadata_json"]) if r["metadata_json"] else {},
            )
            for r in conn.execute("SELECT * FROM metrics WHERE version_id = ? ORDER BY id", (vid,))
        ]

        regressions = [
            Regression(
                version_id=vid,
                kind=r["kind"],
                metric=r["metric"],
                before=r["before_value"],
                after=r["after_value"],
                change_percent=r["change_percent"],
                severity=r["severity"],
                detail=r["detail"],
            )
            for r in conn.execute(
                "SELECT * FROM regressions WHERE version_id = ? ORDER BY id", (vid,)
            )
        ]

        analysis_row = conn.execute(
            "SELECT * FROM analysis WHERE version_id = ?", (vid,)
        ).fetchone()
        analysis = _analysis_from_row(analysis_row) if analysis_row else None

        artifacts = [
            Artifact(
                artifact_id=r["artifact_id"],
                version_id=vid,
                path=r["path"],
                type=r["type"],
                size_bytes=r["size_bytes"],
                sha256=r["sha256"],
                created_at=_dt(r["created_at"]),
            )
            for r in conn.execute(
                "SELECT * FROM artifacts WHERE version_id = ? ORDER BY created_at", (vid,)
            )
        ]

        doc_flags = [
            DocFlag(doc_path=r["doc_path"], reason=r["reason"])
            for r in conn.execute("SELECT * FROM doc_flags WHERE version_id = ?", (vid,))
        ]

        checkpoint_links = self._checkpoints.for_version(vid)
        primary = next((c for c, is_primary in checkpoint_links if is_primary), None)
        if primary is None and checkpoint_links:
            primary = checkpoint_links[0][0]

        env_raw = row["environment_json"]
        environment = EnvironmentInfo.model_validate_json(env_raw) if env_raw else None

        return DevelopmentVersion(
            version_id=vid,
            version_number=row["version_number"],
            project_id=row["project_id"],
            intent=row["intent"],
            agent=row["agent"],
            model=row["model"],
            git_commit=row["git_commit"],
            parent_commit=row["parent_commit"],
            branch=row["branch"],
            feature_id=row["feature_id"],
            status=VersionStatus(row["status"]),
            files_changed=row["files_changed"],
            lines_added=row["lines_added"],
            lines_removed=row["lines_removed"],
            changed_files=changed_files,
            primary_checkpoint=primary,
            checkpoint_ids=[c.checkpoint_id for c, _ in checkpoint_links],
            entire_association_method=AssociationMethod(
                row["entire_association_method"] or AssociationMethod.NONE.value
            ),
            entire_association_confidence=row["entire_association_confidence"] or 0.0,
            tests=tests,
            metrics=metrics,
            regressions=regressions,
            analysis=analysis,
            artifacts=artifacts,
            doc_flags=doc_flags,
            environment=environment,
            run_id=row["run_id"],
            created_at=_dt(row["created_at"]) or _utcnow(),
            committed_at=_dt(row["committed_at"]),
        )

    # -- search ------------------------------------------------

    def search_ids(self, project_id: str, query: str, *, limit: int = 50) -> list[str]:
        if not query.strip():
            return []
        try:
            rows = self._db.connection.execute(
                """
                SELECT s.version_id FROM version_search s
                JOIN versions v ON v.version_id = s.version_id
                WHERE v.project_id = ? AND version_search MATCH ?
                ORDER BY rank LIMIT ?
                """,
                (project_id, _fts_query(query), limit),
            ).fetchall()
        except sqlite3.OperationalError:
            like = f"%{query}%"
            rows = self._db.connection.execute(
                """
                SELECT version_id FROM versions
                WHERE project_id = ? AND (intent LIKE ? OR agent LIKE ? OR git_commit LIKE ?)
                ORDER BY version_number DESC LIMIT ?
                """,
                (project_id, like, like, like, limit),
            ).fetchall()
        return [r["version_id"] for r in rows]


def _fts_query(raw: str) -> str:
    """Make user input safe for FTS5 MATCH: quote each bare term, keep it prefix-y."""
    terms = [t for t in raw.replace('"', " ").split() if t]
    return " ".join(f'"{t}"*' if t.isalnum() else f'"{t}"' for t in terms) or '""'


def _test_from_row(row: sqlite3.Row) -> TestOutcome:
    return TestOutcome(
        command=row["command"],
        framework=row["framework"],
        total=row["total"],
        passed=row["passed"],
        failed=row["failed"],
        skipped=row["skipped"],
        errors=row["errors"],
        exit_code=row["exit_code"],
        duration_seconds=row["duration_seconds"],
        failing=json.loads(row["failing_json"]) if row["failing_json"] else [],
        output=row["output"],
    )


def _analysis_from_row(row: sqlite3.Row) -> Analysis:
    return Analysis(
        version_id=row["version_id"],
        summary=row["summary"] or "",
        reasoning=row["reasoning"],
        recommendation=row["recommendation"],
        warnings=json.loads(row["warnings_json"]) if row["warnings_json"] else [],
        risk=row["risk"],
        provider=row["provider"],
        model=row["model"],
        generated_at=_dt(row["generated_at"]),
    )


__all__ = ["VersionRepository"]
