"""Integration checks against the *real* installed Entire CLI.

Skipped automatically when Entire is not on PATH. These guard against the CLI's
``--json`` shapes drifting from what the adapter parses.
"""

from __future__ import annotations

import pytest

from devmemory.adapters.entire import EntireAdapter, _find_binary
from devmemory.adapters.git import GitAdapter
from tests.conftest import TmpGitRepo

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_find_binary() is None, reason="entire CLI not installed"),
]


def test_probe_against_real_cli(git_repo: TmpGitRepo) -> None:
    git_repo.write("app.py", "print('hi')\n")
    git_repo.commit("feat: hello")

    adapter = EntireAdapter(git_repo.path, git=GitAdapter(git_repo.path))
    before = adapter.probe()
    assert before.installed is True
    assert before.enabled is False  # not enabled yet

    result = git_repo.git("config", "--local", "--get", "user.email")  # sanity: repo is usable
    assert result.returncode == 0

    enable = _run_entire(
        adapter, "enable", "--agent", "claude-code", "--yes", "--no-github", "--telemetry=false"
    )
    assert enable == 0, "entire enable failed"

    after = adapter.probe()
    assert after.installed is True
    assert after.enabled is True
    assert any("claude" in a.lower() for a in after.agents)


def test_explain_commit_without_trailer_is_none(git_repo: TmpGitRepo) -> None:
    git_repo.write("app.py", "print('hi')\n")
    sha = git_repo.commit("feat: hello")  # no Entire-Checkpoint trailer

    adapter = EntireAdapter(git_repo.path, git=GitAdapter(git_repo.path))
    _run_entire(
        adapter, "enable", "--agent", "claude-code", "--yes", "--no-github", "--telemetry=false"
    )

    assert adapter.resolve_for_commit(sha) is None


def _run_entire(adapter: EntireAdapter, *args: str) -> int:
    proc = adapter._run(*args, timeout=60)
    return proc.returncode if proc is not None else -1
