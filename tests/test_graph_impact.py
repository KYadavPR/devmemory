"""Phase 12: Entire `graph` change-impact - parsing, adapter, storage, wiring.

Hermetic: the real `entire-graph` plugin is never invoked. The adapter's
subprocess call is monkeypatched and binary discovery is forced off where a
"not installed" state is needed.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator

import pytest

from devmemory.adapters import graph as graph_mod
from devmemory.adapters.graph import GraphAdapter, GraphImpact, _parse_commit
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.impact import version_impact
from devmemory.services.projects import init_project
from devmemory.storage.graph_impacts import GraphImpactRepository
from tests.conftest import TmpGitRepo

_SAMPLE = {
    "base": "aaaaaaaaaaaa",
    "head": "bbbbbbbbbbbb",
    "files": [
        {
            "path": "src/pkg/core.py",
            "status": "M",
            "language": "Python",
            "changes": [
                {
                    "type": "signature_changed",
                    "kind": "function",
                    "name": "process",
                    "old_signature": "def process(x)",
                    "new_signature": "def process(x, y)",
                    "before_start_line": 10,
                    "after_start_line": 10,
                    "dependents_count": 7,
                },
                {
                    "type": "body_changed",
                    "kind": "function",
                    "name": "helper",
                    "after_start_line": 40,
                    "dependents_count": 0,
                },
            ],
        },
        {
            "path": "README.md",
            "status": "M",
            "language": "Markdown",
            "changes": [
                {
                    "type": "added",
                    "kind": "section",
                    "name": "Usage",
                    "after_start_line": 3,
                    "dependents_count": 0,
                }
            ],
        },
    ],
}


def test_parse_commit_shapes_entities() -> None:
    impact = _parse_commit(_SAMPLE)
    assert impact is not None
    assert impact.base_commit == "aaaaaaaaaaaa"
    assert impact.entity_count == 3
    assert impact.max_dependents == 7

    sig = next(e for e in impact.entities if e.name == "process")
    assert sig.change_type == "signature_changed"
    assert sig.dependents_count == 7
    assert sig.is_risky
    assert sig.old_signature == "def process(x)"

    assert next(e for e in impact.entities if e.name == "helper").is_risky is False


def test_parse_commit_hotspots_rank_risky_first() -> None:
    impact = _parse_commit(_SAMPLE)
    assert impact is not None
    assert impact.hotspots[0].name == "process"
    assert all(
        h.dependents_count > 0 or h.change_type in ("removed", "signature_changed")
        for h in impact.hotspots
    )


def test_parse_commit_rejects_junk() -> None:
    assert _parse_commit("not a dict") is None
    assert _parse_commit({"no": "files"}) is None


def _fake_proc(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["entire-graph"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_adapter_commit_impact_parses_subprocess_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _fake_proc(json.dumps(_SAMPLE))

    monkeypatch.setattr(graph_mod.subprocess, "run", fake_run)
    adapter = GraphAdapter(".", binary="/opt/entire-graph")

    impact = adapter.commit_impact("HEAD")
    assert isinstance(impact, GraphImpact)
    assert impact.entity_count == 3
    assert calls[0][0] == "/opt/entire-graph"
    assert "commit" in calls[0] and "--json" in calls[0]


def test_adapter_degrades_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graph_mod.subprocess, "run", lambda *a, **k: _fake_proc("", returncode=1))
    assert GraphAdapter(".", binary="/opt/entire-graph").commit_impact("HEAD") is None


_IMPACT_SAMPLE = {
    "focus_matches_total": 1,
    "disambiguation_required": False,
    "callers": {
        "total": 2,
        "entries": [
            {
                "endpoint": {
                    "name": "cart_total",
                    "file_path": "pricing/core.py",
                    "kind": "function",
                    "start_line": 12,
                },
                "depth": 1,
            },
            {
                "endpoint": {"name": "quote", "file_path": "pricing/core.py", "kind": "function"},
                "depth": 2,
                "via": "cart_total",
            },
        ],
    },
    "callees": {"total": 1, "entries": [{"endpoint": {"name": "base_rate", "file_path": "pricing/core.py", "kind": "function"}}]},
    "type_consumers": {"total": 0, "entries": None},
    "co_changes": {"total": 1, "entries": [{"endpoint": {"name": "metrics.json", "file_path": "metrics.json", "kind": "module"}}]},
}


def test_symbol_impact_parses_blast_radius(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _fake_proc(json.dumps(_IMPACT_SAMPLE))

    monkeypatch.setattr(graph_mod.subprocess, "run", fake_run)
    si = GraphAdapter(".", binary="/opt/entire-graph").symbol_impact("apply_discount")

    assert si is not None and si.resolved
    assert si.callers_total == 2 and si.callees_total == 1
    assert si.blast_radius == 2  # callers + type consumers
    assert si.affected_files == ["pricing/core.py"]
    assert si.cochange_files == ["metrics.json"]
    assert si.callers[1].via == "cart_total"
    assert "impact" in calls[0] and "--symbol" in calls[0]


def test_symbol_impact_ambiguous_is_unresolved(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "focus_matches_total": 0,
        "disambiguation_required": True,
        "definitions": [
            {"name": "run", "file_path": "a.py", "kind": "function", "start_line": 3},
            {"name": "run", "file_path": "b.py", "kind": "function", "start_line": 9},
        ],
    }
    monkeypatch.setattr(graph_mod.subprocess, "run", lambda *a, **k: _fake_proc(json.dumps(payload)))
    si = GraphAdapter(".", binary="/opt/entire-graph").symbol_impact("run")
    assert si is not None and not si.resolved
    assert len(si.definitions) == 2


def test_graph_search_parses_results(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "query": "round money",
        "results": [
            {
                "file_path": "pkg/core.py",
                "start_line": 29,
                "end_line": 30,
                "symbol_name": "round_money",
                "signature": "def round_money(x)",
                "kind": "function",
                "score": 29.5,
                "snippet": "def round_money(x):\n    return round(x, 2)",
            }
        ],
    }
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _fake_proc(json.dumps(payload))

    monkeypatch.setattr(graph_mod.subprocess, "run", fake_run)
    hits = GraphAdapter(".", binary="/opt/entire-graph").search("round money")
    assert len(hits) == 1
    assert hits[0].symbol_name == "round_money" and hits[0].file_path == "pkg/core.py"
    assert "search" in calls[0] and "--query" in calls[0]


def test_graph_search_empty_without_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graph_mod, "_find_binary", lambda: None)
    assert GraphAdapter(".").search("anything") == []


def test_diff_impact_reuses_commit_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _fake_proc(json.dumps(_SAMPLE))

    monkeypatch.setattr(graph_mod.subprocess, "run", fake_run)
    impact = GraphAdapter(".", binary="/opt/entire-graph").diff_impact("base123", "HEAD")
    assert impact is not None and impact.entity_count == 3
    assert "diff" in calls[0] and "--base" in calls[0] and "--head" in calls[0]


def test_adapter_unavailable_without_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graph_mod, "_find_binary", lambda: None)
    adapter = GraphAdapter(".")
    assert adapter.is_available is False
    assert adapter.commit_impact("HEAD") is None
    assert adapter.probe().installed is False


@pytest.fixture
def project(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> Iterator[ProjectContext]:
    # force "plugin not installed" so the context's GraphAdapter is inert
    monkeypatch.setattr(graph_mod, "_find_binary", lambda: None)
    git_repo.write("app.py", "x = 0\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    git_repo.commit("chore: devmemory")
    ctx = ProjectContext.load(git_repo.path)
    try:
        yield ctx
    finally:
        ctx.close()


def test_repository_round_trip(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("app.py", "x = 1\n")
    git_repo.commit("feat: bump")
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, intent="bump"))

    repo = GraphImpactRepository(project.db)
    impact = _parse_commit(_SAMPLE)
    assert impact is not None
    repo.set("v1", impact)

    loaded = repo.get("v1")
    assert loaded is not None
    assert loaded.version_id == "v1"
    assert loaded.entity_count == 3
    assert loaded.generated_at is not None

    row = project.db.query_one(
        "SELECT entity_count, max_dependents FROM graph_impacts WHERE version_id = ?", ("v1",)
    )
    assert row["entity_count"] == 3
    assert row["max_dependents"] == 7

    repo.delete("v1")
    assert repo.get("v1") is None


def test_pipeline_skips_graph_stage_when_disabled(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    git_repo.write("app.py", "x = 2\n")
    git_repo.commit("feat: change")
    result = run_checkpoint(project, CheckpointRequest(allow_no_entire=True, intent="change"))

    run_path = project.paths.runs_dir / f"{result.run_log.run_id}.json"
    stages = {s["name"]: s for s in json.loads(run_path.read_text())["stages"]}
    assert "collect_graph_impact" in stages
    assert stages["collect_graph_impact"]["status"] == "skipped"


def test_version_impact_service_and_api(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    from fastapi.testclient import TestClient

    from devmemory.api.app import create_app

    git_repo.write("app.py", "x = 3\n")
    git_repo.commit("feat: c")
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, intent="c"))

    # nothing stored, plugin unavailable -> None / 404
    assert version_impact(project, "v1") is None

    GraphImpactRepository(project.db).set("v1", _parse_commit(_SAMPLE))  # type: ignore[arg-type]
    stored = version_impact(project, "v1")
    assert stored is not None and stored.entity_count == 3
    project.close()

    with TestClient(create_app(git_repo.path)) as client:
        r = client.get("/api/versions/v1/impact")
        assert r.status_code == 200
        assert r.json()["entity_count"] == 3

        r = client.get("/api/versions/v999/impact")
        assert r.status_code in (404, 400)
