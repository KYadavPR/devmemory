"""`devmemory init` service behaviour."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmemory.config import DevMemoryConfig
from devmemory.domain.errors import GitRepositoryNotFoundError, ProjectAlreadyInitializedError
from devmemory.paths import ProjectPaths
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project, project_status, slugify
from devmemory.storage.repositories import ProjectRepository
from tests.conftest import TmpGitRepo


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("VisionAI", "visionai"), ("My  Cool Repo!", "my-cool-repo"), ("---", "project")],
)
def test_slugify(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


def test_init_requires_git(tmp_path: Path) -> None:
    with pytest.raises(GitRepositoryNotFoundError):
        init_project(tmp_path)


def test_init_creates_scaffold_and_project(git_repo: TmpGitRepo) -> None:
    report = init_project(git_repo.path, name="VisionAI")

    paths = ProjectPaths.for_root(git_repo.path)
    assert paths.exists
    assert paths.config.is_file()
    assert paths.db.is_file()
    assert report.project.project_id == "visionai"
    assert report.project.name == "VisionAI"
    assert report.git_detected is True

    cfg = DevMemoryConfig.load(paths)
    assert cfg.project_id == "visionai"

    with ProjectContext.load(git_repo.path) as ctx:
        assert ProjectRepository(ctx.db).get() is not None


def test_init_is_idempotent_only_with_force(git_repo: TmpGitRepo) -> None:
    init_project(git_repo.path, name="Demo")
    with pytest.raises(ProjectAlreadyInitializedError):
        init_project(git_repo.path, name="Demo")

    report = init_project(git_repo.path, name="Demo", force=True)
    assert report.project.project_id == "demo"


def test_init_updates_gitignore(git_repo: TmpGitRepo) -> None:
    (git_repo.path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
    report = init_project(git_repo.path)
    assert report.gitignore_updated is True
    text = (git_repo.path / ".gitignore").read_text(encoding="utf-8")
    assert ".devmemory/metadata.db" in text

    # second call: nothing to add
    report2 = init_project(git_repo.path, force=True)
    assert report2.gitignore_updated is False


def test_status_after_init(git_repo: TmpGitRepo) -> None:
    git_repo.write("app.py", "print('hi')\n")
    git_repo.commit("feat: hello")
    init_project(git_repo.path, name="Demo")
    # init leaves .gitignore + .devmemory/config.json to be committed
    git_repo.commit("chore: add devmemory")

    with ProjectContext.load(git_repo.path) as ctx:
        report = project_status(ctx)

    assert report.project.name == "Demo"
    assert report.branch == "main"
    assert report.head_subject == "chore: add devmemory"
    assert report.working_tree_clean is True
