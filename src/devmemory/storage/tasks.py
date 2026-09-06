"""Data access for the state-aware coding loop (migration 0004).

Follows the same rules as :mod:`devmemory.storage.repositories`: every SQL
statement for tasks / requirements / issues / test runs / state snapshots lives
here, and methods return :mod:`devmemory.domain.taskloop` models.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from devmemory.domain.enums import IssueStatus, RequirementStatus, TaskStatus, TestRunStatus
from devmemory.domain.taskloop import (
    Issue,
    NormalizedState,
    Requirement,
    StateSnapshot,
    Task,
    TaskTestRun,
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


class TaskRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    # -- tasks ---------------------------------------------------------------

    def next_task_id(self) -> str:
        row = self._db.query_one("SELECT COUNT(*) AS n FROM tasks")
        return f"TASK-{(int(row['n']) if row else 0) + 1:03d}"

    def create(self, task: Task) -> Task:
        now = _utcnow()
        with self._db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, goal, status, branch, base_commit, test_command,
                                   push_policy, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    task.goal,
                    task.status.value,
                    task.branch,
                    task.base_commit,
                    task.test_command,
                    task.push_policy,
                    now,
                    now,
                ),
            )
            for pos, req in enumerate(task.requirements):
                conn.execute(
                    """
                    INSERT INTO requirements (task_id, req_id, description, status, reason,
                                              evidence_json, evaluated_at, evaluated_by, position)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.id,
                        req.id,
                        req.description,
                        req.status.value,
                        req.reason,
                        json.dumps(req.evidence),
                        req.evaluated_at.isoformat() if req.evaluated_at else None,
                        req.evaluated_by,
                        pos,
                    ),
                )
        return self.get(task.id)  # type: ignore[return-value]

    def get(self, task_id: str) -> Task | None:
        row = self._db.query_one("SELECT * FROM tasks WHERE id = ?", (task_id,))
        if row is None:
            return None
        return Task(
            id=row["id"],
            goal=row["goal"],
            status=TaskStatus(row["status"]),
            branch=row["branch"],
            base_commit=row["base_commit"],
            test_command=row["test_command"],
            push_policy=row["push_policy"],
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
            requirements=self.requirements(task_id),
        )

    def list_tasks(self) -> list[Task]:
        rows = self._db.query("SELECT id FROM tasks ORDER BY created_at")
        return [t for r in rows if (t := self.get(r["id"])) is not None]

    def latest(self) -> Task | None:
        row = self._db.query_one("SELECT id FROM tasks ORDER BY created_at DESC LIMIT 1")
        return self.get(row["id"]) if row else None

    def set_status(self, task_id: str, status: TaskStatus) -> None:
        self._db.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status.value, _utcnow(), task_id),
        )

    # -- requirements ------------------------------------------------------

    def requirements(self, task_id: str) -> list[Requirement]:
        rows = self._db.query(
            "SELECT * FROM requirements WHERE task_id = ? ORDER BY position, req_id",
            (task_id,),
        )
        out: list[Requirement] = []
        for row in rows:
            try:
                evidence = json.loads(row["evidence_json"]) or []
            except (json.JSONDecodeError, TypeError):
                evidence = []
            out.append(
                Requirement(
                    id=row["req_id"],
                    description=row["description"],
                    status=RequirementStatus(row["status"]),
                    reason=row["reason"],
                    evidence=list(evidence),
                    evaluated_at=_dt(row["evaluated_at"]),
                    evaluated_by=row["evaluated_by"],
                )
            )
        return out

    def update_requirement(self, task_id: str, req: Requirement) -> None:
        self._db.execute(
            """
            UPDATE requirements
               SET status = ?, reason = ?, evidence_json = ?, evaluated_at = ?, evaluated_by = ?
             WHERE task_id = ? AND req_id = ?
            """,
            (
                req.status.value,
                req.reason,
                json.dumps(req.evidence),
                req.evaluated_at.isoformat() if req.evaluated_at else _utcnow(),
                req.evaluated_by,
                task_id,
                req.id,
            ),
        )

    # -- issues ----------------------------------------------------------

    def add_issue(self, issue: Issue) -> Issue:
        now = _utcnow()
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO issues (task_id, description, kind, blocking, status, created_at)
                VALUES (?, ?, ?, ?, 'OPEN', ?)
                """,
                (issue.task_id, issue.description, issue.kind, int(issue.blocking), now),
            )
            issue_id = int(cur.lastrowid or 0)
        return issue.model_copy(update={"id": issue_id, "created_at": _dt(now)})

    def open_issues(self, task_id: str) -> list[Issue]:
        rows = self._db.query(
            "SELECT * FROM issues WHERE task_id = ? AND status = 'OPEN' ORDER BY created_at",
            (task_id,),
        )
        return [
            Issue(
                id=row["id"],
                task_id=row["task_id"],
                description=row["description"],
                kind=row["kind"],
                blocking=bool(row["blocking"]),
                status=IssueStatus(row["status"]),
                created_at=_dt(row["created_at"]),
                resolved_at=_dt(row["resolved_at"]),
            )
            for row in rows
        ]

    def resolve_issue(self, issue_id: int) -> bool:
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE issues SET status = 'RESOLVED', resolved_at = ? WHERE id = ? AND status = 'OPEN'",
                (_utcnow(), issue_id),
            )
            return cur.rowcount > 0

    def resolve_issues_by_kind(self, task_id: str, kind: str) -> int:
        """Auto-close engine-raised issues of one kind before re-raising fresh ones."""
        with self._db.transaction() as conn:
            cur = conn.execute(
                "UPDATE issues SET status = 'RESOLVED', resolved_at = ? "
                "WHERE task_id = ? AND kind = ? AND status = 'OPEN'",
                (_utcnow(), task_id, kind),
            )
            return cur.rowcount

    # -- test runs -----------------------------------------------------

    def add_test_run(self, run: TaskTestRun) -> TaskTestRun:
        now = _utcnow()
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO task_test_runs (task_id, command, status, passed, failed, skipped,
                                            exit_code, duration_seconds, output_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.task_id,
                    run.command,
                    run.status.value,
                    run.passed,
                    run.failed,
                    run.skipped,
                    run.exit_code,
                    run.duration_seconds,
                    run.output_path,
                    now,
                ),
            )
            run_id = int(cur.lastrowid or 0)
        return run.model_copy(update={"id": run_id, "created_at": _dt(now)})

    def latest_test_run(self, task_id: str) -> TaskTestRun | None:
        row = self._db.query_one(
            "SELECT * FROM task_test_runs WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        if row is None:
            return None
        return TaskTestRun(
            id=row["id"],
            task_id=row["task_id"],
            command=row["command"],
            status=TestRunStatus(row["status"]),
            passed=row["passed"],
            failed=row["failed"],
            skipped=row["skipped"],
            exit_code=row["exit_code"],
            duration_seconds=row["duration_seconds"],
            output_path=row["output_path"],
            created_at=_dt(row["created_at"]),
        )

    # -- state snapshots (the observable loop) ------------------------

    def append_snapshot(self, state: NormalizedState) -> StateSnapshot:
        now = _utcnow()
        with self._db.transaction() as conn:
            cur = conn.execute(
                """
                INSERT INTO state_snapshots (task_id, overall_status, commit_sha, checkpoint_id,
                                             state_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    state.task.id,
                    state.overall_status.value,
                    state.git.commit_sha,
                    state.checkpoint.current_id,
                    state.model_dump_json(),
                    now,
                ),
            )
            snap_id = int(cur.lastrowid or 0)
        return StateSnapshot(
            id=snap_id,
            task_id=state.task.id,
            overall_status=state.overall_status,
            state=state,
            created_at=_dt(now),
        )

    def latest_snapshot(self, task_id: str) -> StateSnapshot | None:
        row = self._db.query_one(
            "SELECT * FROM state_snapshots WHERE task_id = ? ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        )
        return _snapshot_from_row(row)

    def snapshots(self, task_id: str, *, limit: int = 20) -> list[StateSnapshot]:
        rows = self._db.query(
            "SELECT * FROM state_snapshots WHERE task_id = ? ORDER BY created_at DESC LIMIT ?",
            (task_id, limit),
        )
        return [s for row in rows if (s := _snapshot_from_row(row)) is not None]

    # -- task <-> commit index --------------------------------------

    def link_commit(self, task_id: str, commit_sha: str) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO task_commits (task_id, commit_sha, created_at) VALUES (?, ?, ?)",
            (task_id, commit_sha, _utcnow()),
        )

    def task_commits(self, task_id: str) -> list[str]:
        rows = self._db.query(
            "SELECT commit_sha FROM task_commits WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )
        return [r["commit_sha"] for r in rows]


def _snapshot_from_row(row: sqlite3.Row | None) -> StateSnapshot | None:
    if row is None:
        return None
    try:
        state = NormalizedState.model_validate_json(row["state_json"])
    except ValueError:
        return None
    state.snapshot_id = row["id"]  # the id is a property of the row, injected on read
    return StateSnapshot(
        id=row["id"],
        task_id=row["task_id"],
        overall_status=TaskStatus(row["overall_status"]),
        state=state,
        created_at=_dt(row["created_at"]),
    )


__all__ = ["TaskRepository"]
