"""Phase 11: the agent-facing context service and its REST endpoints."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from devmemory.domain.enums import VersionStatus
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.agent_context import (
    CAUTION,
    HIGH_RISK,
    PROCEED,
    change_guidance,
    project_brief,
    recent_history,
    version_report,
)
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo


@pytest.fixture
def project(git_repo: TmpGitRepo) -> Iterator[ProjectContext]:
    git_repo.write("app.py", "x = 0\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    git_repo.commit("chore: devmemory")
    ctx = ProjectContext.load(git_repo.path)
    try:
        yield ctx
    finally:
        ctx.close()


def _cp(project: ProjectContext, **kw: object) -> None:
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, **kw))  # type: ignore[arg-type]


def _seed(project: ProjectContext, repo: TmpGitRepo) -> None:
    repo.write("auth.py", "EXPIRY = 3600\n")
    repo.commit("feat: add login")
    _cp(
        project,
        intent="Add JWT authentication",
        feature="Authentication",
        status=VersionStatus.SUCCESS,
    )

    repo.write("auth.py", "EXPIRY = 30\n")
    repo.commit("fix: shorten expiry")
    _cp(
        project,
        intent="Shorten the JWT token expiry window to 30 seconds",
        feature="Authentication",
        status=VersionStatus.REGRESSION,
        tests_passed=20,
        tests_failed=6,
    )

    repo.write("calc.py", "def add(a, b):\n    return a + b\n")
    repo.commit("feat: calculator")
    _cp(project, intent="Add a calculator", feature="Calculator", status=VersionStatus.SUCCESS)


def test_project_brief(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo)
    brief = project_brief(project)

    assert brief.project == "Demo"
    assert brief.version_count == 3
    assert brief.success_rate == pytest.approx(66.7, abs=0.1)
    assert brief.latest is not None and brief.latest.version_id == "v3"
    assert [v.version_id for v in brief.recent_adverse] == ["v2"]
    assert brief.last_regression_id == "v2"
    assert any("regression" in n.lower() for n in brief.notes)


def test_recent_history_and_feature_filter(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo)
    all_versions = recent_history(project, limit=10)
    assert [v.version_id for v in all_versions] == ["v3", "v2", "v1"]

    auth_only = recent_history(project, limit=10, feature="Authentication")
    assert {v.version_id for v in auth_only} == {"v1", "v2"}
    assert all(v.feature == "authentication" for v in auth_only)


def test_version_report_has_trace(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo)
    report = version_report(project, "v2")
    assert report.brief.version_id == "v2"
    assert report.brief.is_adverse
    assert report.trace.version_id == "v2"
    assert any(n.source == "status" for n in report.trace.nodes)


def test_change_guidance_high_risk_on_prior_regression(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    _seed(project, git_repo)
    guidance = change_guidance(
        project,
        files=["auth.py"],
        intent="shorten the token expiry even further",
        feature="Authentication",
    )
    assert guidance.verdict in {CAUTION, HIGH_RISK}
    assert any("V2" in w for w in guidance.warnings)
    assert guidance.recommendations
    assert any(a.version_id == "v2" for a in guidance.related_attempts)


def test_change_guidance_proceed_on_new_ground(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    _seed(project, git_repo)
    guidance = change_guidance(
        project, files=["brand_new_module.py"], intent="add a completely new feature"
    )
    assert guidance.verdict == PROCEED
    assert guidance.warnings == []


def test_change_guidance_uses_graph_blast_radius(
    project: ProjectContext, git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    from devmemory.adapters.graph import SymbolImpact, SymbolRef

    _seed(project, git_repo)

    def fake_impact(symbol: str, **_kw: object) -> SymbolImpact:
        return SymbolImpact(
            query=symbol,
            resolved=True,
            callers_total=25,
            callers=[SymbolRef(name="c1", file_path="a.py"), SymbolRef(name="c2", file_path="b.py")],
        )

    monkeypatch.setattr(project.graph, "_binary", "/opt/entire-graph")
    monkeypatch.setattr(project.graph, "symbol_impact", fake_impact)

    guidance = change_guidance(
        project,
        files=["brand_new_module.py"],
        intent="add a feature",
        symbols=["core_helper"],
    )
    assert guidance.graph_available
    assert guidance.max_blast_radius == 25
    assert guidance.verdict == HIGH_RISK  # escalated purely by fan-out
    assert any("core_helper" in w and "caller" in w for w in guidance.warnings)


def test_api_agent_endpoints(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    from fastapi.testclient import TestClient

    from devmemory.api.app import create_app

    _seed(project, git_repo)
    project.close()

    with TestClient(create_app(git_repo.path)) as client:
        r = client.get("/api/agent/context")
        assert r.status_code == 200
        assert r.json()["version_count"] == 3

        r = client.get("/api/agent/history", params={"feature": "Authentication"})
        assert r.status_code == 200
        assert {v["version_id"] for v in r.json()} == {"v1", "v2"}

        r = client.post(
            "/api/agent/check",
            json={"files": ["auth.py"], "intent": "shorten expiry more"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["verdict"] in {"proceed", "caution", "high-risk"}
        assert any(a["version_id"] == "v2" for a in body["related_attempts"])
