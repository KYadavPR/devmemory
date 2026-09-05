"""Shared fixtures."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from devmemory.config import DevMemoryConfig
from devmemory.paths import ProjectPaths
from devmemory.storage.db import Database


@pytest.fixture
def project_paths(tmp_path: Path) -> ProjectPaths:
    """A scaffolded ``.devmemory/`` layout under a temp directory."""
    paths = ProjectPaths.for_root(tmp_path)
    paths.ensure_scaffold()
    return paths


@pytest.fixture
def config() -> DevMemoryConfig:
    return DevMemoryConfig.default_for(project_id="demo", project_name="Demo")


@pytest.fixture
def database(project_paths: ProjectPaths) -> Iterator[Database]:
    db = Database(project_paths.db)
    try:
        yield db
    finally:
        db.close()


@dataclass
class TmpGitRepo:
    """A real, throwaway git repository for adapter/integration tests."""

    path: Path

    def git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-c", "core.autocrlf=false", *args],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=check,
        )

    def write(self, rel: str, content: str) -> None:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")

    def commit(self, message: str, *, trailers: dict[str, str] | None = None) -> str:
        self.git("add", "-A")
        full = message
        if trailers:
            full += "\n\n" + "\n".join(f"{k}: {v}" for k, v in trailers.items())
        self.git("commit", "-m", full, "--no-verify")
        return self.git("rev-parse", "HEAD").stdout.strip()

    def rev(self, ref: str = "HEAD") -> str:
        return self.git("rev-parse", ref).stdout.strip()

    def _hash_object(self, content: str) -> str:
        # bytes I/O: text mode would translate \n -> \r\n into git's stdin on Windows.
        proc = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=self.path,
            input=content.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        return proc.stdout.decode().strip()

    def _mktree(self, entries: list[tuple[str, str, str, str]]) -> str:
        """entries: (mode, type, sha, name)."""
        payload = "".join(f"{m} {t} {s}\t{n}\n" for m, t, s, n in entries)
        proc = subprocess.run(
            ["git", "mktree"],
            cwd=self.path,
            input=payload.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        return proc.stdout.decode().strip()

    def make_entire_checkpoint(
        self,
        checkpoint_id: str,
        *,
        intent: str,
        agent: str = "Claude Code",
        model: str = "claude-sonnet-5",
        commit_sha: str | None = None,
        strategy: str = "session",
        imported: bool = False,
    ) -> str:
        """Build a realistic ``refs/entire/checkpoints/<shard>/<id>`` ref by hand."""
        session_meta = {
            "cli_version": "0.10.5",
            "checkpoint_id": checkpoint_id,
            "session_id": f"sess-{checkpoint_id[:8]}",
            "strategy": strategy,
            "created_at": "2026-09-06T01:15:00Z",
            "commit_sha": commit_sha,
            "agent": agent,
            "model": model,
            "kind": "imported" if imported else "live",
            "token_usage": {
                "input_tokens": 100,
                "output_tokens": 2000,
                "cache_read_tokens": 5000,
                "cache_creation_tokens": 800,
                "api_call_count": 12,
            },
        }
        root_meta = {
            "cli_version": "0.10.5",
            "checkpoint_id": checkpoint_id,
            "strategy": strategy,
            "commit_sha": commit_sha,
            "checkpoints_count": 1,
            "files_touched": None,
            "sessions": [
                {
                    "metadata": "/0/metadata.json",
                    "transcript": "/0/full.jsonl",
                    "compact_transcript": "/0/transcript.jsonl",
                    "prompt": "/0/prompt.txt",
                }
            ],
            "token_usage": session_meta["token_usage"],
            "imported": imported,
        }
        b_session_meta = self._hash_object(json.dumps(session_meta, indent=2))
        b_prompt = self._hash_object(intent)
        b_transcript = self._hash_object('{"role":"user","content":"' + intent[:20] + '"}\n')
        b_full = self._hash_object('{"type":"session"}\n')
        b_hash = self._hash_object("deadbeef\n")
        sub_tree = self._mktree(
            [
                ("100644", "blob", b_session_meta, "metadata.json"),
                ("100644", "blob", b_prompt, "prompt.txt"),
                ("100644", "blob", b_transcript, "transcript.jsonl"),
                ("100644", "blob", b_full, "full.jsonl"),
                ("100644", "blob", b_hash, "content_hash.txt"),
            ]
        )
        b_root_meta = self._hash_object(json.dumps(root_meta, indent=2))
        root_tree = self._mktree(
            [
                ("100644", "blob", b_root_meta, "metadata.json"),
                ("040000", "tree", sub_tree, "0"),
            ]
        )
        commit = subprocess.run(
            ["git", "commit-tree", root_tree, "-m", f"checkpoint {checkpoint_id}"],
            cwd=self.path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        shard = checkpoint_id[-2:]
        ref = f"refs/entire/checkpoints/{shard}/{checkpoint_id}"
        self.git("update-ref", ref, commit)
        return ref


@pytest.fixture
def git_repo(tmp_path: Path) -> TmpGitRepo:
    repo = TmpGitRepo(tmp_path)
    repo.git("init", "-q", "-b", "main")
    repo.git("config", "user.email", "test@example.com")
    repo.git("config", "user.name", "Test User")
    repo.git("config", "commit.gpgsign", "false")
    return repo
