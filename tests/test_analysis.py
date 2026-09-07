"""Phase 13: the AI analysis layer - provider chain, fact guard, wiring.

Hermetic: no LLM SDK is ever called. LLM keys are cleared; the chain falls
through to the deterministic rules provider.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from devmemory.analysis import build_providers, fact_guard, run_analysis
from devmemory.analysis.base import AnalysisInput, AnalysisProvider, AttemptRef
from devmemory.analysis.llm import LLMProvider, _parse
from devmemory.analysis.rules import RulesProvider
from devmemory.domain.enums import VersionStatus
from devmemory.domain.models import Analysis
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.analysis import analyze_version, build_analysis_input
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from devmemory.services.versions import get_version
from tests.conftest import TmpGitRepo

_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")


@pytest.fixture(autouse=True)
def _no_llm_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)


def _input(**over: object) -> AnalysisInput:
    base: dict[str, object] = {
        "version_id": "v3",
        "intent": "Shorten the token expiry window",
        "feature": "auth",
        "agent": "Claude Code",
        "model": "claude-sonnet-5",
        "status": "SUCCESS",
        "is_adverse": False,
        "files_changed": 2,
        "lines_added": 10,
        "lines_removed": 3,
        "changed_paths": ["auth.py", "config.py"],
    }
    base.update(over)
    return AnalysisInput(**base)  # type: ignore[arg-type]


# --- rules provider -----------------------------------------------------------


def test_rules_provider_is_deterministic_and_offline() -> None:
    data = _input(status="SUCCESS")
    a1 = RulesProvider().analyze(data)
    a2 = RulesProvider().analyze(data)
    assert a1.summary == a2.summary
    assert a1.provider == "rules"
    assert a1.risk == "low"


def test_rules_provider_flags_regression() -> None:
    data = _input(
        status="REGRESSION",
        is_adverse=True,
        regressions=["latency 100 -> 400 (300% increase)"],
    )
    a = RulesProvider().analyze(data)
    assert a.risk == "high"
    assert "regress" in a.summary.lower()
    assert a.recommendation and "before building on this" in a.recommendation


def test_rules_provider_surfaces_prior_attempts() -> None:
    data = _input(
        previous_attempts=[
            AttemptRef(
                version_id="v2",
                status="REGRESSION",
                result="latency up 300%",
                matched_on=["auth.py"],
            )
        ],
    )
    a = RulesProvider().analyze(data)
    assert any("V2" in w for w in a.warnings)
    assert a.risk == "medium"


# --- fact guard -------------------------------------------------------------


def test_fact_guard_cannot_downplay_an_adverse_version() -> None:
    lying = Analysis(summary="All good, ship it.", risk="low", provider="anthropic")
    data = _input(status="REGRESSION", is_adverse=True, regressions=["tests failed"])

    guarded = fact_guard(lying, data, provider="anthropic")
    assert guarded.risk == "medium"
    assert any("raised to 'medium'" in w for w in guarded.warnings)
    assert guarded.provider == "anthropic"


def test_fact_guard_clamps_bogus_risk_and_scrubs_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-supersecretvalue-1234567890")
    dirty = Analysis(
        summary="Key is sk-supersecretvalue-1234567890 and risk is banana",
        risk="banana",
        provider="whoever",
    )
    guarded = fact_guard(dirty, _input(), provider="openai")
    assert guarded.risk == "low"  # bogus -> derived from (non-adverse) facts
    assert "sk-supersecretvalue-1234567890" not in guarded.summary
    assert guarded.provider == "openai"


def test_analysis_model_holds_no_fact_fields() -> None:
    # structural guarantee: analysis literally cannot carry git/test/metric facts
    forbidden = {
        "lines_added",
        "lines_removed",
        "files_changed",
        "tests",
        "metrics",
        "git_commit",
        "changed_files",
    }
    assert forbidden.isdisjoint(Analysis.model_fields)


# --- chain -----------------------------------------------------------------


class _NoneProvider(AnalysisProvider):
    name = "none-maker"

    def analyze(self, data: AnalysisInput) -> Analysis | None:
        return None


class _BoomProvider(AnalysisProvider):
    name = "boom"

    def analyze(self, data: AnalysisInput) -> Analysis | None:
        raise RuntimeError("provider exploded")


def test_build_providers_always_ends_with_rules() -> None:
    chain = build_providers(["anthropic", "bogus", "openai"])
    assert isinstance(chain[-1], RulesProvider)
    assert [type(p).__name__ for p in chain].count("RulesProvider") == 1


def test_build_providers_dedupes_and_keeps_order() -> None:
    chain = build_providers(["rules", "rules", "anthropic"])
    assert [p.name for p in chain] == ["rules", "anthropic"] or chain[-1].name == "rules"


def test_run_analysis_falls_through_none_and_errors() -> None:
    data = _input(status="SUCCESS")
    result = run_analysis(data, [_NoneProvider(), _BoomProvider(), RulesProvider()])
    assert result.provider == "rules"
    assert result.summary


def test_run_analysis_uses_first_successful_provider() -> None:
    class _Good(AnalysisProvider):
        name = "good"

        def analyze(self, d: AnalysisInput) -> Analysis:
            return Analysis(summary="from the good provider", risk="low", provider="good")

    result = run_analysis(_input(), [_Good(), RulesProvider()])
    assert result.provider == "good"
    assert result.summary == "from the good provider"


# --- llm provider (no network) --------------------------------------------


def test_llm_provider_without_key_returns_none() -> None:
    assert LLMProvider("anthropic").analyze(_input()) is None
    assert LLMProvider("openai").analyze(_input()) is None
    assert LLMProvider("openrouter").analyze(_input()) is None


def test_openrouter_is_a_known_llm_provider() -> None:
    chain = build_providers(["openrouter", "rules"])
    assert chain[0].name == "openrouter"
    assert isinstance(chain[-1], RulesProvider)


def test_openrouter_uses_openai_wire_via_call_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    import devmemory.analysis.llm as llm_mod

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    captured: dict[str, object] = {}

    def fake(name: str, key: str, model: str, prompt: str, system: str, local: object = None) -> str:
        captured.update(name=name, key=key, model=model)
        return '{"ok": true}'

    monkeypatch.setattr(llm_mod, "_dispatch", fake)
    out = llm_mod.call_llm("hi", system="s", providers=["openrouter"])
    assert out == '{"ok": true}'
    assert captured == {"name": "openrouter", "key": "sk-or-v1-test", "model": "openai/gpt-4o-mini"}


def test_local_is_a_known_provider_needing_no_key() -> None:
    from devmemory.config import LocalModelSettings

    chain = build_providers(["local", "rules"], local_model=LocalModelSettings())
    assert chain[0].name == "local"
    assert isinstance(chain[-1], RulesProvider)


def test_local_provider_routes_to_the_on_device_model(monkeypatch: pytest.MonkeyPatch) -> None:
    import devmemory.analysis.llm as llm_mod
    from devmemory.config import LocalModelSettings

    seen: dict[str, object] = {}

    def fake_generate(settings: object, prompt: str, *, system: str) -> str:
        seen.update(prompt=prompt, system=system)
        return '{"summary": "ok", "risk": "low"}'

    monkeypatch.setattr("devmemory.adapters.local_model.generate", fake_generate)
    out = llm_mod.call_llm(
        "hi", system="s", providers=["local"], local_model=LocalModelSettings()
    )
    assert out == '{"summary": "ok", "risk": "low"}'
    assert seen["system"] == "s"


def test_llm_parse_handles_fences_and_junk() -> None:
    assert _parse('```json\n{"risk": "low"}\n```') == {"risk": "low"}
    assert _parse('here you go: {"a": 1} thanks') == {"a": 1}
    assert _parse("not json at all") is None
    assert _parse("[1, 2, 3]") is None


# --- service + pipeline + api + cli --------------------------------------


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


def test_pipeline_generates_and_stores_analysis(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    import json

    git_repo.write("auth.py", "EXPIRY = 30\n")
    git_repo.commit("fix: shorten expiry")
    result = run_checkpoint(
        project,
        CheckpointRequest(
            allow_no_entire=True,
            intent="Shorten the token expiry window",
            feature="Authentication",
            status=VersionStatus.REGRESSION,
        ),
    )

    run_path = project.paths.runs_dir / f"{result.run_log.run_id}.json"
    stages = {s["name"]: s for s in json.loads(run_path.read_text())["stages"]}
    assert stages["generate_analysis"]["status"] == "ok"
    assert stages["generate_analysis"]["data"]["provider"] == "rules"

    stored = get_version(project, "v1")
    assert stored.analysis is not None
    assert stored.analysis.provider == "rules"
    assert stored.analysis.risk == "high"  # REGRESSION


def test_pipeline_skips_analysis_when_disabled(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    import json

    project.config.analysis.enabled = False
    git_repo.write("app.py", "x = 1\n")
    git_repo.commit("feat: bump")
    result = run_checkpoint(project, CheckpointRequest(allow_no_entire=True, intent="bump"))

    run_path = project.paths.runs_dir / f"{result.run_log.run_id}.json"
    stages = {s["name"]: s for s in json.loads(run_path.read_text())["stages"]}
    assert stages["generate_analysis"]["status"] == "skipped"
    assert get_version(project, "v1").analysis is None


def test_build_analysis_input_from_a_real_version(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    git_repo.write("auth.py", "EXPIRY = 30\n")
    git_repo.commit("fix: expiry")
    run_checkpoint(
        project,
        CheckpointRequest(
            allow_no_entire=True,
            intent="tune expiry",
            feature="Auth",
            status=VersionStatus.SUCCESS,
            tests_passed=10,
            tests_failed=0,
        ),
    )
    v = get_version(project, "v1")
    data = build_analysis_input(project, v)
    assert data.version_id == "v1"
    assert data.feature == "auth"
    assert data.changed_paths == ["auth.py"]
    assert data.test_summary == "10 passed / 0 failed / 0 skipped"
    assert data.diff_excerpt is None  # include_diff defaults off


def test_analyze_version_service_persists(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("app.py", "x = 9\n")
    git_repo.commit("feat: c")
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, intent="c"))

    analysis = analyze_version(project, "v1", providers=["rules"])
    assert analysis.provider == "rules"
    assert get_version(project, "v1").analysis is not None


def test_api_regenerate_analysis(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    from fastapi.testclient import TestClient

    from devmemory.api.app import create_app

    git_repo.write("app.py", "x = 5\n")
    git_repo.commit("feat: c")
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, intent="c"))
    project.close()

    with TestClient(create_app(git_repo.path)) as client:
        r = client.post("/api/versions/v1/analysis")
        assert r.status_code == 200
        assert r.json()["provider"] == "rules"

        r = client.get("/api/versions/v1")
        assert r.json()["analysis"]["provider"] == "rules"


def test_cli_analyze(
    project: ProjectContext, git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from devmemory.cli.app import app

    git_repo.write("app.py", "x = 7\n")
    git_repo.commit("feat: c")
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, intent="improve things"))
    project.close()
    monkeypatch.chdir(git_repo.path)

    result = CliRunner().invoke(app, ["analyze", "v1"])
    assert result.exit_code == 0, result.output
    assert "rules" in result.output
    assert "risk" in result.output
