"""Typed error taxonomy.

Every failure DevMemory raises carries a human-readable ``message`` and, where we
can, a ``hint`` telling the user what to do next. The CLI renders these; adapters
and services raise them instead of leaking ``subprocess`` / ``sqlite3`` details.
"""

from __future__ import annotations

_GIT_INIT_HINT = "DevMemory records versions against real git commits. Run `git init` first."
_ENTIRE_INSTALL_HINT = (
    "Install it from https://entire.io or set `entire.binary` in .devmemory/config.json. "
    "Use `--allow-no-entire` to record a version without checkpoint context."
)


class DevMemoryError(Exception):
    """Base class for every error DevMemory raises deliberately.

    ``exit_code`` is used by the CLI as the process exit status. ``hint`` is an
    optional next-step suggestion shown to the user beneath the message.
    """

    exit_code: int = 1

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


# --- configuration / project lifecycle -------------------------------------------------


class ConfigError(DevMemoryError):
    """The DevMemory configuration is missing, malformed, or invalid."""

    exit_code = 2


class ProjectNotInitializedError(DevMemoryError):
    """No ``.devmemory/`` directory was found at or above the working directory."""

    exit_code = 3

    def __init__(
        self,
        message: str = "DevMemory is not initialized in this directory.",
        *,
        hint: str | None = "Run `devmemory init` in your project root.",
    ) -> None:
        super().__init__(message, hint=hint)


class ProjectAlreadyInitializedError(DevMemoryError):
    """``devmemory init`` was run where DevMemory is already set up."""

    exit_code = 3


# --- storage --------------------------------------------------------------------------


class StorageError(DevMemoryError):
    """A local persistence operation failed."""


class MigrationError(StorageError):
    """A schema migration could not be applied."""


# --- git -----------------------------------------------------------------------------


class GitError(DevMemoryError):
    """A git operation failed."""


class GitRepositoryNotFoundError(GitError):
    """The target path is not inside a git repository."""

    exit_code = 4

    def __init__(
        self,
        message: str = "This directory is not inside a git repository.",
        *,
        hint: str | None = _GIT_INIT_HINT,
    ) -> None:
        super().__init__(message, hint=hint)


# --- entire --------------------------------------------------------------------------


class EntireError(DevMemoryError):
    """An Entire integration operation failed."""


class EntireNotInstalledError(EntireError):
    """The Entire CLI could not be located."""

    exit_code = 5

    def __init__(
        self,
        message: str = "The Entire CLI was not found on PATH.",
        *,
        hint: str | None = _ENTIRE_INSTALL_HINT,
    ) -> None:
        super().__init__(message, hint=hint)


class EntireNotEnabledError(EntireError):
    """Entire is installed but not enabled in this repository."""

    exit_code = 5

    def __init__(
        self,
        message: str = "Entire is not enabled in this repository.",
        *,
        hint: str | None = "Run `entire enable` so AI sessions are captured as checkpoints.",
    ) -> None:
        super().__init__(message, hint=hint)


class CheckpointNotFoundError(EntireError):
    """No Entire checkpoint could be associated with the target commit."""

    exit_code = 6


class CheckpointAmbiguousError(EntireError):
    """More than one checkpoint plausibly matches and no explicit link exists."""

    exit_code = 6


# --- collection / analysis ----------------------------------------------------------


class CollectionError(DevMemoryError):
    """A test or metric collection step failed to run (not: the tests failed)."""


class AnalysisError(DevMemoryError):
    """The analysis provider could not produce a result."""


# --- restore ----------------------------------------------------------------------


class RestoreSafetyError(DevMemoryError):
    """A restore was refused because it would risk losing uncommitted work."""

    exit_code = 7


# --- external services ----------------------------------------------------------


class DatabricksError(DevMemoryError):
    """A Databricks operation failed. Never fatal to local history."""


__all__ = [
    "AnalysisError",
    "CheckpointAmbiguousError",
    "CheckpointNotFoundError",
    "CollectionError",
    "ConfigError",
    "DatabricksError",
    "DevMemoryError",
    "EntireError",
    "EntireNotEnabledError",
    "EntireNotInstalledError",
    "GitError",
    "GitRepositoryNotFoundError",
    "MigrationError",
    "ProjectAlreadyInitializedError",
    "ProjectNotInitializedError",
    "RestoreSafetyError",
    "StorageError",
]
