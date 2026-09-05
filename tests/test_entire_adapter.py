"""EntireAdapter detection - CLI calls are stubbed, so this runs anywhere."""

from __future__ import annotations

import subprocess

import pytest

from devmemory.adapters.entire import EntireAdapter
from tests.conftest import TmpGitRepo


def _completed(stdout: str, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["entire"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_probe_without_binary(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("devmemory.adapters.entire._find_binary", lambda: None)
    status = EntireAdapter(git_repo.path).probe()
    assert status.installed is False
    assert status.enabled is False
    assert status.detail


def test_probe_enabled(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = EntireAdapter(git_repo.path, binary="/fake/entire")

    def fake_run(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        if args[:1] == ("version",):
            return _completed("Entire CLI 9.9.9\nGo version: go1.27.0\n")
        if args[:2] == ("status", "--json"):
            return _completed('{"enabled": true, "agents": ["Claude Code"]}')
        return _completed("", returncode=2)

    monkeypatch.setattr(adapter, "_run", fake_run)
    status = adapter.probe()
    assert status.installed is True
    assert status.enabled is True
    assert status.cli_version == "9.9.9"
    assert status.agents == ["Claude Code"]


def test_probe_installed_but_disabled(
    git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = EntireAdapter(git_repo.path, binary="/fake/entire")

    def fake_run(*args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        if args[:1] == ("version",):
            return _completed("Entire CLI 9.9.9\n")
        if args[:2] == ("status", "--json"):
            return _completed('{"enabled": false, "agents": []}')
        return _completed("", returncode=2)

    monkeypatch.setattr(adapter, "_run", fake_run)
    status = adapter.probe()
    assert status.installed is True
    assert status.enabled is False
    assert "not enabled" in (status.detail or "")


def test_probe_handles_broken_cli(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = EntireAdapter(git_repo.path, binary="/fake/entire")
    monkeypatch.setattr(adapter, "_run", lambda *a, **k: None)
    status = adapter.probe()
    assert status.installed is True
    assert status.enabled is False
