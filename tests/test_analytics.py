"""Phase 10: development-intelligence analytics (local implementation + API + CLI)."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from typer.testing import CliRunner

from devmemory.cli.app import app
from devmemory.domain.enums import VersionStatus
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.analytics import analytics_summary, canned_queries
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo

runner = CliRunner()


@pytest.fixture
def project(git_repo: TmpGitRepo) -> Iterator[ProjectContext]:
    git_repo.write("app.py", "x = 0\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    cfg_path = git_repo.path / ".devmemory" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["metrics"] = {"file": "metrics.json"}
    cfg_path.write_text(json.dumps(cfg))
    git_repo.commit("chore: devmemory")
    ctx = ProjectContext.load(git_repo.path)
    try:
        yield ctx
    finally:
        ctx.close()


def _cp(project: ProjectContext, **kw: object) -> None:
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, **kw))  # type: ignore[arg-type]


def _seed(project: ProjectContext, repo: TmpGitRepo) -> None:
    # v1 - Authentication, success, baseline latency
    repo.write("auth.py", "EXPIRY = 3600\n")
    repo.write("metrics.json", json.dumps({"latency_ms": 100}))
    repo.commit("feat: add login")
    _cp(
        project,
        intent="Add JWT authentication with refresh tokens",
        feature="Authentication",
        status=VersionStatus.SUCCESS,
        tests_passed=30,
        tests_failed=0,
    )

    # v2 - Authentication, latency regression, touches auth.py + metrics.json
    repo.write("auth.py", "EXPIRY = 30\n")
    repo.write("metrics.json", json.dumps({"latency_ms": 400}))
    repo.commit("fix: shorten token expiry")
    _cp(
        project,
        intent="Shorten the token expiry window to 30 seconds",
        feature="Authentication",
        tests_passed=24,
        tests_failed=6,
    )

    # v3 - Calculator, unrelated success
    repo.write("calc.py", "def add(a, b):\n    return a + b\n")
    repo.commit("feat: add calculator")
    _cp(
        project,
        intent="Add a calculator module",
        feature="Calculator",
        status=VersionStatus.SUCCESS,
        tests_passed=10,
        tests_failed=0,
    )

    # v4 - Authentication, explicit regression, same file signature as v2
    repo.write("auth.py", "EXPIRY = 15\n")
    repo.write("metrics.json", json.dumps({"latency_ms": 380}))
    repo.commit("fix: shorten token expiry further")
    _cp(
        project,
        intent="Shorten expiry further to 15 seconds",
        feature="Authentication",
        status=VersionStatus.REGRESSION,
    )


def test_local_summary_topline(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo)
    s = analytics_summary(project)

    assert s.source == "local"
    assert s.version_count == 4
    assert s.regression_count == 2
    assert s.success_rate == 50.0


def test_regression_rows_newest_first(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo)
    s = analytics_summary(project)

    assert [r.version_id for r in s.regressions] == ["v4", "v2"]
    v2 = next(r for r in s.regressions if r.version_id == "v2")
    assert v2.feature == "authentication"
    assert v2.severity in {"LOW", "MEDIUM", "HIGH"}


def test_feature_attempts(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo)
    s = analytics_summary(project)

    auth = next(f for f in s.features if f.feature == "authentication")
    assert auth.attempts == 3
    assert auth.successes == 1
    assert auth.regressions == 2
    assert auth.success_rate == pytest.approx(33.3, abs=0.1)


def test_file_churn_flags_repeatedly_touched_file(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    _seed(project, git_repo)
    s = analytics_summary(project)

    auth = next(c for c in s.file_churn if c.path == "auth.py")
    assert auth.changes == 3
    assert auth.adverse_changes == 2
    assert auth.risk == pytest.approx(0.67, abs=0.01)


def test_agent_rows(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo)
    s = analytics_summary(project)

    assert len(s.agents) == 1
    agent = s.agents[0]
    assert agent.versions == 4
    assert agent.success_rate == 50.0


def test_trend_is_ordered(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo)
    s = analytics_summary(project)

    assert [p.version_number for p in s.trend] == [1, 2, 3, 4]
    assert s.trend[0].test_pass_rate == 100.0


def test_failed_approaches_cluster(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo)
    s = analytics_summary(project)

    assert len(s.failed_approaches) == 1
    fa = s.failed_approaches[0]
    assert fa.occurrences == 2
    assert set(fa.version_ids) == {"v2", "v4"}
    assert "auth.py" in fa.signature


def test_empty_project_summary(project: ProjectContext) -> None:
    s = analytics_summary(project)
    assert s.version_count == 0
    assert s.success_rate == 0.0
    assert s.regressions == []
    assert s.failed_approaches == []


def test_canned_queries_reference_configured_tables() -> None:
    q = canned_queries("devmemory", "analytics")
    assert set(q) == {"regressions", "feature_attempts", "file_churn", "agent_effectiveness"}
    assert all("devmemory.analytics.fact_versions" in sql for sql in q.values())


def test_api_analytics_endpoint(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    from fastapi.testclient import TestClient

    from devmemory.api.app import create_app

    _seed(project, git_repo)
    project.close()

    with TestClient(create_app(git_repo.path)) as client:
        r = client.get("/api/analytics")
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "local"
        assert body["version_count"] == 4
        assert body["regression_count"] == 2
        assert any(f["feature"] == "authentication" for f in body["features"])
        assert any(fa["occurrences"] == 2 for fa in body["failed_approaches"])


def test_cli_analytics(
    project: ProjectContext, git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(project, git_repo)
    project.close()
    monkeypatch.chdir(git_repo.path)

    result = runner.invoke(app, ["analytics"])
    assert result.exit_code == 0, result.output
    assert "source: local" in result.output
    assert "authentication" in result.output.lower()

    result = runner.invoke(app, ["analytics", "--json"])
    assert result.exit_code == 0, result.output
    assert '"source"' in result.output
    assert '"local"' in result.output
