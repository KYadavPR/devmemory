"""Phase 11: the MCP server, exercised in-memory through a fastmcp client.

The async client calls are driven synchronously with ``asyncio.run`` so no
pytest async plugin is needed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from typing import TypeVar

import pytest
from typer.testing import CliRunner

from devmemory.cli.app import app
from devmemory.domain.enums import VersionStatus
from devmemory.mcp.server import build_server
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo

runner = CliRunner()
T = TypeVar("T")


def _sync(factory: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(factory())


@pytest.fixture
def repo(git_repo: TmpGitRepo) -> Iterator[TmpGitRepo]:
    git_repo.write("app.py", "x = 0\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    git_repo.commit("chore: devmemory")

    ctx = ProjectContext.load(git_repo.path)
    try:
        git_repo.write("auth.py", "EXPIRY = 3600\n")
        git_repo.commit("feat: login")
        run_checkpoint(
            ctx,
            CheckpointRequest(
                allow_no_entire=True,
                intent="Add JWT auth",
                feature="Authentication",
                status=VersionStatus.SUCCESS,
            ),
        )
        git_repo.write("auth.py", "EXPIRY = 30\n")
        git_repo.commit("fix: shorten expiry")
        run_checkpoint(
            ctx,
            CheckpointRequest(
                allow_no_entire=True,
                intent="Shorten the token expiry window",
                feature="Authentication",
                status=VersionStatus.REGRESSION,
                tests_passed=20,
                tests_failed=6,
            ),
        )
    finally:
        ctx.close()
    yield git_repo


def _call(server: object, name: str, args: dict[str, object]) -> object:
    async def factory() -> object:
        from fastmcp import Client

        async with Client(server) as client:  # type: ignore[arg-type]
            result = await client.call_tool(name, args)
            return result.data

    return _sync(factory)


def test_tools_are_registered(repo: TmpGitRepo) -> None:
    async def factory() -> set[str]:
        from fastmcp import Client

        server = build_server(repo.path)
        async with Client(server) as client:
            return {t.name for t in await client.list_tools()}

    names = _sync(factory)
    assert {
        "get_project_context",
        "get_version_history",
        "get_version",
        "get_development_trace",
        "get_previous_attempts",
        "check_before_change",
        "search_versions",
        "get_analytics",
    } <= names


def test_get_project_context(repo: TmpGitRepo) -> None:
    data = _call(build_server(repo.path), "get_project_context", {})
    assert data.version_count == 2
    assert data.latest.version_id == "v2"
    assert [v.version_id for v in data.recent_adverse] == ["v2"]


def test_get_version_history_and_filter(repo: TmpGitRepo) -> None:
    server = build_server(repo.path)
    everything = _call(server, "get_version_history", {"limit": 10})
    assert [v.version_id for v in everything] == ["v2", "v1"]

    filtered = _call(server, "get_version_history", {"limit": 10, "feature": "Authentication"})
    assert {v.version_id for v in filtered} == {"v1", "v2"}


def test_check_before_change_flags_prior_regression(repo: TmpGitRepo) -> None:
    data = _call(
        build_server(repo.path),
        "check_before_change",
        {"files": ["auth.py"], "intent": "shorten the token expiry further"},
    )
    assert data.verdict in {"caution", "high-risk"}
    assert any(a.version_id == "v2" for a in data.related_attempts)
    assert data.warnings


def test_get_version_and_trace(repo: TmpGitRepo) -> None:
    server = build_server(repo.path)
    report = _call(server, "get_version", {"ref": "v2"})
    assert report.brief.version_id == "v2"
    assert report.trace.version_id == "v2"

    trace = _call(server, "get_development_trace", {"ref": "1"})
    assert trace.version_id == "v1"


def test_search_versions_tool(repo: TmpGitRepo) -> None:
    data = _call(build_server(repo.path), "search_versions", {"query": "expiry"})
    assert any(v.version_id == "v2" for v in data)


def test_cli_mcp_print_config(repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(repo.path)
    result = runner.invoke(app, ["mcp", "--print-config"])
    assert result.exit_code == 0, result.output
    cfg = json.loads(result.output)
    assert cfg["mcpServers"]["devmemory"]["command"] == "devmemory"
    assert cfg["mcpServers"]["devmemory"]["args"][0] == "mcp"


# --- the state-aware coding loop over MCP -----------------------------------


def test_taskloop_tools_registered(repo: TmpGitRepo) -> None:
    async def factory() -> set[str]:
        from fastmcp import Client

        async with Client(build_server(repo.path)) as client:
            return {t.name for t in await client.list_tools()}

    names = _sync(factory)
    assert {
        "create_task",
        "get_state",
        "refresh_state",
        "get_checkpoint",
        "report_issue",
        "mark_complete",
        "set_requirement_status",
    } <= names


def test_loop_over_mcp_create_refresh_state(
    repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    server = build_server(repo.path)

    created = _call(server, "create_task", {"goal": "Document the auth module; tests pass"})
    assert created.task.id == "TASK-001"
    assert created.overall_status in {"NEEDS_WORK", "IN_PROGRESS"}

    state = _call(server, "get_state", {"task_id": "TASK-001"})
    assert state.task.id == "TASK-001"
    assert [r.id for r in state.requirements][:1] == ["R1"]
    assert state.git.commit_sha  # git collector ran

    refreshed = _call(server, "refresh_state", {"task_id": "TASK-001"})
    assert refreshed.snapshot_id is not None


def test_report_blocking_issue_over_mcp(repo: TmpGitRepo) -> None:
    server = build_server(repo.path)
    _call(server, "create_task", {"goal": "Ship auth; tests pass"})
    _call(
        server,
        "report_issue",
        {"task_id": "TASK-001", "description": "need a human decision", "blocking": True},
    )
    state = _call(server, "refresh_state", {"task_id": "TASK-001"})
    assert state.overall_status == "BLOCKED"
