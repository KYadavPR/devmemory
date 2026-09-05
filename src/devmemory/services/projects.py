"""Project lifecycle: ``init`` and ``status``."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from devmemory.adapters.git import GitAdapter
from devmemory.config import DevMemoryConfig
from devmemory.domain.errors import (
    GitRepositoryNotFoundError,
    ProjectAlreadyInitializedError,
)
from devmemory.domain.models import EntireStatus, EnvironmentInfo, Project
from devmemory.environment import collect_environment
from devmemory.logging import get_logger
from devmemory.paths import DEVMEMORY_DIRNAME, ProjectPaths
from devmemory.services.context import ProjectContext
from devmemory.storage.repositories import ProjectRepository

_log = get_logger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.strip().lower()).strip("-")
    return slug or "project"


class InitReport(BaseModel):
    project: Project
    config_path: str
    db_path: str
    git_detected: bool
    git_version: str | None
    entire: EntireStatus
    environment: EnvironmentInfo
    gitignore_updated: bool


class ProjectStatusReport(BaseModel):
    project: Project
    branch: str | None
    head_sha: str | None
    head_subject: str | None
    working_tree_clean: bool
    entire: EntireStatus
    version_count: int = 0
    current_version_id: int | None = None


def init_project(
    repo_path: Path | str,
    *,
    name: str | None = None,
    project_id: str | None = None,
    force: bool = False,
    entire_probe: EntireStatus | None = None,
) -> InitReport:
    """Create ``.devmemory/`` for a repository and register the project."""
    repo_path = Path(repo_path).resolve()

    git = GitAdapter(repo_path)
    if not git.is_repository():
        raise GitRepositoryNotFoundError(
            f"{repo_path} is not inside a git repository.",
        )
    repo_root = git.repo_root()
    paths = ProjectPaths.for_root(repo_root)

    if paths.exists and not force:
        raise ProjectAlreadyInitializedError(
            f"DevMemory is already initialized at {paths.root}.",
            hint="Pass --force to re-create the configuration (history is preserved).",
        )

    paths.ensure_scaffold()

    resolved_name = name or repo_root.name
    resolved_id = slugify(project_id or resolved_name)

    config = _load_or_default_config(paths, project_id=resolved_id, project_name=resolved_name)
    config.save(paths)

    ctx = ProjectContext.for_paths(paths, config)
    try:
        repo = ProjectRepository(ctx.db)
        project = repo.get_by_id(resolved_id)
        if project is None:
            project = repo.create(
                project_id=resolved_id,
                name=resolved_name,
                repo_path=str(repo_root),
            )
    finally:
        ctx.close()

    gitignore_updated = _ensure_repo_gitignore(repo_root)
    entire = entire_probe or EntireStatus()

    _log.info(
        "project.init",
        project_id=resolved_id,
        repo=str(repo_root),
        force=force,
    )

    return InitReport(
        project=project,
        config_path=str(paths.config),
        db_path=str(paths.db),
        git_detected=True,
        git_version=git.git_version(),
        entire=entire,
        environment=collect_environment(repo_root),
        gitignore_updated=gitignore_updated,
    )


def project_status(
    ctx: ProjectContext, *, entire_probe: EntireStatus | None = None
) -> ProjectStatusReport:
    repo = ProjectRepository(ctx.db)
    project = repo.get()
    if project is None:  # pragma: no cover - context load implies a project row
        raise ProjectAlreadyInitializedError("No project row found; re-run `devmemory init`.")

    head = ctx.git.head_sha()
    subject = ctx.git.commit(head).subject if head else None

    return ProjectStatusReport(
        project=project,
        branch=ctx.git.current_branch(),
        head_sha=head,
        head_subject=subject,
        working_tree_clean=not ctx.git.is_dirty(),
        entire=entire_probe or EntireStatus(),
        version_count=0,
        current_version_id=project.current_version_id,
    )


# --- helpers ---------------------------------------------------------------------


def _load_or_default_config(
    paths: ProjectPaths, *, project_id: str, project_name: str
) -> DevMemoryConfig:
    if paths.config.is_file():
        try:
            existing = DevMemoryConfig.load(paths)
        except Exception:
            _log.warning("project.init.config_unreadable", path=str(paths.config))
        else:
            return existing
    return DevMemoryConfig.default_for(project_id=project_id, project_name=project_name)


_GITIGNORE_BLOCK = f"""
# DevMemory - local-only data (config.json is committed, the rest is not)
{DEVMEMORY_DIRNAME}/config.local.json
{DEVMEMORY_DIRNAME}/metadata.db
{DEVMEMORY_DIRNAME}/metadata.db-*
{DEVMEMORY_DIRNAME}/artifacts/
{DEVMEMORY_DIRNAME}/outbox/
{DEVMEMORY_DIRNAME}/runs/
{DEVMEMORY_DIRNAME}/cache/
"""


def _ensure_repo_gitignore(repo_root: Path) -> bool:
    gitignore = repo_root / ".gitignore"
    marker = f"{DEVMEMORY_DIRNAME}/metadata.db"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    if marker in existing:
        return False
    with gitignore.open("a", encoding="utf-8") as handle:
        if existing and not existing.endswith("\n"):
            handle.write("\n")
        handle.write(_GITIGNORE_BLOCK)
    return True


__all__ = [
    "InitReport",
    "ProjectStatusReport",
    "init_project",
    "project_status",
    "slugify",
]
