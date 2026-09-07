"""LocalAskAdapter: provider ordering, the on-device model, guarded SQL."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from devmemory.adapters.local_ask import LocalAskAdapter
from devmemory.domain.enums import VersionStatus
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo


@pytest.fixture(autouse=True)
def _no_cloud_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY",
                "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def project(git_repo: TmpGitRepo) -> Iterator[ProjectContext]:
    git_repo.write("a.py", "x = 0\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    ctx = ProjectContext.load(git_repo.path)
    git_repo.write("a.py", "x = 1\n")
    git_repo.commit("feat: bump")
    run_checkpoint(ctx, CheckpointRequest(allow_no_entire=True, status=VersionStatus.SUCCESS,
                                          intent="bump x", tests_passed=1, tests_failed=0))
    try:
        yield ctx
    finally:
        ctx.close()


def test_unavailable_without_key_or_model(project: ProjectContext) -> None:
    a = LocalAskAdapter(project)
    assert a.is_available is False
    assert "devmemory model pull" in (a.unavailable_reason() or "")


def test_on_device_model_makes_it_available_and_offline(
    project: ProjectContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    project.config.local_model.enabled = True
    monkeypatch.setattr("devmemory.adapters.local_model.is_ready", lambda _s: True)

    a = LocalAskAdapter(project)
    assert a.is_available is True
    assert a.is_offline is True
    assert a._providers()[0] == "local"
    assert "on-device" in a.engine_label


def test_ask_uses_the_model_to_write_and_summarise_sql(
    project: ProjectContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    project.config.local_model.enabled = True
    monkeypatch.setattr("devmemory.adapters.local_model.is_ready", lambda _s: True)

    calls: list[str] = []

    def fake_call_llm(prompt: str, *, system: str, providers: list[str], **_kw: object) -> str:
        calls.append(system)
        if "translate a question" in system:
            return json.dumps({"sql": "SELECT count(*) AS n FROM versions", "explanation": "count"})
        return "There is 1 version."

    monkeypatch.setattr("devmemory.adapters.local_ask.call_llm", fake_call_llm)

    ans = LocalAskAdapter(project).ask("how many versions?")
    assert ans.error is None
    assert ans.sql == "SELECT count(*) AS n FROM versions"
    assert ans.rows == [[1]]
    assert ans.text == "There is 1 version."
    assert len(calls) == 2  # SQL, then summary


def test_ask_rejects_a_non_select_query(
    project: ProjectContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    project.config.local_model.enabled = True
    monkeypatch.setattr("devmemory.adapters.local_model.is_ready", lambda _s: True)
    monkeypatch.setattr(
        "devmemory.adapters.local_ask.call_llm",
        lambda *_a, **_k: json.dumps({"sql": "DELETE FROM versions", "explanation": "x"}),
    )
    ans = LocalAskAdapter(project).ask("delete everything")
    assert ans.error is not None
    assert "refused" in ans.error
