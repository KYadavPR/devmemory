"""API response models. Domain models are reused where they already serialize
cleanly; these add dashboard-shaped aggregates."""

from __future__ import annotations

from pydantic import BaseModel

from devmemory.domain.models import ChangedFile, DiffStat


class ProjectSummary(BaseModel):
    project_id: str
    name: str
    repo_path: str
    branch: str | None
    head_sha: str | None
    head_subject: str | None
    working_tree_clean: bool
    version_count: int
    latest_version_id: str | None
    latest_status: str | None
    latest_intent: str | None
    head_has_version: bool
    last_regression_id: str | None
    open_features: list[str]
    latest_metrics: dict[str, float | None]
    entire_installed: bool
    entire_enabled: bool
    entire_version: str | None
    entire_agents: list[str]


class VersionListItem(BaseModel):
    version_id: str
    version_number: int
    status: str
    intent: str | None
    agent: str | None
    model: str | None
    feature: str | None
    git_commit: str
    branch: str | None
    files_changed: int
    lines_added: int
    lines_removed: int
    checkpoint_id: str | None
    association_method: str
    association_confidence: float
    metrics: dict[str, float | None]
    tests_passed: int | None
    tests_failed: int | None
    has_regression: bool
    committed_at: str | None
    created_at: str


class MetricChange(BaseModel):
    name: str
    before: float | None
    after: float | None
    delta: float | None
    unit: str | None
    direction: str


class ComparisonResponse(BaseModel):
    from_version: str
    to_version: str
    from_commit: str
    to_commit: str
    stat: DiffStat
    files: list[ChangedFile]
    diff_text: str
    metric_changes: list[MetricChange]
    test_changes: dict[str, int | None]
    status_from: str
    status_to: str
    feature_from: str | None = None
    feature_to: str | None = None
    checkpoint_from: str | None = None
    checkpoint_to: str | None = None


class FeatureHistoryPoint(BaseModel):
    version_id: str
    version_number: int
    status: str
    metrics: dict[str, float | None]
    committed_at: str | None


class FeatureDetail(BaseModel):
    feature_id: str
    name: str
    status: str
    derived_from: str | None
    version_count: int
    latest_metrics: dict[str, float | None]
    history: list[FeatureHistoryPoint]


class SearchHit(BaseModel):
    version_id: str
    version_number: int
    status: str
    intent: str | None
    agent: str | None
    feature: str | None
    git_commit: str
    snippet: str | None = None


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list[SearchHit]


class AgentCheckRequest(BaseModel):
    """Body for ``POST /api/agent/check`` - the pre-flight risk read."""

    files: list[str] = []
    intent: str | None = None
    feature: str | None = None
    symbols: list[str] = []  # names or path/to/file.py:line - graph blast radius


# --- state-aware coding loop ---------------------------------------------------


class TaskCreateRequest(BaseModel):
    goal: str
    test_command: str | None = None


class IssueRequest(BaseModel):
    description: str
    blocking: bool = False


class RequirementUpdateRequest(BaseModel):
    status: str
    note: str = ""


class TaskSummary(BaseModel):
    """One row in the tasks list."""

    id: str
    goal: str
    status: str
    branch: str
    requirements_total: int
    requirements_complete: int
    test_command: str | None
    updated_at: str | None


class SnapshotSummary(BaseModel):
    """One point on a task's state timeline (the full state stays server-side)."""

    id: int | None
    overall_status: str
    commit_sha: str | None
    checkpoint_id: str | None
    tests_passed: int
    tests_failed: int
    tests_status: str
    requirements_total: int
    requirements_complete: int
    created_at: str | None


class ProjectBriefDoc(BaseModel):
    """The project's single source of truth: one editable markdown document."""

    content: str
    updated_at: str | None


class ProjectBriefRequest(BaseModel):
    content: str


class GenieAskRequest(BaseModel):
    """One turn in the dashboard's Ask chat."""

    question: str
    conversation_id: str | None = None


class GenieStatus(BaseModel):
    configured: bool
    mode: str = "none"
    """Which engine answers questions: ``genie`` | ``local`` | ``rules`` | ``none``."""
    engine: str | None = None
    """Human-readable label for the active engine."""
    space_id: str | None = None
    reason: str | None = None


__all__ = [
    "AgentCheckRequest",
    "ComparisonResponse",
    "FeatureDetail",
    "FeatureHistoryPoint",
    "GenieAskRequest",
    "GenieStatus",
    "IssueRequest",
    "MetricChange",
    "ProjectBriefDoc",
    "ProjectBriefRequest",
    "ProjectSummary",
    "RequirementUpdateRequest",
    "SearchHit",
    "SearchResponse",
    "SnapshotSummary",
    "TaskCreateRequest",
    "TaskSummary",
    "VersionListItem",
]
