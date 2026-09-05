"""Shared fixtures."""

from __future__ import annotations

from collections.abc import Iterator
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
