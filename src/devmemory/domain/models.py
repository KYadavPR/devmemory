"""Typed domain models.

Pure data + light behaviour. No I/O, no framework imports. These are the shapes
adapters produce, services operate on, and the API/MCP layers serialize.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from devmemory.domain.enums import (
    AssociationMethod,
    ChangeType,
    FeatureStatus,
    MetricDirection,
    VersionStatus,
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


# --- git ---------------------------------------------------------------------------


class CommitInfo(_Model):
    """A resolved git commit. Facts only - straight from ``git``."""

    sha: str
    parents: list[str] = Field(default_factory=list)
    author_name: str = ""
    author_email: str = ""
    authored_at: datetime | None = None
    committer_name: str = ""
    committer_email: str = ""
    committed_at: datetime | None = None
    subject: str = ""
    body: str = ""
    trailers: dict[str, list[str]] = Field(default_factory=dict)

    @property
    def short_sha(self) -> str:
        return self.sha[:12]

    @property
    def parent(self) -> str | None:
        """First parent, or ``None`` for a root commit."""
        return self.parents[0] if self.parents else None

    @property
    def is_merge(self) -> bool:
        return len(self.parents) > 1

    @property
    def message(self) -> str:
        return f"{self.subject}\n\n{self.body}".strip() if self.body else self.subject

    def trailer(self, key: str) -> str | None:
        """First value of a git trailer (case-insensitive), or ``None``."""
        lowered = key.lower()
        for name, values in self.trailers.items():
            if name.lower() == lowered and values:
                return values[0]
        return None


class ChangedFile(_Model):
    """One file's change between two commits."""

    path: str
    change_type: ChangeType
    old_path: str | None = None
    additions: int = 0
    deletions: int = 0
    binary: bool = False

    @property
    def net_lines(self) -> int:
        return self.additions - self.deletions


class DiffStat(_Model):
    """Aggregate line/file counts for a diff."""

    files_changed: int = 0
    additions: int = 0
    deletions: int = 0

    @classmethod
    def from_files(cls, files: list[ChangedFile]) -> DiffStat:
        return cls(
            files_changed=len(files),
            additions=sum(f.additions for f in files),
            deletions=sum(f.deletions for f in files),
        )


class WorkingTreeState(_Model):
    """Snapshot of ``git status`` relevant to safe operations."""

    branch: str | None = None
    detached: bool = False
    head: str | None = None
    staged: list[str] = Field(default_factory=list)
    unstaged: list[str] = Field(default_factory=list)
    untracked: list[str] = Field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not (self.staged or self.unstaged or self.untracked)

    @property
    def has_uncommitted_changes(self) -> bool:
        return bool(self.staged or self.unstaged)


# --- entire ----------------------------------------------------------------------


class TokenUsage(_Model):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    api_call_count: int = 0

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_creation_tokens
        )


class CheckpointSession(_Model):
    """One AI session inside a checkpoint."""

    session_id: str | None = None
    agent: str | None = None
    model: str | None = None
    kind: str | None = None
    created_at: datetime | None = None
    tokens: TokenUsage = Field(default_factory=TokenUsage)


class CheckpointReference(_Model):
    """DevMemory's normalized view of an Entire checkpoint.

    A reference plus the small amount of normalized context we display and search.
    The full transcript stays in Entire's git refs.
    """

    checkpoint_id: str
    commit_sha: str | None = None
    intent: str | None = None
    """The developer's prompt (from ``<idx>/prompt.txt``), trimmed for storage."""
    agent: str | None = None
    model: str | None = None
    strategy: str | None = None
    created_at: datetime | None = None
    sessions: list[CheckpointSession] = Field(default_factory=list)
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    association_method: AssociationMethod = AssociationMethod.NONE
    association_confidence: float = 0.0
    ref: str | None = None
    """The git ref (``refs/entire/checkpoints/<shard>/<id>``) when known."""
    imported: bool = False

    @property
    def is_linked(self) -> bool:
        return self.association_method is not AssociationMethod.NONE

    @property
    def is_uncertain(self) -> bool:
        return 0.0 < self.association_confidence < 0.8


class EntireStatus(_Model):
    """Result of probing the Entire integration for a repository."""

    installed: bool = False
    enabled: bool = False
    cli_version: str | None = None
    agents: list[str] = Field(default_factory=list)
    binary_path: str | None = None
    detail: str | None = None


# --- project ----------------------------------------------------------------------


class Project(_Model):
    """One repository tracked by DevMemory."""

    project_id: str
    name: str
    repo_path: str
    created_at: datetime
    updated_at: datetime
    current_version_id: int | None = None


class EnvironmentInfo(_Model):
    """Best-effort snapshot of the toolchain, attached to versions later."""

    python_version: str
    platform: str
    machine: str
    git_version: str | None = None
    entire_version: str | None = None
    package_manager: str | None = None


# --- results (facts) ------------------------------------------------------------------


class TestOutcome(_Model):
    """Outcome of running the configured test command. Facts, not judgement."""

    __test__ = False  # this is a data model, not a pytest test case

    command: str | None = None
    framework: str | None = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    exit_code: int | None = None
    duration_seconds: float | None = None
    failing: list[str] = Field(default_factory=list)
    output: str | None = None

    @property
    def ran(self) -> bool:
        return self.command is not None

    @property
    def all_passed(self) -> bool:
        return self.ran and self.failed == 0 and self.errors == 0 and self.exit_code in (0, None)

    @property
    def pass_rate(self) -> float | None:
        return self.passed / self.total if self.total else None


