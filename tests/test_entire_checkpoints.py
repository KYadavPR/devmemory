"""EntireAdapter checkpoint resolution - the trailer -> CLI -> git-ref ladder."""

from __future__ import annotations

import subprocess

import pytest

from devmemory.adapters.entire import EntireAdapter
from devmemory.adapters.git import GitAdapter
from devmemory.domain.enums import AssociationMethod
from tests.conftest import TmpGitRepo

CP_ID = "8149ec99eeae"
CP_ULID = "01K9TQ8ZP7X3F5M2WVJ4CNRB6D"


def _adapter(repo: TmpGitRepo, *, binary: str | None = "/fake/entire") -> EntireAdapter:
    return EntireAdapter(repo.path, binary=binary, git=GitAdapter(repo.path))


def test_resolve_via_trailer_and_git_ref_offline(git_repo: TmpGitRepo) -> None:
    git_repo.write("model.py", "lr = 0.001\n")
    sha = git_repo.commit("feat: model", trailers={"Entire-Checkpoint": CP_ID})
    git_repo.make_entire_checkpoint(
        CP_ID, intent="Improve image classification accuracy", commit_sha=sha
    )

    # No working CLI - the git-ref read must carry it.
    adapter = _adapter(git_repo, binary=None)
    ref = adapter.resolve_for_commit(sha)

    assert ref is not None
    assert ref.checkpoint_id == CP_ID
    assert ref.association_method is AssociationMethod.TRAILER
    assert ref.association_confidence == 1.0
    assert ref.intent == "Improve image classification accuracy"
    assert ref.agent == "Claude Code"
    assert ref.model == "claude-sonnet-5"
    assert ref.commit_sha == sha
    assert ref.is_linked is True
    assert ref.is_uncertain is False


def test_resolve_merges_cli_envelope_with_git_ref(
    git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    git_repo.write("a.py", "x = 1\n")
    sha = git_repo.commit("feat: a", trailers={"Entire-Checkpoint": CP_ULID})
    git_repo.make_entire_checkpoint(CP_ULID, intent="Add feature A", commit_sha=sha)

    adapter = _adapter(git_repo)
    envelope = {
        "checkpoint_id": CP_ULID,
        "strategy": "session",
        "sessions": [
            {
                "index": 0,
                "session_id": "sess-live",
                "agent": "Claude Code",
                "model": "claude-opus-5",
                "kind": "live",
                "created_at": "2026-09-06T01:20:00Z",
                "token_usage": {"input_tokens": 5, "output_tokens": 50},
            }
        ],
    }

    def fake_run_json(*args: str, timeout: int = 30) -> object | None:
        if args[:2] == ("checkpoint", "explain"):
            return envelope
        return None

    monkeypatch.setattr(adapter, "_run_json", fake_run_json)
    ref = adapter.resolve_for_commit(sha)

    assert ref is not None
    assert ref.sessions[0].model == "claude-opus-5"  # from CLI envelope
    assert ref.intent == "Add feature A"  # from git ref (CLI never has it)
    assert ref.ref == f"refs/entire/checkpoints/{CP_ULID[-2:]}/{CP_ULID}"


def test_no_trailer_no_heuristic_returns_none(git_repo: TmpGitRepo) -> None:
    git_repo.write("a.py", "x = 1\n")
    sha = git_repo.commit("no checkpoint here")
    adapter = _adapter(git_repo, binary=None)
    assert adapter.resolve_for_commit(sha) is None


def test_trailer_present_but_checkpoint_unreadable(git_repo: TmpGitRepo) -> None:
    git_repo.write("a.py", "x = 1\n")
    sha = git_repo.commit("feat: a", trailers={"Entire-Checkpoint": "ffffffffffff"})
    adapter = _adapter(git_repo, binary=None)
    ref = adapter.resolve_for_commit(sha)

    # We still record the link (from the trailer) but with no context.
    assert ref is not None
    assert ref.checkpoint_id == "ffffffffffff"
    assert ref.association_method is AssociationMethod.TRAILER
    assert ref.intent is None
    assert ref.agent is None


def test_heuristic_match_is_low_confidence(
    git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    git_repo.write("a.py", "x = 1\n")
    sha = git_repo.commit("feat: a")  # no trailer
    git_repo.make_entire_checkpoint(CP_ID, intent="nearby work", commit_sha=None)

    adapter = _adapter(git_repo)
    committed_at = git_repo.git("show", "-s", "--format=%cI", sha).stdout.strip()

    monkeypatch.setattr(
        adapter,
        "list_checkpoints",
        lambda **_: [{"checkpoint_id": CP_ID, "date": committed_at}],
    )
    from datetime import datetime

    ref = adapter.resolve_for_commit(sha, committed_at=datetime.fromisoformat(committed_at))
    assert ref is not None
    assert ref.association_method is AssociationMethod.HEURISTIC_TIME
    assert ref.association_confidence < 0.8
    assert ref.is_uncertain is True


def test_get_checkpoint_by_id(git_repo: TmpGitRepo) -> None:
    git_repo.write("a.py", "x = 1\n")
    git_repo.commit("base")
    git_repo.make_entire_checkpoint(CP_ID, intent="standalone", commit_sha=None)

    adapter = _adapter(git_repo, binary=None)
    ref = adapter.get_checkpoint(CP_ID)
    assert ref is not None
    assert ref.intent == "standalone"
    assert ref.association_method is AssociationMethod.NONE


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


pytestmark = pytest.mark.skipif(not _has_git(), reason="git not available")
