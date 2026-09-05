"""GitAdapter against real throwaway repositories."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmemory.adapters.git import GitAdapter
from devmemory.domain.enums import ChangeType
from devmemory.domain.errors import GitError, GitRepositoryNotFoundError
from tests.conftest import TmpGitRepo


def test_non_repository(tmp_path: Path) -> None:
    git = GitAdapter(tmp_path)
    assert git.is_repository() is False
    with pytest.raises(GitRepositoryNotFoundError):
        git.require_repository()


def test_empty_repository(git_repo: TmpGitRepo) -> None:
    git = GitAdapter(git_repo.path)
    assert git.is_repository() is True
    assert git.has_commits() is False
    assert git.head_sha() is None
    assert git.working_tree_state().is_clean is True


def test_root_commit_metadata_and_files(git_repo: TmpGitRepo) -> None:
    git_repo.write("calc.py", "def add(a, b):\n    return a + b\n")
    git_repo.write("README.md", "# demo\n")
    sha = git_repo.commit("feat: initial calculator")

    git = GitAdapter(git_repo.path)
    info = git.commit("HEAD")
    assert info.sha == sha
    assert info.parent is None
    assert info.subject == "feat: initial calculator"
    assert info.author_email == "test@example.com"
    assert info.authored_at is not None

    files = git.changed_files(None, "HEAD")
    paths = {f.path: f for f in files}
    assert set(paths) == {"calc.py", "README.md"}
    assert paths["calc.py"].change_type is ChangeType.ADDED
    assert paths["calc.py"].additions == 2
    assert paths["calc.py"].deletions == 0

    stat = git.diff_stat(None, "HEAD")
    assert stat.files_changed == 2
    assert stat.additions == 3


def test_diff_between_commits_with_modify_and_delete(git_repo: TmpGitRepo) -> None:
    git_repo.write("a.py", "x = 1\n")
    git_repo.write("b.py", "y = 2\n")
    base = git_repo.commit("base")

    git_repo.write("a.py", "x = 1\nz = 3\n")
    (git_repo.path / "b.py").unlink()
    git_repo.write("c.py", "w = 4\n")
    head = git_repo.commit("change")

    git = GitAdapter(git_repo.path)
    files = {f.path: f for f in git.changed_files(base, head)}
    assert files["a.py"].change_type is ChangeType.MODIFIED
    assert files["a.py"].additions == 1
    assert files["b.py"].change_type is ChangeType.DELETED
    assert files["c.py"].change_type is ChangeType.ADDED

    diff = git.diff_text(base, head)
    assert "z = 3" in diff
    assert git.parent_sha(head) == base


def test_rename_detection(git_repo: TmpGitRepo) -> None:
    body = "\n".join(f"line {i}" for i in range(40)) + "\n"
    git_repo.write("old_name.py", body)
    base = git_repo.commit("add")

    (git_repo.path / "old_name.py").rename(git_repo.path / "new_name.py")
    head = git_repo.commit("rename")

    git = GitAdapter(git_repo.path)
    files = {f.path: f for f in git.changed_files(base, head)}
    assert "new_name.py" in files
    assert files["new_name.py"].change_type is ChangeType.RENAMED
    assert files["new_name.py"].old_path == "old_name.py"


def test_entire_checkpoint_trailer(git_repo: TmpGitRepo) -> None:
    git_repo.write("f.py", "x = 1\n")
    git_repo.commit("with trailer", trailers={"Entire-Checkpoint": "01K9TQ8ZP7X3F5M2WVJ4CNRB6D"})

    git = GitAdapter(git_repo.path)
    assert git.entire_checkpoint_trailer("HEAD") == "01K9TQ8ZP7X3F5M2WVJ4CNRB6D"
    assert git.commit("HEAD").trailer("entire-checkpoint") == "01K9TQ8ZP7X3F5M2WVJ4CNRB6D"

    git_repo.write("g.py", "y = 2\n")
    git_repo.commit("no trailer")
    assert git.entire_checkpoint_trailer("HEAD") is None


def test_working_tree_state_reports_changes(git_repo: TmpGitRepo) -> None:
    git_repo.write("tracked.py", "x = 1\n")
    git_repo.commit("base")
    git_repo.write("tracked.py", "x = 2\n")
    git_repo.write("untracked.txt", "hello\n")

    git = GitAdapter(git_repo.path)
    state = git.working_tree_state()
    assert state.is_clean is False
    assert state.has_uncommitted_changes is True
    assert "tracked.py" in state.unstaged
    assert "untracked.txt" in state.untracked
    assert git.is_dirty() is True


def test_resolve_bad_revision(git_repo: TmpGitRepo) -> None:
    git_repo.write("f.py", "x = 1\n")
    git_repo.commit("base")
    git = GitAdapter(git_repo.path)
    with pytest.raises(GitError):
        git.resolve("does-not-exist")
