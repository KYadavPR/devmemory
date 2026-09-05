"""Project path resolution."""

from __future__ import annotations

from pathlib import Path

from devmemory.paths import ProjectPaths, find_project_paths, find_project_root


def test_scaffold_creates_every_directory(tmp_path: Path) -> None:
    paths = ProjectPaths.for_root(tmp_path)
    assert not paths.exists
    paths.ensure_scaffold()
    assert paths.exists
    for directory in (
        paths.versions_dir,
        paths.artifacts_dir,
        paths.outbox_dir,
        paths.runs_dir,
        paths.cache_dir,
    ):
        assert directory.is_dir()
    paths.ensure_scaffold()  # idempotent


def test_find_root_walks_upward(tmp_path: Path) -> None:
    (tmp_path / ".devmemory").mkdir()
    nested = tmp_path / "src" / "pkg" / "sub"
    nested.mkdir(parents=True)

    assert find_project_root(nested) == tmp_path.resolve()
    found = find_project_paths(nested)
    assert found is not None
    assert found.repo_root == tmp_path.resolve()


def test_find_root_returns_none_when_absent(tmp_path: Path) -> None:
    assert find_project_root(tmp_path) is None
    assert find_project_paths(tmp_path) is None
