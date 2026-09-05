"""Shared fixtures."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from devmemory.config import DevMemoryConfig
from devmemory.paths import ProjectPaths
from devmemory.storage.db import Database


@pytest.fixture
def project_paths(tmp_path: Path) -> ProjectPaths:
    """A scaffolded ``.devmemory/`` layout under a temp directory."""
    paths = ProjectPaths.for_root(tmp_path)
    paths.ensure_scaffold()
    return paths


@pytest.fixture
def config() -> DevMemoryConfig:
    return DevMemoryConfig.default_for(project_id="demo", project_name="Demo")


@pytest.fixture
def database(project_paths: ProjectPaths) -> Iterator[Database]:
    db = Database(project_paths.db)
    try:
        yield db
    finally:
        db.close()


@dataclass
class TmpGitRepo:
    """A real, throwaway git repository for adapter/integration tests."""

    path: Path

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "core.autocrlf=false", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=check,
        )

    def write(self, rel: str, content: str) -> None:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")

    def commit(self, message: str, *, trailers: dict[str, str] | None = None) -> str:
        self.git("add", "-A")
        full = message
        if trailers:
            full += "\n\n" + "\n".join(f"{k}: {v}" for k, v in trailers.items())
        self.git("commit", "-m", full, "--no-verify")
        return self.git("rev-parse", "HEAD").stdout.strip()

    def rev(self, ref: str = "HEAD") -> str:
        return self.git("rev-parse", ref).stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> TmpGitRepo:
    repo = TmpGitRepo(tmp_path)
    repo.git("init", "-q", "-b", "main")
    repo.git("config", "user.email", "test@example.com")
    repo.git("config", "user.name", "Test User")
    repo.git("config", "commit.gpgsign", "false")
    return repo