class Metric(_Model):
    """One measurable project metric, with an explicit better-direction."""

    name: str
    before: float | None = None
    after: float | None = None
    unit: str | None = None
    direction: MetricDirection = MetricDirection.HIGHER_IS_BETTER
    metadata: dict[str, object] = Field(default_factory=dict)

    @property
    def delta(self) -> float | None:
        if self.before is None or self.after is None:
            return None
        return self.after - self.before

    @property
    def percent_change(self) -> float | None:
        if self.before is None or self.after is None or self.before == 0:
            return None
        return (self.after - self.before) / abs(self.before) * 100.0

    @property
    def is_improvement(self) -> bool:
        delta = self.delta
        if delta is None or delta == 0 or self.direction is MetricDirection.NEUTRAL:
            return False
        return delta > 0 if self.direction is MetricDirection.HIGHER_IS_BETTER else delta < 0

    @property
    def is_worse(self) -> bool:
        delta = self.delta
        if delta is None or delta == 0 or self.direction is MetricDirection.NEUTRAL:
            return False
        return delta < 0 if self.direction is MetricDirection.HIGHER_IS_BETTER else delta > 0


class Regression(_Model):
    version_id: str | None = None
    kind: str  # 'metric' | 'test'
    metric: str | None = None
    before: float | None = None
    after: float | None = None
    change_percent: float | None = None
    severity: str = "MEDIUM"  # LOW | MEDIUM | HIGH
    detail: str | None = None


class Analysis(_Model):
    """AI (or rule-based) interpretation. Never overwrites facts."""

    version_id: str | None = None
    summary: str = ""
    reasoning: str | None = None
    recommendation: str | None = None
    warnings: list[str] = Field(default_factory=list)
    risk: str | None = None
    provider: str = "rules"
    model: str | None = None
    generated_at: datetime | None = None


class Artifact(_Model):
    artifact_id: str
    version_id: str
    path: str
    type: str = "project_snapshot"
    size_bytes: int | None = None
    sha256: str | None = None
    created_at: datetime | None = None


class DocFlag(_Model):
    doc_path: str
    reason: str | None = None


class Feature(_Model):
    feature_id: str
    project_id: str
    name: str
    status: FeatureStatus = FeatureStatus.IN_PROGRESS
    derived_from: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# --- the normalized bridge --------------------------------------------------------


class DevelopmentEvent(_Model):
    """Everything collected about one development change, normalized.

    Adapters fill this; the version registry persists it. It is stored verbatim on
    the version (``source_event_json``) for replay and debugging.
    """

    project_id: str
    source: str = "devmemory"
    occurred_at: datetime
    run_id: str | None = None

    intent: str | None = None
    agent: str | None = None
    model: str | None = None
    feature: str | None = None
    feature_derived_from: str | None = None

    commit: CommitInfo
    parent_commit: str | None = None
    branch: str | None = None
    changed_files: list[ChangedFile] = Field(default_factory=list)

    checkpoint: CheckpointReference | None = None

    status: VersionStatus | None = None
    tests: TestOutcome | None = None
    metrics: list[Metric] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    environment: EnvironmentInfo | None = None

    @property
    def diff_stat(self) -> DiffStat:
        return DiffStat.from_files(self.changed_files)


# --- the record ----------------------------------------------------------------


class DevelopmentVersion(_Model):
    """The persisted development record - the join of everything above."""

    version_id: str
    version_number: int
    project_id: str

    intent: str | None = None
    agent: str | None = None
    model: str | None = None

    git_commit: str
    parent_commit: str | None = None
    branch: str | None = None

    feature_id: str | None = None
    status: VersionStatus = VersionStatus.NEEDS_REVIEW

    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0

    changed_files: list[ChangedFile] = Field(default_factory=list)
    primary_checkpoint: CheckpointReference | None = None
    checkpoint_ids: list[str] = Field(default_factory=list)

    entire_association_method: AssociationMethod = AssociationMethod.NONE
    entire_association_confidence: float = 0.0

    tests: TestOutcome | None = None
    metrics: list[Metric] = Field(default_factory=list)
    regressions: list[Regression] = Field(default_factory=list)
    analysis: Analysis | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    doc_flags: list[DocFlag] = Field(default_factory=list)

    environment: EnvironmentInfo | None = None
    run_id: str | None = None

    created_at: datetime
    committed_at: datetime | None = None

    @property
    def net_lines(self) -> int:
        return self.lines_added - self.lines_removed

    @property
    def has_uncertain_checkpoint(self) -> bool:
        return bool(self.primary_checkpoint and self.primary_checkpoint.is_uncertain)


__all__ = [
    "Analysis",
    "Artifact",
    "ChangedFile",
    "CheckpointReference",
    "CheckpointSession",
    "CommitInfo",
    "DevelopmentEvent",
    "DevelopmentVersion",
    "DiffStat",
    "DocFlag",
    "EntireStatus",
    "EnvironmentInfo",
    "Feature",
    "Metric",
    "Project",
    "Regression",
    "TestOutcome",
    "TokenUsage",
    "WorkingTreeState",
]
