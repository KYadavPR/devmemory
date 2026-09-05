"""Domain models -> API response schemas."""

from __future__ import annotations

from devmemory.api.schemas import (
    ComparisonResponse,
    FeatureDetail,
    FeatureHistoryPoint,
    MetricChange,
    ProjectSummary,
    SearchHit,
    VersionListItem,
)
from devmemory.domain.models import DevelopmentVersion
from devmemory.services.features import FeatureWithHistory
from devmemory.services.projects import ProjectStatusReport
from devmemory.services.versions import VersionDiff


def _iso(value: object) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else None


def project_summary(report: ProjectStatusReport) -> ProjectSummary:
    return ProjectSummary(
        project_id=report.project.project_id,
        name=report.project.name,
        repo_path=report.project.repo_path,
        branch=report.branch,
        head_sha=report.head_sha,
        head_subject=report.head_subject,
        working_tree_clean=report.working_tree_clean,
        version_count=report.version_count,
        latest_version_id=report.latest_version_id,
        latest_status=report.latest_status,
        latest_intent=report.latest_intent,
        head_has_version=report.head_has_version,
        last_regression_id=report.last_regression_id,
        open_features=report.open_features,
        latest_metrics=report.latest_metrics,
        entire_installed=report.entire.installed,
        entire_enabled=report.entire.enabled,
        entire_version=report.entire.cli_version,
        entire_agents=report.entire.agents,
    )


def version_list_item(v: DevelopmentVersion) -> VersionListItem:
    cp = v.primary_checkpoint
    return VersionListItem(
        version_id=v.version_id,
        version_number=v.version_number,
        status=v.status.value,
        intent=v.intent,
        agent=v.agent,
        model=v.model,
        feature=v.feature_id.split(":", 1)[-1] if v.feature_id else None,
        git_commit=v.git_commit,
        branch=v.branch,
        files_changed=v.files_changed,
        lines_added=v.lines_added,
        lines_removed=v.lines_removed,
        checkpoint_id=cp.checkpoint_id if cp else None,
        association_method=v.entire_association_method.value,
        association_confidence=v.entire_association_confidence,
        metrics={m.name: m.after for m in v.metrics},
        tests_passed=v.tests.passed if v.tests and v.tests.ran else None,
        tests_failed=v.tests.failed if v.tests and v.tests.ran else None,
        has_regression=bool(v.regressions),
        committed_at=_iso(v.committed_at),
        created_at=v.created_at.isoformat(),
    )


def search_hit(v: DevelopmentVersion) -> SearchHit:
    return SearchHit(
        version_id=v.version_id,
        version_number=v.version_number,
        status=v.status.value,
        intent=v.intent,
        agent=v.agent,
        feature=v.feature_id.split(":", 1)[-1] if v.feature_id else None,
        git_commit=v.git_commit,
        snippet=(v.analysis.summary if v.analysis and v.analysis.summary else v.intent),
    )


def comparison_response(diff: VersionDiff) -> ComparisonResponse:
    return ComparisonResponse(
        from_version=diff.from_version_id,
        to_version=diff.to_version_id,
        from_commit=diff.from_commit,
        to_commit=diff.to_commit,
        stat=diff.stat,
        files=diff.files,
        diff_text=diff.diff_text,
        metric_changes=[
            MetricChange(
                name=name,
                before=change["before"],
                after=change["after"],
                delta=change["delta"],
                unit=None,
                direction="higher_is_better",
            )
            for name, change in diff.metric_changes.items()
        ],
        test_changes=diff.test_changes,
        status_from=diff.status_from.value,
        status_to=diff.status_to.value,
    )


def feature_detail(fh: FeatureWithHistory) -> FeatureDetail:
    latest_metrics: dict[str, float | None] = {}
    if fh.versions:
        latest_metrics = {m.name: m.after for m in fh.versions[-1].metrics}
    return FeatureDetail(
        feature_id=fh.feature.feature_id,
        name=fh.feature.name,
        status=fh.rolled_up_status.value,
        derived_from=fh.feature.derived_from,
        version_count=len(fh.versions),
        latest_metrics=latest_metrics,
        history=[
            FeatureHistoryPoint(
                version_id=v.version_id,
                version_number=v.version_number,
                status=v.status.value,
                metrics={m.name: m.after for m in v.metrics},
                committed_at=_iso(v.committed_at),
            )
            for v in fh.versions
        ],
    )


__all__ = [
    "comparison_response",
    "feature_detail",
    "project_summary",
    "search_hit",
    "version_list_item",
]
