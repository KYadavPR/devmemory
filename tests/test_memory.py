"""Phase 7: development memory / previous attempts."""

from __future__ import annotations

import json
import sys

import pytest

from devmemory.domain.enums import VersionStatus
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.memory import MemoryQuery, previous_attempts
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo

PY = sys.executable


@pytest.fixture
def project(git_repo: TmpGitRepo) -> ProjectContext:
    git_repo.write("app.py", "print('v0')\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    git_repo.commit("chore: devmemory")
    return ProjectContext.load(git_repo.path)


def _checkpoint(project: ProjectContext, **kw: object) -> None:
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, **kw))  # type: ignore[arg-type]


def _seed_history(project: ProjectContext, repo: TmpGitRepo) -> None:
    # v1: add auth - success
    repo.write("auth.py", "EXPIRY = 3600\ndef login(): ...\n")
    repo.commit("feat: add login")
    _checkpoint(
        project, intent="Add JWT authentication", feature="Authentication", status=VersionStatus.SUCCESS
    )

    # v2: shorten token expiry - REGRESSION
    repo.write("auth.py", "EXPIRY = 30\ndef login(): ...\n")
    repo.commit("fix: shorten token expiry to 30s")
    _checkpoint(
        project,
        intent="Shorten the JWT token expiry window",
        feature="Authentication",
        status=VersionStatus.REGRESSION,
        tests_passed=20,
        tests_failed=6,
    )

    # v3: unrelated - success
    repo.write("calc.py", "def add(a, b): return a + b\n")
    repo.commit("feat: add calculator")
    _checkpoint(project, intent="Add a calculator", feature="Calculator", status=VersionStatus.SUCCESS)


def test_previous_attempts_by_files(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed_history(project, git_repo)
    attempts = previous_attempts(project, MemoryQuery(files=["auth.py"]))
    assert [a.version_id for a in attempts] == ["v2"]
    a = attempts[0]
    assert a.status == "REGRESSION"
    assert a.is_adverse
    assert "auth.py" in " ".join(a.matched_on)
    assert a.recommendation
    project.close()


def test_previous_attempts_by_intent(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed_history(project, git_repo)
    attempts = previous_attempts(
        project, MemoryQuery(intent="change how long a token stays valid (expiry)")
    )
    assert "v2" in [a.version_id for a in attempts]
    project.close()


def test_successes_excluded_by_default(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed_history(project, git_repo)
    only_bad = previous_attempts(project, MemoryQuery(feature="Authentication"))
    assert all(a.is_adverse for a in only_bad)

    with_good = previous_attempts(
        project, MemoryQuery(feature="Authentication", include_successes=True)
    )
    assert any(not a.is_adverse for a in with_good)
    project.close()


def test_pipeline_warns_about_prior_regression(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    _seed_history(project, git_repo)

    # Now touch auth.py again with a similar intent - the pipeline should warn.
    git_repo.write("auth.py", "EXPIRY = 15\ndef login(): ...\n")
    git_repo.commit("fix(auth): make expiry even shorter")
    result = run_checkpoint(
        project,
        CheckpointRequest(allow_no_entire=True, intent="Shorten the token expiry further"),
    )
    assert any("prior attempt V2" in w or "V2" in w for w in result.warnings)

    run_path = project.paths.runs_dir / f"{result.run_log.run_id}.json"
    log = json.loads(run_path.read_text())
    cpa = next(s for s in log["stages"] if s["name"] == "check_previous_attempts")
    assert "v2" in cpa["data"]["matches"]
    project.close()


def test_api_attempts_endpoint(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    from fastapi.testclient import TestClient

    from devmemory.api.app import create_app

    _seed_history(project, git_repo)
    project.close()

    with TestClient(create_app(git_repo.path)) as client:
        r = client.get("/api/attempts", params={"file": "auth.py"})
        assert r.status_code == 200
        assert r.json()[0]["version_id"] == "v2"

        r = client.get("/api/versions/v2/attempts")
        assert r.status_code == 200  # v2 itself excluded
        assert all(a["version_id"] != "v2" for a in r.json())
