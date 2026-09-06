"""DevMemory - development-memory and version-intelligence for AI-assisted software development.

Git remembers *what* changed. Entire remembers the AI-assisted development *context*.
DevMemory connects those changes with test results, metrics, feature status, regressions,
and previous attempts so that developers and future AI agents can understand the complete
development history - and avoid repeating past mistakes.

This package sits *alongside* existing tools (Git, Entire, editors, CI). It is not an IDE,
a version-control system, or an MLflow replacement.
"""

import sys

if sys.version_info < (3, 11):
    import datetime
    import enum
    if not hasattr(datetime, "UTC"):
        datetime.UTC = datetime.timezone.utc
    if not hasattr(enum, "StrEnum"):
        class _StrEnum(str, enum.Enum):
            def __str__(self) -> str:
                return str(self.value)
        enum.StrEnum = _StrEnum

from devmemory.__about__ import __version__

__all__ = ["__version__"]
