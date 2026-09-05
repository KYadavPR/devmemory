"""Development version analyzer: status inference, regression detection, and heuristic recommendations."""

from typing import Optional, Tuple, List, Dict, Any
from devmemory.models import DevelopmentVersion, VersionStatus


LOWER_IS_BETTER_METRICS = {
    "latency", "latency_ms", "duration", "time", "loss", "train_loss",
    "val_loss", "error_rate", "cost", "memory_mb", "memory_used",
    "failures", "response_time", "p95_latency", "p99_latency"
}


def is_lower_better(metric_name: str) -> bool:
    """Determine whether a smaller value is better for a given metric name."""
    clean = metric_name.lower().replace("-", "_").strip()
    return any(term in clean for term in LOWER_IS_BETTER_METRICS)


def detect_regression(
    current_metrics: Dict[str, Any],
    current_tests_passed: Optional[int],
    current_tests_failed: Optional[int],
    previous_metrics: Dict[str, Any],
    previous_tests_passed: Optional[int],
    previous_tests_failed: Optional[int],
) -> Tuple[bool, List[str]]:
    """Detect if the current development step caused a regression relative to the previous version.

    Returns:
        (is_regression, reasons_list)
    """
    reasons: List[str] = []

    # 1. Test failure regression
    prev_failed = previous_tests_failed or 0
    curr_failed = current_tests_failed or 0
    if curr_failed > prev_failed:
        reasons.append(
            f"Test failures increased from {prev_failed} to {curr_failed} (+{curr_failed - prev_failed} failures)"
        )

    # 2. Test passed drop
    if previous_tests_passed is not None and current_tests_passed is not None:
        if current_tests_passed < previous_tests_passed:
            reasons.append(
                f"Passing tests dropped from {previous_tests_passed} to {current_tests_passed} (-{previous_tests_passed - current_tests_passed})"
            )

    # 3. Metric degradation (>5% tolerance)
    for k, v in current_metrics.items():
        if k in previous_metrics:
            try:
                curr_val = float(v)
                prev_val = float(previous_metrics[k])
            except (ValueError, TypeError):
                continue

            lower_better = is_lower_better(k)

            if lower_better:
                # E.g. latency jumped > 10%
                if prev_val > 0 and curr_val > prev_val * 1.10:
                    delta = curr_val - prev_val
                    pct = (delta / prev_val) * 100
                    reasons.append(
                        f"Metric '{k}' regressed: increased from {prev_val:.3f} to {curr_val:.3f} (+{pct:.1f}%)"
                    )
            else:
                # E.g. accuracy dropped > 5%
                if prev_val > 0 and curr_val < prev_val * 0.95:
                    delta = prev_val - curr_val
                    pct = (delta / prev_val) * 100
                    reasons.append(
                        f"Metric '{k}' regressed: decreased from {prev_val:.3f} to {curr_val:.3f} (-{pct:.1f}%)"
                    )

    is_reg = len(reasons) > 0
    return is_reg, reasons


def infer_status(
    tests_passed: Optional[int],
    tests_failed: Optional[int],
    errors: List[str],
    is_regression: bool,
    explicit_status: Optional[str] = None,
) -> VersionStatus:
    """Infer the development version status based on tests, errors, and regressions."""
    if explicit_status:
        try:
            return VersionStatus(explicit_status.upper())
        except ValueError:
            pass

    if errors and len(errors) > 0:
        return VersionStatus.ERROR

    if is_regression:
        return VersionStatus.REGRESSION

    if tests_failed is not None and tests_failed > 0:
        if tests_passed is not None and tests_passed > 0:
            return VersionStatus.PARTIAL_SUCCESS
        return VersionStatus.ERROR

    if tests_passed is not None and tests_passed > 0 and (tests_failed == 0 or tests_failed is None):
        return VersionStatus.SUCCESS

    return VersionStatus.SUCCESS


def generate_analysis_and_recommendation(
    version: DevelopmentVersion,
    previous: Optional[DevelopmentVersion] = None,
    regression_reasons: Optional[List[str]] = None,
) -> Tuple[str, str]:
    """Generate concise heuristic analysis and actionable recommendations for AI/human."""
    reasons = regression_reasons or []
    analysis_parts = []
    recommendation_parts = []

    # Analysis summary
    if version.is_regression:
        analysis_parts.append("REGRESSION DETECTED: " + "; ".join(reasons))
        recommendation_parts.append(
            "Do not deploy this change. Review git diff and investigate recent edits."
        )
        if version.feature:
            recommendation_parts.append(
                f"For feature '{version.feature}', revert or refine the implementation before proceeding."
            )
    elif version.status == VersionStatus.ERROR:
        analysis_parts.append("Execution or build errors encountered.")
        if version.errors:
            analysis_parts.append(f"Errors: {', '.join(version.errors[:2])}")
        recommendation_parts.append("Fix failing errors before committing further changes.")
    elif version.status == VersionStatus.SUCCESS:
        analysis_parts.append("All validations and tests passed successfully.")
        if previous and version.metrics and previous.metrics:
            improvements = []
            for k, v in version.metrics.items():
                if k in previous.metrics:
                    try:
                        cv, pv = float(v), float(previous.metrics[k])
                        if not is_lower_better(k) and cv > pv:
                            improvements.append(f"{k}: {pv:.2f} -> {cv:.2f}")
                        elif is_lower_better(k) and cv < pv:
                            improvements.append(f"{k}: {pv:.2f} -> {cv:.2f}")
                    except (ValueError, TypeError):
                        pass
            if improvements:
                analysis_parts.append("Metrics improved: " + ", ".join(improvements))
        recommendation_parts.append("State is stable. Proceed to next development milestone.")
    else:
        analysis_parts.append(f"Development step marked as {version.status.value}.")
        recommendation_parts.append("Continue implementation and run test suite.")

    analysis = " ".join(analysis_parts)
    recommendation = " ".join(recommendation_parts)
    return analysis, recommendation
