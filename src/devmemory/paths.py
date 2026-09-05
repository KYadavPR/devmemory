"""Filesystem layout for a DevMemory-tracked project.

Everything DevMemory writes into a target repository lives under a single hidden
directory, ``.devmemory/``. This module is the one place that knows its shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEVMEMORY_DIRNAME = ".devmemory"
CONFIG_FILENAME = "config.json"
CONFIG_LOCAL_FILENAME = "config.local.json"
DB_FILENAME = "metadata.db"


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Resolved absolute paths for one project's DevMemory data."""

    repo_root: Path
    """The project/repository root - the parent of ``.devmemory/``."""

    root: Path
    """The ``.devmemory/`` directory itself."""

    config: Path
    """Committed, non-secret configuration (``.devmemory/config.json``)."""

    config_local: Path
    """Git-ignored local overrides (``.devmemory/config.local.json``)."""

    db: Path
    """SQLite metadata database."""

    versions_dir: Path
    """Human-readable per-version JSON mirrors."""

    artifacts_dir: Path
    """Compressed project snapshots."""

    outbox_dir: Path
    """Pending Databricks events awaiting sync."""

    runs_dir: Path
    """Structured logs, one file per ``devmemory checkpoint`` run."""

    cache_dir: Path
    """Derived data that can be safely deleted (diffs, graph results)."""

    @classmethod
    def for_root(cls, repo_root: Path) -> ProjectPaths:
        repo_root = repo_root.resolve()
        root = repo_root / DEVMEMORY_DIRNAME
        return cls(
            repo_root=repo_root,
            root=root,
            config=root / CONFIG_FILENAME,
            config_local=root / CONFIG_LOCAL_FILENAME,
            db=root / DB_FILENAME,
            versions_dir=root / "versions",
            artifacts_dir=root / "artifacts",
            outbox_dir=root / "outbox",
            runs_dir=root / "runs",
            cache_dir=root / "cache",
        )

    def ensure_scaffold(self) -> None:
        """Create every directory in the layout. Idempotent."""
        for directory in (
            self.root,
            self.versions_dir,
            self.artifacts_dir,
            self.outbox_dir,
            self.runs_dir,
            self.cache_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def exists(self) -> bool:
        return self.root.is_dir()


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk upward from ``start`` (default: cwd) looking for a ``.devmemory/`` dir.

    Returns the containing directory, or ``None`` if the filesystem root is
    reached without finding one.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / DEVMEMORY_DIRNAME).is_dir():
            return candidate
    return None


def find_project_paths(start: Path | None = None) -> ProjectPaths | None:
    root = find_project_root(start)
    return ProjectPaths.for_root(root) if root is not None else None


__all__ = [
    "CONFIG_FILENAME",
    "CONFIG_LOCAL_FILENAME",
    "DB_FILENAME",
    "DEVMEMORY_DIRNAME",
    "ProjectPaths",
    "find_project_paths",
    "find_project_root",
]
