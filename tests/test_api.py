"""Phase 5: the dashboard JSON API."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from devmemory.api.app import create_app
from devmemory.domain.enums import VersionStatus
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo


@pytest.fixture
def client(git_repo: TmpGitRepo) -> Iterator[TestClient]:
    git_repo.write("app.py", "x = 0\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    git_repo.commit("chore: devmemory")

    # v1: a success with metrics + a real checkpoint via trailer
    cp = "cpaaaa111122"
    git_repo.write("auth.py", "def login(): return True\n")
    sha = git_repo.commit("feat(auth): add login", trailers={"Entire-Checkpoint": cp})
    git_repo.make_entire_checkpoint(cp, intent="Add JWT authentication", commit_sha=sha)
    with ProjectContext.load(git_repo.path) as ctx:
        run_checkpoint(
            ctx,
            CheckpointRequest(status=VersionStatus.SUCCESS, tests_passed=10, tests_failed=0),
        )
    # v2: a regression
    git_repo.write("auth.py", "def login(): return None  # broken\n")
    git_repo.commit("fix(auth): shorten token expiry")
    with ProjectContext.load(git_repo.path) as ctx:
        run_checkpoint(
            ctx,
            CheckpointRequest(
                allow_no_entire=True,
                status=VersionStatus.REGRESSION,
                tests_passed=6,
                tests_failed=4,
            ),
        )

    with TestClient(create_app(git_repo.path)) as c:
        yield c


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_project_summary(client: TestClient) -> None:
    r = client.get("/api/project")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Demo"
    assert body["version_count"] == 2
    assert body["latest_version_id"] == "v2"
    assert body["latest_status"] == "REGRESSION"
    assert body["last_regression_id"] == "v2"
    assert "Authentication" in body["open_features"] or "Auth" in body["open_features"]


def test_versions_list_and_detail(client: TestClient) -> None:
    r = client.get("/api/versions")
    items = r.json()
    assert [v["version_id"] for v in items] == ["v1", "v2"]
    assert items[0]["checkpoint_id"] == "cpaaaa111122"
    assert items[0]["association_method"] == "trailer"

    detail = client.get("/api/versions/v1").json()
    assert detail["intent"] == "Add JWT authentication"
    assert detail["primary_checkpoint"]["checkpoint_id"] == "cpaaaa111122"
    assert detail["tests"]["passed"] == 10

    # ref resolution
    assert client.get("/api/versions/1").json()["version_id"] == "v1"


def test_version_diff_and_trace(client: TestClient) -> None:
    diff = client.get("/api/versions/v2/diff").text
    assert "broken" in diff

    trace = client.get("/api/versions/v1/trace").json()
    keys = [n["key"] for n in trace["nodes"]]
    assert keys[0] == "intent"
    assert "checkpoint" in keys
    assert "status" in keys
    entire_node = next(n for n in trace["nodes"] if n["key"] == "checkpoint")
    assert entire_node["value"] == "cpaaaa111122"


def test_version_checkpoint_endpoint(client: TestClient) -> None:
    r = client.get("/api/versions/v1/checkpoint")
    assert r.status_code == 200
    assert r.json()["checkpoint_id"] == "cpaaaa111122"
    assert client.get("/api/versions/v2/checkpoint").status_code == 404


def test_compare(client: TestClient) -> None:
    r = client.get("/api/compare", params={"from": "v1", "to": "v2"})
    assert r.status_code == 200
    body = r.json()
    assert body["from_version"] == "v1"
    assert body["status_to"] == "REGRESSION"
    assert body["test_changes"]["failed"] == 4


def test_features(client: TestClient) -> None:
    r = client.get("/api/features")
    assert r.status_code == 200
    names = {f["name"] for f in r.json()}
    assert names & {"Authentication", "Auth"}

    feat = client.get("/api/features/Authentication")
    if feat.status_code == 404:
        feat = client.get("/api/features/Auth")
    assert feat.status_code == 200
    assert feat.json()["version_count"] >= 1


def test_search(client: TestClient) -> None:
    r = client.get("/api/search", params={"q": "authentication"})
    assert r.status_code == 200
    assert r.json()["count"] >= 1
    assert client.get("/api/search", params={"q": "auth.py"}).json()["count"] >= 1


def test_missing_version_is_404(client: TestClient) -> None:
    assert client.get("/api/versions/v99").status_code == 404


def test_dashboard_index_served(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "DevMemory" in r.text
    # the built Vite bundle: index.html links a hashed JS + CSS asset under /static/
    assert '/static/assets/' in r.text
    assert client.get("/static/index.html").status_code == 200
