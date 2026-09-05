"""CLI smoke tests."""

from __future__ import annotations

from typer.testing import CliRunner

from devmemory.__about__ import __version__
from devmemory.cli.app import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_version_command_reports_toolchain() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "DevMemory" in result.output
    assert "Python" in result.output
    assert "git" in result.output
    assert "entire" in result.output


def test_no_args_shows_help() -> None:
    # Typer treats "no command" as a usage error (exit 2) but still prints help.
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage" in result.output
    assert "development-memory" in result.output.lower()


def test_help_flag_exits_zero() -> None:
    result = runner.invoke(app, ["-h"])
    assert result.exit_code == 0
    assert "version" in result.output
    assert "--version" in result.output
