"""Phase 6: the pipeline collects tests + metrics and detects regressions."""

from __future__ import annotations

import json
import sys

import pytest

from devmemory.domain.enums import FeatureStatus, VersionStatus
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.features import get_feature
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo

PY = sys.executable


@pytest.fixture
def project(git_repo: TmpGitRepo) -> ProjectContext:
    git_repo.write("app.py", "print('v0')\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    # configure a test command + metrics file
    cfg = json.loads((git_repo.path / ".devmemory" / "config.json").read_text())
    cfg["tests"] = {"command": f"{PY} run_tests.py"}
    cfg["metrics"] = {"file": "metrics.json"}
    (git_repo.path / ".devmemory" / "config.json").write_text(json.dumps(cfg))
    git_repo.commit("chore: devmemory")
    return ProjectContext.load(git_repo.path)


def _set_scenario(repo: TmpGitRepo, *, passed: int, failed: int, accuracy: float) -> None:
    repo.write(
        "run_tests.py",
        f"print('{passed} passed, {failed} failed')\n"
        + "".join(f"print('FAILED test_{i}')\n" for i in range(failed)),
    )
    repo.write("metrics.json", json.dumps({"accuracy": accuracy}))


def test_pipeline_runs_tests_and_metrics(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _set_scenario(git_repo, passed=30, failed=0, accuracy=89.2)
    git_repo.write("model.py", "lr = 0.01\n")
    git_repo.commit("feat(training): baseline")

    result = run_checkpoint(project, CheckpointRequest(allow_no_entire=True))
    v = result.version
    assert v.tests is not None
    assert v.tests.passed == 30
    assert v.tests.command != "(manual)"
    assert v.metrics[0].name == "accuracy"
    assert v.metrics[0].after == 89.2
    assert v.status is VersionStatus.SUCCESS
    assert not v.regressions

    run_stages = {
        s["name"]
        for s in json.loads(next(project.paths.runs_dir.glob("*.json")).read_text())["stages"]
    }
    assert {
        "collect_tests",
        "collect_metrics",
        "detect_regression",
        "refresh_feature",
    } <= run_stages
    project.close()


def test_pipeline_detects_metric_and_test_regression(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    _set_scenario(git_repo, passed=30, failed=0, accuracy=89.2)
    git_repo.write("model.py", "lr = 0.01\n")
    git_repo.commit("feat(training): baseline")
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True))

    _set_scenario(git_repo, passed=24, failed=6, accuracy=71.0)
    git_repo.write("model.py", "lr = 0.5  # too high\n")
    git_repo.commit("feat(training): raise lr")
    result = run_checkpoint(project, CheckpointRequest(allow_no_entire=True))

    v = result.version
    assert v.status is VersionStatus.REGRESSION
    kinds = {r.kind for r in v.regressions}
    assert kinds == {"metric", "test"}
    assert any("regression" in w.lower() for w in result.warnings)

    # metric `before` was backfilled from v1's `after`
    accuracy = next(m for m in v.metrics if m.name == "accuracy")
    assert accuracy.before == 89.2

    feature = get_feature(project, "Training")
    assert feature.rolled_up_status is FeatureStatus.PARTIAL
    project.close()


def test_manual_counts_skip_the_runner(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _set_scenario(git_repo, passed=1, failed=99, accuracy=10)  # runner would report failure
    git_repo.write("x.py", "x = 1\n")
    git_repo.commit("feat: x")

    result = run_checkpoint(
        project,
        CheckpointRequest(allow_no_entire=True, tests_passed=50, tests_failed=0),
    )
    assert result.version.tests is not None
    assert result.version.tests.passed == 50
    assert result.version.tests.command == "(manual)"
    project.close()
