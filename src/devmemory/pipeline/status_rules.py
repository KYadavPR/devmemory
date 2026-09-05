"""Derive a version status from the available evidence.

Phase 4 covers the direct signals (explicit override, errors, test outcome).
Metric-regression-aware status is layered on in Phase 6.
"""

from __future__ import annotations

from devmemory.domain.enums import VersionStatus
from devmemory.domain.models import Regression, TestOutcome


def derive_status(
    *,
    explicit: VersionStatus | None,
    tests: TestOutcome | None,
    errors: list[str],
    regressions: list[Regression] | None = None,
    has_changes: bool = True,
) -> VersionStatus:
    if explicit is not None:
        return explicit

    if errors:
        return VersionStatus.ERROR

    if regressions:
        return VersionStatus.REGRESSION

    if tests is not None and tests.ran:
        if tests.exit_code not in (0, None) and tests.total == 0:
            return VersionStatus.ERROR
        if tests.failed > 0 or tests.errors > 0:
            return VersionStatus.PARTIAL_SUCCESS if tests.passed > 0 else VersionStatus.ERROR
        if tests.passed > 0 or tests.total == 0:
            return VersionStatus.SUCCESS

    if not has_changes:
        return VersionStatus.NEEDS_REVIEW

    return VersionStatus.NEEDS_REVIEW


__all__ = ["derive_status"]
