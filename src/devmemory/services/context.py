"""``ProjectContext`` - the wired-up bundle every entry point works through.

The CLI, the REST API, and the MCP server each build one of these and then call
service functions with it. It owns the DB connection lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from devmemory.adapters.entire import EntireAdapter
from devmemory.adapters.git import GitAdapter
from devmemory.config import DevMemoryConfig
from devmemory.domain.errors import ProjectNotInitializedError
from devmemory.paths import ProjectPaths, find_project_paths
from devmemory.storage.db import Database


@dataclass(slots=True)
class ProjectContext:
    paths: ProjectPaths
    config: DevMemoryConfig
    db: Database
    git: GitAdapter
    entire: EntireAdapter

    @classmethod
    def load(cls, start: Path | str | None = None) -> ProjectContext:
        """Discover the project at or above ``start`` and open it.

        Raises :class:`ProjectNotInitializedError` if there is no ``.devmemory/``.
        """
        start_path = Path(start) if start is not None else None
        paths = find_project_paths(start_path)
        if paths is None:
            raise ProjectNotInitializedError
        config = DevMemoryConfig.load(paths)
        return cls._build(paths, config)

    @classmethod
    def for_paths(cls, paths: ProjectPaths, config: DevMemoryConfig) -> ProjectContext:
        """Build a context from already-resolved paths/config (used during ``init``)."""
        return cls._build(paths, config)

    @classmethod
    def _build(cls, paths: ProjectPaths, config: DevMemoryConfig) -> ProjectContext:
        db = Database(paths.db)
        db.migrate()
        git = GitAdapter(paths.repo_root, git_binary=None)
        entire = EntireAdapter(
            paths.repo_root,
            binary=config.entire.binary,
            repo=config.entire.repo,
            git=git,
        )
        return cls(paths=paths, config=config, db=db, git=git, entire=entire)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> ProjectContext:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.close()


__all__ = ["ProjectContext"]
