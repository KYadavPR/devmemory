"""Phase 8: `devmemory diff` / `compare` / `search` CLI + enriched comparison."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from devmemory.cli.app import app
from devmemory.domain.enums import VersionStatus
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from devmemory.services.versions import version_diff
from tests.conftest import TmpGitRepo

runner = CliRunner()


@pytest.fixture
def repo(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> TmpGitRepo:
    monkeypatch.chdir(git_repo.path)
    git_repo.write("m.py", "acc = 0.80\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="D", project_id="d")
    git_repo.commit("chore: dm")

    git_repo.write("m.py", "acc = 0.89\n")
    git_repo.commit("feat: tune")
    with ProjectContext.load(git_repo.path) as ctx:
        run_checkpoint(
            ctx,
            CheckpointRequest(
                allow_no_entire=True,
                feature="Training",
                intent="Improve accuracy",
                status=VersionStatus.SUCCESS,
            ),
        )
    git_repo.write("m.py", "acc = 0.71\n")
    git_repo.write("extra.py", "x = 1\n")
    git_repo.commit("feat: risky change")
    with ProjectContext.load(git_repo.path) as ctx:
        run_checkpoint(
            ctx,
            CheckpointRequest(
                allow_no_entire=True,
                feature="Training",
                intent="Aggressive learning rate",
                status=VersionStatus.REGRESSION,
            ),
        )
    return git_repo


def test_diff_command(repo: TmpGitRepo) -> None:
    result = runner.invoke(app, ["diff", "v1", "v2"])
    assert result.exit_code == 0
    assert "acc = 0.71" in result.output
    assert "extra.py" in result.output


def test_compare_command(repo: TmpGitRepo) -> None:
    result = runner.invoke(app, ["compare", "1", "2"])
    assert result.exit_code == 0
    assert "V1" in result.output and "V2" in result.output
    assert "SUCCESS" in result.output and "REGRESSION" in result.output
    assert "extra.py" in result.output


def test_compare_json_has_feature_and_checkpoint(repo: TmpGitRepo) -> None:
    with ProjectContext.load(repo.path) as ctx:
        d = version_diff(ctx, "v1", "v2")
    assert d.from_number == 1
    assert d.to_number == 2
    assert d.feature_from == "training"
    assert d.status_to is VersionStatus.REGRESSION


def test_search_command(repo: TmpGitRepo) -> None:
    result = runner.invoke(app, ["search", "learning rate"])
    assert result.exit_code == 0
    assert "V2" in result.output

    result = runner.invoke(app, ["search", "extra.py"])
    assert "V2" in result.output

    result = runner.invoke(app, ["search", "nonexistent-xyzzy"])
    assert "No matches" in result.output
