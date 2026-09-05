"""CLI tests for `devmemory init` and `devmemory status`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devmemory.cli.app import app
from tests.conftest import TmpGitRepo

runner = CliRunner()


def test_init_and_status_flow(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo.path)
    git_repo.write("app.py", "print('hi')\n")
    git_repo.commit("feat: hello")

    result = runner.invoke(app, ["init", "--name", "Demo Project"])
    assert result.exit_code == 0, result.output
    assert "initialized" in result.output.lower()

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Demo Project" in result.output
    assert "main" in result.output


def test_init_json_output(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo.path)
    result = runner.invoke(app, ["init", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["project"]["project_id"]
    assert "environment" in payload


def test_init_outside_git_repo_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 4
    assert "git" in result.output.lower()


def test_status_without_init_errors(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(git_repo.path)
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 3
    assert "init" in result.output.lower()
