"""The state-aware coding loop over the dashboard REST API."""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from devmemory.api.app import create_app
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo

_PYTEST = f"{sys.executable} -m pytest -q"


@pytest.fixture
def client(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    git_repo.write("pkg/__init__.py", "")
    git_repo.write("pkg/calc.py", "def add(a, b):\n    return a + b\n")
    git_repo.write(
        "tests/test_calc.py",
        "from pkg.calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    )
    git_repo.commit("chore: baseline")
    init_project(git_repo.path, name="Calc", project_id="calc")
    git_repo.commit("chore: devmemory")
    with TestClient(create_app(git_repo.path)) as c:
        yield c


def test_tasks_crud_and_state(client: TestClient) -> None:
    assert client.get("/api/tasks").json() == []

    created = client.post(
        "/api/tasks",
        json={
            "goal": "Add a subtract helper; relevant tests exist and pass",
            "test_command": _PYTEST,
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["task"]["id"] == "TASK-001"
    assert [r["id"] for r in body["requirements"]] == ["R1", "R2"]

    listed = client.get("/api/tasks").json()
    assert listed[0]["id"] == "TASK-001"
    assert listed[0]["requirements_total"] == 2

    state = client.get("/api/tasks/TASK-001/state").json()
    assert state["git"]["commit_sha"]
    assert state["overall_status"] in {"NEEDS_WORK", "IN_PROGRESS"}


def test_refresh_appends_snapshots(client: TestClient) -> None:
    client.post("/api/tasks", json={"goal": "Ship it; tests pass", "test_command": _PYTEST})
    client.post("/api/tasks/TASK-001/refresh")
    client.post("/api/tasks/TASK-001/refresh")
    snaps = client.get("/api/tasks/TASK-001/snapshots").json()
    assert len(snaps) >= 3
    assert all("overall_status" in s for s in snaps)


def test_full_loop_to_ready(client: TestClient, git_repo: TmpGitRepo) -> None:
    client.post(
        "/api/tasks",
        json={
            "goal": "Add pkg.calc.subtract; relevant tests exist and pass",
            "test_command": _PYTEST,
        },
    )
    s1 = client.get("/api/tasks/TASK-001/state").json()
    assert s1["overall_status"] == "NEEDS_WORK"

    git_repo.write(
        "pkg/calc.py",
        "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
    )
    git_repo.write(
        "tests/test_calc.py",
        "from pkg.calc import add, subtract\n\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n\n"
        "def test_subtract():\n    assert subtract(5, 3) == 2\n",
    )
    git_repo.commit("feat: subtract")

    done = client.post(
        "/api/tasks/TASK-001/requirements/R1",
        json={"status": "complete", "note": "added subtract"},
    ).json()
    assert done["overall_status"] == "READY"

    final = client.post("/api/tasks/TASK-001/complete").json()
    assert final["overall_status"] == "READY"


def test_blocking_issue_over_api(client: TestClient) -> None:
    client.post("/api/tasks", json={"goal": "Do the thing; tests pass", "test_command": _PYTEST})
    blocked = client.post(
        "/api/tasks/TASK-001/issues",
        json={"description": "need a product decision", "blocking": True},
    ).json()
    assert blocked["overall_status"] == "BLOCKED"
    issue_id = blocked["unresolved"][0]["id"]

    cleared = client.post(f"/api/tasks/TASK-001/issues/{issue_id}/resolve").json()
    assert cleared["overall_status"] != "BLOCKED"


def test_bad_requirement_status_is_422(client: TestClient) -> None:
    client.post("/api/tasks", json={"goal": "x; tests pass", "test_command": _PYTEST})
    r = client.post("/api/tasks/TASK-001/requirements/R1", json={"status": "sortof"})
    assert r.status_code == 422


def test_unknown_task_is_404(client: TestClient) -> None:
    assert client.get("/api/tasks/TASK-999/state").status_code == 404
