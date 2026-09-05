"""CliRunner coverage for checkpoint / history / show rendering."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from devmemory.cli.app import app
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo

runner = CliRunner()


@pytest.fixture
def repo(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> TmpGitRepo:
    monkeypatch.chdir(git_repo.path)
    git_repo.write("app.py", "print('v0')\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    git_repo.commit("chore: devmemory")
    return git_repo


def test_checkpoint_history_show_flow(repo: TmpGitRepo) -> None:
    repo.write("auth.py", "def login(): ...\n")
    repo.commit("feat(auth): add login")

    result = runner.invoke(
        app, ["checkpoint", "--allow-no-entire", "-m", "coverage=70:80", "--tests-passed", "9"]
    )
    assert result.exit_code == 0, result.output
    assert "v1" in result.output.lower()
    assert "recorded" in result.output

    result = runner.invoke(app, ["history"])
    assert result.exit_code == 0
    assert "V1" in result.output
    assert "auth" in result.output.lower()

    result = runner.invoke(app, ["show", "v1", "--diff"])
    assert result.exit_code == 0
    assert "coverage" in result.output
    assert "def login" in result.output

    result = runner.invoke(app, ["show", "1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["version_id"] == "v1"
    assert payload["metrics"][0]["name"] == "coverage"


def test_checkpoint_requires_entire_without_flag(repo: TmpGitRepo) -> None:
    repo.write("x.py", "x = 1\n")
    repo.commit("feat: x")
    result = runner.invoke(app, ["checkpoint"])
    assert result.exit_code == 6
    assert "checkpoint" in result.output.lower()


def test_checkpoint_second_run_is_noop(repo: TmpGitRepo) -> None:
    repo.write("x.py", "x = 1\n")
    repo.commit("feat: x")
    runner.invoke(app, ["checkpoint", "--allow-no-entire"])
    result = runner.invoke(app, ["checkpoint", "--allow-no-entire"])
    assert result.exit_code == 0
    assert "nothing to do" in result.output


def test_show_missing_version(repo: TmpGitRepo) -> None:
    result = runner.invoke(app, ["show", "v9"])
    assert result.exit_code == 9


def test_bad_metric_flag(repo: TmpGitRepo) -> None:
    repo.write("x.py", "x = 1\n")
    repo.commit("feat: x")
    result = runner.invoke(app, ["checkpoint", "--allow-no-entire", "-m", "oops"])
    assert result.exit_code == 1
    assert "metric" in result.output.lower()
