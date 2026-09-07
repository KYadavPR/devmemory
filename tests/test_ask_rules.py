"""The built-in (no-LLM) Ask engine: intent routing and answers from local data."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from devmemory.adapters.ask_rules import RulesAskAdapter
from devmemory.adapters.genie import GenieAnswer
from devmemory.domain.enums import VersionStatus
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo


@pytest.fixture
def seeded(git_repo: TmpGitRepo) -> Iterator[ProjectContext]:
    git_repo.write("app.py", "x = 0\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    cfg = git_repo.path / ".devmemory" / "config.json"
    cfg.write_text(json.dumps({**json.loads(cfg.read_text()), "metrics": {"file": "m.json"}}))
    git_repo.commit("chore: devmemory")
    ctx = ProjectContext.load(git_repo.path)

    def cp(**kw: object) -> None:
        run_checkpoint(ctx, CheckpointRequest(allow_no_entire=True, **kw))

    git_repo.write("auth.py", "E = 3600\n")
    git_repo.write("m.json", json.dumps({"latency_ms": 100}))
    git_repo.commit("feat: login")
    cp(intent="add auth", feature="Auth", status=VersionStatus.SUCCESS, tests_passed=10, tests_failed=0)

    git_repo.write("auth.py", "E = 30\n")
    git_repo.write("m.json", json.dumps({"latency_ms": 400}))
    git_repo.commit("fix: shorten expiry")
    cp(intent="tune expiry", feature="Auth", status=VersionStatus.REGRESSION, tests_passed=8, tests_failed=2)

    try:
        yield ctx
    finally:
        ctx.close()


def _ask(ctx: ProjectContext, q: str) -> tuple[str, GenieAnswer]:
    ans = RulesAskAdapter(ctx).ask(q)
    assert ans.text is not None
    return ans.text, ans


def test_always_available(seeded: ProjectContext) -> None:
    assert RulesAskAdapter(seeded).is_available is True


def test_count_intent(seeded: ProjectContext) -> None:
    text, ans = _ask(seeded, "how many versions are there?")
    assert "2 development versions" in text
    assert ans.rows


def test_regression_intent(seeded: ProjectContext) -> None:
    text, ans = _ask(seeded, "what regressed?")
    assert "v2" in text or any("v2" in r for r in ans.rows)
    assert ans.columns[0] == "version"


def test_failing_tests_intent(seeded: ProjectContext) -> None:
    _text, ans = _ask(seeded, "show every version that failed tests, newest first")
    assert "v2" in [row[0] for row in ans.rows]


def test_metric_trend_intent(seeded: ProjectContext) -> None:
    text, ans = _ask(seeded, "how did latency_ms move over time?")
    assert "latency_ms" in text
    assert len(ans.rows) == 2


def test_single_version_intent(seeded: ProjectContext) -> None:
    text, _ans = _ask(seeded, "show v1")
    assert "v1" in text
    assert "add auth" in text


def test_unrecognised_question_lists_capabilities(seeded: ProjectContext) -> None:
    text, _ans = _ask(seeded, "write me a poem about kubernetes")
    assert "common questions" in text.lower()
    assert "OPENROUTER_API_KEY" in text
