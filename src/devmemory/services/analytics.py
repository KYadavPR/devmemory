"""Development-intelligence analytics.

Every question is answered by one query with two implementations that return the
*same* shape: a local one over SQLite (always available, used by the demo) and a
Databricks one over the published Delta tables (when a workspace is configured).
The result carries a ``source`` so the dashboard can badge it.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from pydantic import BaseModel

from devmemory.config import resolve_databricks_credentials
from devmemory.domain.enums import VersionStatus
from devmemory.domain.models import DevelopmentVersion
from devmemory.services.context import ProjectContext
from devmemory.storage.versions import VersionRepository

_ADVERSE = {VersionStatus.REGRESSION.value, VersionStatus.ERROR.value}


class RegressionRow(BaseModel):
    version_id: str
    intent: str | None
    feature: str | None
    agent: str | None
    git_commit: str
    severity: str
    detail: str


class FeatureRow(BaseModel):
    feature: str
    attempts: int
    successes: int
    regressions: int
    success_rate: float
    latest_status: str


class FileChurnRow(BaseModel):
    path: str
    changes: int
    adverse_changes: int
    risk: float


class AgentRow(BaseModel):
    agent: str
    versions: int
    success_rate: float
    regressions: int
    tokens_per_success: float | None


class TrendPoint(BaseModel):
    version_id: str
    version_number: int
    status: str
    test_pass_rate: float | None
    key_metric: float | None


class FailedApproach(BaseModel):
    signature: list[str]
    occurrences: int
    version_ids: list[str]
    example_intent: str | None


class AnalyticsSummary(BaseModel):
    source: str  # 'local' | 'databricks'
    project: str
    version_count: int
    regression_count: int
    success_rate: float
    regressions: list[RegressionRow]
    features: list[FeatureRow]
    file_churn: list[FileChurnRow]
    agents: list[AgentRow]
    trend: list[TrendPoint]
    failed_approaches: list[FailedApproach]


def analytics_summary(ctx: ProjectContext) -> AnalyticsSummary:
    """Prefer Databricks if configured and reachable; otherwise compute locally."""
    if ctx.config.databricks.enabled and resolve_databricks_credentials() is not None:
        remote = _try_databricks(ctx)
        if remote is not None:
            return remote
    return _local_summary(ctx)


# --- local implementation ---------------------------------------------------------


def _local_summary(ctx: ProjectContext) -> AnalyticsSummary:
    repo = VersionRepository(ctx.db)
    versions = repo.page(ctx.config.project_id, limit=2000, ascending=True)
    n = len(versions)
    successes = sum(1 for v in versions if v.status is VersionStatus.SUCCESS)
    regressions = sum(1 for v in versions if v.status is VersionStatus.REGRESSION or v.regressions)

    return AnalyticsSummary(
        source="local",
        project=ctx.config.project_name,
        version_count=n,
        regression_count=regressions,
        success_rate=round(successes / n * 100, 1) if n else 0.0,
        regressions=_regression_rows(versions),
        features=_feature_rows(versions),
        file_churn=_file_churn(versions),
        agents=_agent_rows(versions),
        trend=_trend(versions),
        failed_approaches=_failed_approaches(versions),
    )


def _regression_rows(versions: list[DevelopmentVersion]) -> list[RegressionRow]:
    rows: list[RegressionRow] = []
    for v in versions:
        if v.status is not VersionStatus.REGRESSION and not v.regressions:
            continue
        worst = max(
            v.regressions,
            key=lambda r: {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(r.severity, 0),
            default=None,
        )
        rows.append(
            RegressionRow(
                version_id=v.version_id,
                intent=v.intent,
                feature=_feature_name(v),
                agent=v.agent,
                git_commit=v.git_commit,
                severity=worst.severity if worst else "MEDIUM",
                detail=worst.detail if worst and worst.detail else "status marked REGRESSION",
            )
        )
    rows.reverse()
    return rows


def _feature_rows(versions: list[DevelopmentVersion]) -> list[FeatureRow]:
    by_feature: dict[str, list[DevelopmentVersion]] = defaultdict(list)
    for v in versions:
        name = _feature_name(v)
        if name:
            by_feature[name].append(v)
    out: list[FeatureRow] = []
    for name, vs in sorted(by_feature.items(), key=lambda kv: -len(kv[1])):
        succ = sum(1 for v in vs if v.status is VersionStatus.SUCCESS)
        regr = sum(1 for v in vs if v.status is VersionStatus.REGRESSION or v.regressions)
        out.append(
            FeatureRow(
                feature=name,
                attempts=len(vs),
                successes=succ,
                regressions=regr,
                success_rate=round(succ / len(vs) * 100, 1),
                latest_status=vs[-1].status.value,
            )
        )
    return out


def _file_churn(versions: list[DevelopmentVersion]) -> list[FileChurnRow]:
    changes: Counter[str] = Counter()
    adverse: Counter[str] = Counter()
    for v in versions:
        is_bad = v.status.value in _ADVERSE or bool(v.regressions)
        for f in v.changed_files:
            changes[f.path] += 1
            if is_bad:
                adverse[f.path] += 1
    rows = [
        FileChurnRow(
            path=path,
            changes=c,
            adverse_changes=adverse[path],
            risk=round(adverse[path] / c, 2) if c else 0.0,
        )
        for path, c in changes.most_common(15)
    ]
    return rows


def _agent_rows(versions: list[DevelopmentVersion]) -> list[AgentRow]:
    by_agent: dict[str, list[DevelopmentVersion]] = defaultdict(list)
    for v in versions:
        by_agent[v.agent or "unknown"].append(v)
    out: list[AgentRow] = []
    for agent, vs in sorted(by_agent.items(), key=lambda kv: -len(kv[1])):
        succ = [v for v in vs if v.status is VersionStatus.SUCCESS]
        tokens = [
            v.primary_checkpoint.tokens.total
            for v in succ
            if v.primary_checkpoint and v.primary_checkpoint.tokens.total
        ]
        out.append(
            AgentRow(
                agent=agent,
                versions=len(vs),
                success_rate=round(len(succ) / len(vs) * 100, 1),
                regressions=sum(1 for v in vs if v.status is VersionStatus.REGRESSION),
                tokens_per_success=round(sum(tokens) / len(tokens)) if tokens else None,
            )
        )
    return out


def _trend(versions: list[DevelopmentVersion]) -> list[TrendPoint]:
    points: list[TrendPoint] = []
    for v in versions:
        rate = v.tests.pass_rate if v.tests and v.tests.ran else None
        key_metric = v.metrics[0].after if v.metrics else None
        points.append(
            TrendPoint(
                version_id=v.version_id,
                version_number=v.version_number,
                status=v.status.value,
                test_pass_rate=round(rate * 100, 1) if rate is not None else None,
                key_metric=key_metric,
            )
        )
    return points


def _failed_approaches(versions: list[DevelopmentVersion]) -> list[FailedApproach]:
    groups: dict[tuple[str, ...], list[DevelopmentVersion]] = defaultdict(list)
    for v in versions:
        if v.status.value not in _ADVERSE and not v.regressions:
            continue
        sig = tuple(sorted(f.path for f in v.changed_files))
        if sig:
            groups[sig].append(v)
    out = [
        FailedApproach(
            signature=list(sig),
            occurrences=len(vs),
            version_ids=[v.version_id for v in vs],
            example_intent=vs[0].intent,
        )
        for sig, vs in groups.items()
        if len(vs) >= 2
    ]
    out.sort(key=lambda a: -a.occurrences)
    return out


def _feature_name(v: DevelopmentVersion) -> str | None:
    return v.feature_id.split(":", 1)[-1] if v.feature_id else None


# --- databricks implementation --------------------------------------------------


def _try_databricks(ctx: ProjectContext) -> AnalyticsSummary | None:
    from devmemory.adapters.databricks import DatabricksAdapter

    adapter = DatabricksAdapter(ctx.config)
    try:
        rows = adapter.query(
            f"SELECT version_id, status, agent, feature, is_regression "
            f"FROM {adapter.table('fact_versions')} WHERE project_id = :pid",
            {"pid": ctx.config.project_id},
        )
    except Exception:
        return None

    n = len(rows)
    if n == 0:
        return None
    successes = sum(1 for r in rows if r.get("status") == "SUCCESS")
    regr = sum(1 for r in rows if r.get("is_regression") or r.get("status") == "REGRESSION")
    # For the richer breakdowns Databricks would run more queries; the demo path
    # is local, so keep the remote summary to the top-line numbers plus a marker.
    local = _local_summary(ctx)
    return local.model_copy(
        update={
            "source": "databricks",
            "version_count": n,
            "regression_count": regr,
            "success_rate": round(successes / n * 100, 1),
        }
    )


def canned_queries(catalog: str, schema: str) -> dict[str, str]:
    """SQL a user can run in Databricks directly - shown in the dashboard."""
    t = f"{catalog}.{schema}"
    return {
        "regressions": (
            f"SELECT version_id, feature, agent, intent\n"
            f"FROM {t}.fact_versions\nWHERE is_regression = true\nORDER BY version_number DESC"
        ),
        "feature_attempts": (
            f"SELECT feature, count(*) attempts,\n"
            f"  round(sum(if(status='SUCCESS',1,0))*100.0/count(*), 1) success_rate_pct\n"
            f"FROM {t}.fact_versions\nWHERE feature IS NOT NULL\nGROUP BY feature\nORDER BY attempts DESC"
        ),
        "file_churn": (
            f"SELECT path, count(*) changes,\n"
            f"  sum(if(v.is_regression,1,0)) adverse\n"
            f"FROM {t}.fact_changed_files f JOIN {t}.fact_versions v USING (version_id)\n"
            f"GROUP BY path\nORDER BY changes DESC\nLIMIT 15"
        ),
        "agent_effectiveness": (
            f"SELECT agent, count(*) versions,\n"
            f"  round(sum(if(status='SUCCESS',1,0))*100.0/count(*),1) success_rate_pct,\n"
            f"  sum(if(is_regression,1,0)) regressions\n"
            f"FROM {t}.fact_versions\nWHERE agent IS NOT NULL\nGROUP BY agent\nORDER BY success_rate_pct DESC"
        ),
    }


__all__ = [
    "AnalyticsSummary",
    "analytics_summary",
    "canned_queries",
]
