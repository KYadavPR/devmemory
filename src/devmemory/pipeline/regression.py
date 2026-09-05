"""Regression detection: compare a version against the previous relevant one.

A regression is a measurable deterioration - a metric moving the wrong way past a
threshold, or tests that used to pass now failing. Purely rule-based and
direction-aware; the AI analysis layer explains *why*, it does not decide *if*.
"""

from __future__ import annotations

from pydantic import BaseModel

from devmemory.domain.enums import MetricDirection
from devmemory.domain.models import DevelopmentVersion, Metric, Regression, TestOutcome


class RegressionThresholds(BaseModel):
    metric_pct: float = 2.0
    """Adverse move larger than this percent of the baseline counts."""
    metric_abs_floor: float = 1e-9
    """Ignore moves smaller than this in absolute terms (noise)."""
    high_pct: float = 15.0
    """Adverse move at or above this percent is severity HIGH."""
    medium_pct: float = 6.0


def detect_regressions(
    *,
    metrics: list[Metric],
    tests: TestOutcome | None,
    previous: DevelopmentVersion | None,
    thresholds: RegressionThresholds | None = None,
) -> list[Regression]:
    th = thresholds or RegressionThresholds()
    out: list[Regression] = []
    out.extend(_metric_regressions(metrics, previous, th))
    test_reg = _test_regression(tests, previous, th)
    if test_reg is not None:
        out.append(test_reg)
    return out


def _metric_regressions(
    metrics: list[Metric], previous: DevelopmentVersion | None, th: RegressionThresholds
) -> list[Regression]:
    prev_by_name = {m.name: m for m in previous.metrics} if previous else {}
    out: list[Regression] = []
    for m in metrics:
        before = m.before if m.before is not None else _prev_after(prev_by_name.get(m.name))
        after = m.after
        if before is None or after is None or before == 0:
            continue
        delta = after - before
        if abs(delta) < th.metric_abs_floor:
            continue
        adverse = delta < 0 if m.direction is MetricDirection.HIGHER_IS_BETTER else delta > 0
        if m.direction is MetricDirection.NEUTRAL or not adverse:
            continue
        pct = abs(delta) / abs(before) * 100.0
        if pct < th.metric_pct:
            continue
        out.append(
            Regression(
                kind="metric",
                metric=m.name,
                before=before,
                after=after,
                change_percent=round(
                    -pct if m.direction is MetricDirection.HIGHER_IS_BETTER else pct, 2
                ),
                severity=_severity(pct, th),
                detail=(
                    f"{m.name} moved from {before:g} to {after:g} "
                    f"({pct:.1f}% {'drop' if m.direction is MetricDirection.HIGHER_IS_BETTER else 'increase'})"
                ),
            )
        )
    return out


def _test_regression(
    tests: TestOutcome | None, previous: DevelopmentVersion | None, th: RegressionThresholds
) -> Regression | None:
    if tests is None or not tests.ran:
        return None
    prev = previous.tests if previous else None
    now_failing = tests.failed + tests.errors

    if prev is not None and prev.ran:
        prev_failing = prev.failed + prev.errors
        if now_failing > prev_failing:
            increase = now_failing - prev_failing
            newly = sorted(set(tests.failing) - set(prev.failing))
            return Regression(
                kind="test",
                metric="tests",
                before=float(prev_failing),
                after=float(now_failing),
                change_percent=None,
                severity="HIGH" if increase >= 3 else "MEDIUM",
                detail=(
                    f"failing tests {prev_failing} -> {now_failing}"
                    + (f" (new: {', '.join(newly[:5])})" if newly else "")
                ),
            )
        if tests.passed < prev.passed and now_failing >= prev_failing:
            return Regression(
                kind="test",
                metric="tests",
                before=float(prev.passed),
                after=float(tests.passed),
                change_percent=None,
                severity="MEDIUM",
                detail=f"passing tests {prev.passed} -> {tests.passed}",
            )
        return None

    # No prior test data: only flag if this run itself is clearly broken.
    if now_failing > 0 and tests.passed == 0:
        return Regression(
            kind="test",
            metric="tests",
            after=float(now_failing),
            severity="HIGH",
            detail=f"{now_failing} failing, 0 passing",
        )
    return None


def _prev_after(metric: Metric | None) -> float | None:
    return metric.after if metric is not None else None


def _severity(pct: float, th: RegressionThresholds) -> str:
    if pct >= th.high_pct:
        return "HIGH"
    if pct >= th.medium_pct:
        return "MEDIUM"
    return "LOW"


__all__ = ["RegressionThresholds", "detect_regressions"]
