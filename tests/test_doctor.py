"""Phase 14: `devmemory doctor`."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from devmemory.cli.app import app
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo

runner = CliRunner()


def test_doctor_outside_a_project(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "python" in result.output
    assert "run `devmemory init`" in result.output


def test_doctor_strict_fails_without_a_project(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[arg-type]
    result = runner.invoke(app, ["doctor", "--strict"])
    assert result.exit_code == 1


def test_doctor_reports_a_healthy_project(
    git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    git_repo.write("app.py", "x = 1\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    monkeypatch.chdir(git_repo.path)

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Demo (demo)" in result.output
    assert "schema" in result.output
    # credential presence is reported, never a value
    assert "not set" in result.output or "absent" in result.output


def test_doctor_never_prints_secret_values(
    git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    git_repo.write("app.py", "x = 1\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    monkeypatch.chdir(git_repo.path)
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.databricks.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-super-secret-value")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh-123")

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "dapi-super-secret-value" not in result.output
    assert "set" in result.output
