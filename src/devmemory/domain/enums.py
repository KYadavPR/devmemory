"""Enumerations shared across the domain.

All are ``str`` enums so they serialize transparently to JSON and SQLite.
"""

from __future__ import annotations

from enum import StrEnum


class VersionStatus(StrEnum):
    """The development result a version represents - not merely whether a commit exists."""

    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    ERROR = "ERROR"
    REGRESSION = "REGRESSION"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_REVIEW = "NEEDS_REVIEW"

    @property
    def is_adverse(self) -> bool:
        return self in {VersionStatus.ERROR, VersionStatus.REGRESSION}


class FeatureStatus(StrEnum):
    """Roll-up health of a logical feature area across its versions."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    NOT_STARTED = "NOT_STARTED"


class ChangeType(StrEnum):
    """How a single file changed between two commits (git name-status)."""

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    TYPE_CHANGED = "type_changed"

    @classmethod
    def from_git_status(cls, code: str) -> ChangeType:
        """Map a git ``--name-status`` letter (``A``/``M``/``D``/``R``/``C``/``T``)."""
        return {
            "A": cls.ADDED,
            "M": cls.MODIFIED,
            "D": cls.DELETED,
            "R": cls.RENAMED,
            "C": cls.COPIED,
            "T": cls.TYPE_CHANGED,
        }.get(code[:1].upper(), cls.MODIFIED)


class MetricDirection(StrEnum):
    """Which way a metric should move to count as an improvement."""

    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"
    NEUTRAL = "neutral"


class AssociationMethod(StrEnum):
    """How a checkpoint was linked to a commit, ordered by decreasing confidence."""

    TRAILER = "trailer"
    ENTIRE_CLI = "entire_cli"
    GIT_REF = "git_ref"
    HEURISTIC_TIME = "heuristic_time"
    MANUAL = "manual"
    NONE = "none"

    @property
    def default_confidence(self) -> float:
        return {
            AssociationMethod.TRAILER: 1.0,
            AssociationMethod.ENTIRE_CLI: 1.0,
            AssociationMethod.GIT_REF: 1.0,
            AssociationMethod.HEURISTIC_TIME: 0.5,
            AssociationMethod.MANUAL: 0.9,
            AssociationMethod.NONE: 0.0,
        }[self]


__all__ = [
    "AssociationMethod",
    "ChangeType",
    "FeatureStatus",
    "MetricDirection",
    "VersionStatus",
]
