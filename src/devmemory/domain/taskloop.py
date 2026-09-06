"""Models for the state-aware coding loop.

A :class:`Task` is a live, multi-commit unit of work carrying an explicit list of
:class:`Requirement` s. It is deliberately *not* a ``DevelopmentVersion`` (which
is a post-commit record of one change): a task spans many commits, many
checkpoints, and many refreshes.

Every ``refresh_state`` call aggregates fresh evidence - Git, Entire, tests,
optional Graph - into one :class:`NormalizedState` and appends a
:class:`StateSnapshot`, so the loop is observable as State #1 -> #2 -> #3.

Nothing here interprets *how* code should be written. The engine reports
evidence; Antigravity decides implementation.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from devmemory.domain.enums import (
    IssueStatus,
    RequirementStatus,
    TaskStatus,
    TestRunStatus,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- persisted entities --------------------------------------------------------


class Requirement(_Model):
    """One normalized, checkable slice of the human task."""

    id: str  # "R1", "R2", ...
    description: str
    status: RequirementStatus = RequirementStatus.INCOMPLETE
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)
    evaluated_at: datetime | None = None
    evaluated_by: str = ""  # "rules" | "anthropic" | "openai" | "gemini" | "manual"


class Task(_Model):
    """The original human task, preserved verbatim in ``goal``."""

    id: str  # "TASK-001"
    goal: str
    status: TaskStatus = TaskStatus.IN_PROGRESS
    branch: str = "main"
    base_commit: str | None = None  # HEAD when the task was created
    test_command: str | None = None
    push_policy: str = "manual"  # "manual" | "on_ready" | "never"
    created_at: datetime | None = None
    updated_at: datetime | None = None
    requirements: list[Requirement] = Field(default_factory=list)


class Issue(_Model):
    """An unresolved item raised by the agent (``report_issue``) or the engine."""

    id: int | None = None
    task_id: str
    description: str
    kind: str = "agent"  # "agent" | "test" | "requirement" | "engine"
    blocking: bool = False
    status: IssueStatus = IssueStatus.OPEN
    created_at: datetime | None = None
    resolved_at: datetime | None = None


class TaskTestRun(_Model):
    """One execution of the configured test command during a refresh."""

    id: int | None = None
    task_id: str
    command: str
    status: TestRunStatus
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    exit_code: int | None = None
    duration_seconds: float | None = None
    output_path: str | None = None
    created_at: datetime | None = None


# --- the normalized state (the MCP payload) -----------------------------------


class StateTask(_Model):
    id: str
    goal: str
    status: TaskStatus


class StateRequirement(_Model):
    id: str
    description: str
    status: RequirementStatus
    reason: str = ""


class StateCheckpoint(_Model):
    current_id: str | None = None
    last_committed_id: str | None = None
    session_id: str | None = None
    commit_sha: str | None = None
    association: str | None = None  # how it was linked (trailer / entire_cli / ...)


class StateGit(_Model):
    branch: str = "main"
    commit_sha: str | None = None
    commit_subject: str | None = None
    files_changed: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    working_tree_clean: bool = False
    available: bool = True
    reason: str | None = None  # set when available is False


class StateTests(_Model):
    command: str | None = None
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    status: TestRunStatus = TestRunStatus.NOT_RUN
    exit_code: int | None = None
    output_path: str | None = None


class StateImpact(_Model):
    affected_files: int = 0
    affected_tests: int = 0
    available: bool = False
    reason: str | None = None
    details: list[str] = Field(default_factory=list)


class StateIssue(_Model):
    id: int | None = None
    description: str
    kind: str = "agent"
    blocking: bool = False


class NormalizedState(_Model):
    """The single machine-readable project state handed to Antigravity.

    Compact by design - it orients the agent; the agent still inspects the real
    repository with its own tools.
    """

    task: StateTask
    requirements: list[StateRequirement] = Field(default_factory=list)
    checkpoint: StateCheckpoint = Field(default_factory=StateCheckpoint)
    git: StateGit = Field(default_factory=StateGit)
    tests: StateTests = Field(default_factory=StateTests)
    impact: StateImpact = Field(default_factory=StateImpact)
    unresolved: list[StateIssue] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    recommended_focus: list[str] = Field(default_factory=list)
    overall_status: TaskStatus = TaskStatus.IN_PROGRESS
    snapshot_id: int | None = None
    refreshed_at: datetime | None = None


class StateSnapshot(_Model):
    """A stored, timestamped :class:`NormalizedState`. One per refresh."""

    id: int | None = None
    task_id: str
    overall_status: TaskStatus
    state: NormalizedState
    created_at: datetime | None = None


# --- requirement evaluation (structured, auditable) --------------------------


class RequirementVerdict(_Model):
    """One requirement's evaluation result - structured and auditable per §5."""

    requirement_id: str
    status: RequirementStatus
    reason: str
    evidence: list[str] = Field(default_factory=list)


__all__ = [
    "Issue",
    "NormalizedState",
    "Requirement",
    "RequirementVerdict",
    "StateCheckpoint",
    "StateGit",
    "StateImpact",
    "StateIssue",
    "StateRequirement",
    "StateSnapshot",
    "StateTask",
    "StateTests",
    "Task",
    "TaskTestRun",
]
