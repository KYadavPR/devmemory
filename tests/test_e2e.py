"""End-to-end: a full DevMemory lifecycle through the real CLI and API.

init -> three checkpoints (success, regression, fix) -> history / show / compare
/ analyze / memory -> the dashboard API. No mocks; the only thing stubbed out is
the Entire checkpoint (``--allow-no-entire``) and the optional graph plugin.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from devmemory.adapters import graph as graph_mod
from devmemory.api.app import create_app
from devmemory.cli.app import app
from tests.conftest import TmpGitRepo

runner = CliRunner()
PY = sys.executable


@pytest.fixture(autouse=True)
def _no_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graph_mod, "_find_binary", lambda: None)


@pytest.fixture
def repo(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> Iterator[TmpGitRepo]:
    monkeypatch.chdir(git_repo.path)
    git_repo.write("service.py", "TIMEOUT = 30\n")
    git_repo.write("run_tests.py", "print('12 passed, 0 failed')\n")
    git_repo.write("metrics.json", json.dumps({"latency_ms": 100}))
    git_repo.commit("chore: baseline")
    yield git_repo


def _run(*args: str) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, f"{args} failed:\n{result.output}"
    return result.output


def test_full_lifecycle(repo: TmpGitRepo) -> None:
    # 1. init + configure test/metric collection
    #    (--no-backfill so this test owns the version numbering explicitly)
    _run("init", "--name", "Checkout", "--project-id", "checkout", "--no-backfill")
    cfg_path = repo.path / ".devmemory" / "config.json"
    cfg = json.loads(cfg_path.read_text())
    cfg["tests"] = {"command": f"{PY} run_tests.py"}
    cfg["metrics"] = {"file": "metrics.json"}
    cfg_path.write_text(json.dumps(cfg))
    repo.commit("chore: devmemory")

    # 2. v1 - a clean success
    repo.write("service.py", "TIMEOUT = 30\nRETRIES = 3\n")
    repo.commit("feat(checkout): add retries")
    out = _run("checkpoint", "--allow-no-entire", "--intent", "Add request retries")
    assert "v1" in out.lower()

    # 3. v2 - a regression: latency up, tests failing
    repo.write("service.py", "TIMEOUT = 2\nRETRIES = 9\n")
    repo.write("run_tests.py", "print('9 passed, 3 failed')\nprint('FAILED test_slow')\n")
    repo.write("metrics.json", json.dumps({"latency_ms": 340}))
    repo.commit("fix(checkout): tighten timeout")
    _run("checkpoint", "--allow-no-entire", "--intent", "Tighten the timeout to 2s")

    # 4. v3 - the fix
    repo.write("service.py", "TIMEOUT = 15\nRETRIES = 3\n")
    repo.write("run_tests.py", "print('12 passed, 0 failed')\n")
    repo.write("metrics.json", json.dumps({"latency_ms": 105}))
    repo.commit("fix(checkout): settle on 15s")
    _run("checkpoint", "--allow-no-entire", "--intent", "Settle on a 15s timeout")

    # 5. history shows all three, v2 adverse
    history = _run("history")
    assert "V1" in history and "V2" in history and "V3" in history
    assert "REGRESSION" in history

    # 6. show v2 - the regression detail
    show = _run("show", "v2")
    assert "REGRESSION" in show
    assert "latency_ms" in show

    # 7. compare v1 -> v2
    compare = _run("compare", "1", "2")
    assert "service.py" in compare

    # 8. analyze v2 - rules provider, high risk
    analyze = _run("analyze", "v2")
    assert "rules" in analyze
    assert "high" in analyze.lower()

    # 9. memory: touching service.py again should surface v2
    mem = _run("memory", "--file", "service.py")
    assert "V2" in mem

    # 10. the dashboard API
    with TestClient(create_app(repo.path)) as client:
        assert client.get("/api/health").json()["status"] == "ok"

        project = client.get("/api/project").json()
        assert project["version_count"] == 3
        assert project["last_regression_id"] == "v2"

        versions = client.get("/api/versions").json()
        assert [v["version_id"] for v in versions] == ["v1", "v2", "v3"]

        analytics = client.get("/api/analytics").json()
        assert analytics["version_count"] == 3
        assert analytics["regression_count"] >= 1

        v2 = client.get("/api/versions/v2").json()
        assert v2["analysis"]["provider"] == "rules"
        assert v2["analysis"]["risk"] == "high"

        check = client.post(
            "/api/agent/check",
            json={"files": ["service.py"], "intent": "make the timeout even shorter"},
        ).json()
        assert check["verdict"] in {"caution", "high-risk"}
        assert any(a["version_id"] == "v2" for a in check["related_attempts"])

    # 11. doctor runs clean against the finished project
    doctor = _run("doctor")
    assert "schema" in doctor
    assert "Checkout (checkout)" in doctor
