"""Typed domain models.

Pure data + light behaviour. No I/O, no framework imports. These are the shapes
adapters produce, services operate on, and the API/MCP layers serialize.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from devmemory.domain.enums import AssociationMethod, ChangeType


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


__all__ = [
    "ChangedFile",
    "CheckpointReference",
    "CheckpointSession",
    "CommitInfo",
    "DiffStat",
    "EntireStatus",
    "EnvironmentInfo",
    "Project",
    "TokenUsage",
    "WorkingTreeState",
]
