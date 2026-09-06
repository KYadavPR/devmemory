"""Entire adapter - the only place DevMemory invokes the ``entire`` CLI or reads
its checkpoint git refs.

Checkpoint resolution follows the ladder in docs/IMPLEMENTATION_STRATEGY.md sec. 3:

1. ``Entire-Checkpoint`` git trailer on the commit  (method=trailer, conf 1.0)
2. ``entire checkpoint explain --commit <sha> --json``  (session metadata)
3. direct read of ``refs/entire/checkpoints/<shard>/<id>``  (offline, + intent)
4. time/branch heuristic against ``entire checkpoint list --json``  (conf <= 0.5)
5. nothing - never fabricated

The CLI is authoritative for what it exposes; the git-ref read is the resilience
path when the CLI is absent or its output shape drifts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from devmemory.domain.enums import AssociationMethod
from devmemory.domain.models import (
    CheckpointReference,
    CheckpointSession,
    EntireStatus,
    TokenUsage,
)
from devmemory.logging import get_logger
from devmemory.privacy.boundary import compute_context_status, is_redacted

if TYPE_CHECKING:
    from devmemory.adapters.git import GitAdapter

_log = get_logger(__name__)

_CHECKPOINT_REF_PREFIX = "refs/entire/checkpoints/"
_INTENT_MAX_CHARS = 2000
_HEURISTIC_WINDOW = timedelta(hours=6)


class EntireAdapter:
    """Wraps the installed Entire CLI. Every method degrades gracefully when the
    CLI is absent, disabled, or returns something unexpected - it never raises for
    "Entire is just not here" and never fabricates checkpoint data.
    """

    def __init__(
        self,
        repo_path: Path | str,
        *,
        binary: str | None = None,
        repo: str | None = None,
        git: GitAdapter | None = None,
    ) -> None:
        self._cwd = Path(repo_path).resolve()
        self._repo = repo
        self._binary = binary or _find_binary()
        self._git = git

    # -- process plumbing --------------------------------------------------

    @property
    def binary_path(self) -> str | None:
        return self._binary

    def _run(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str] | None:
        if self._binary is None:
            return None
        cmd = [self._binary, *args]
        if self._repo and "--repo" not in args:
            cmd += ["--repo", self._repo]
        env = {**os.environ, "ENTIRE_TOKEN_STORE": os.environ.get("ENTIRE_TOKEN_STORE", "file")}
        try:
            return subprocess.run(  # noqa: S603 - resolved binary, arg list, no shell
                cmd,
                cwd=self._cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _log.warning("entire.run_failed", args=list(args), error=str(exc))
            return None

    def _run_json(self, *args: str, timeout: int = 30) -> object | None:
        proc = self._run(*args, timeout=timeout)
        if proc is None or proc.returncode != 0 or not proc.stdout.strip():
            return None
        try:
            parsed: object = json.loads(proc.stdout)
        except json.JSONDecodeError:
            _log.warning("entire.bad_json", args=list(args))
            return None
        return parsed

    # -- detection -------------------------------------------------------

    def is_installed(self) -> bool:
        return self._binary is not None

    def cli_version(self) -> str | None:
        proc = self._run("version")
        if proc is None or proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            if line.lower().startswith("entire cli"):
                return line.split("Entire CLI", 1)[-1].strip() or line.strip()
        return proc.stdout.splitlines()[0].strip() if proc.stdout.strip() else None

    def probe(self) -> EntireStatus:
        """Full detection snapshot for ``init`` / ``status`` / ``doctor``."""
        if self._binary is None:
            return EntireStatus(installed=False, detail="entire CLI not found on PATH")

        status = EntireStatus(
            installed=True,
            binary_path=self._binary,
            cli_version=self.cli_version(),
        )
        data = self._run_json("status", "--json")
        if isinstance(data, dict):
            status.enabled = bool(data.get("enabled"))
            agents = data.get("agents")
            if isinstance(agents, list):
                status.agents = [str(a) for a in agents]
            if not status.enabled:
                status.detail = "Entire is installed but not enabled in this repository"
        else:
            status.detail = "could not read `entire status --json`"
        return status

    # -- checkpoint resolution ------------------------------------------

    def resolve_for_commit(
        self,
        commit_sha: str,
        *,
        committed_at: datetime | None = None,
        branch: str | None = None,
    ) -> CheckpointReference | None:
        """Best available checkpoint for a commit, or ``None`` (never fabricated)."""
        checkpoint_id = self._git.entire_checkpoint_trailer(commit_sha) if self._git else None

        if checkpoint_id:
            ref = self._assemble(checkpoint_id, commit_sha=commit_sha)
            if ref is None:
                # Trailer names a checkpoint we cannot read yet (e.g. not fetched).
                ref = CheckpointReference(checkpoint_id=checkpoint_id, commit_sha=commit_sha)
            ref.association_method = AssociationMethod.TRAILER
            ref.association_confidence = AssociationMethod.TRAILER.default_confidence
            return ref

        heuristic = self._heuristic_for_commit(commit_sha, committed_at, branch)
        if heuristic is not None:
            return heuristic
        return None

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointReference | None:
        """A checkpoint by id, with no commit association claim."""
        return self._assemble(checkpoint_id, commit_sha=None)

    def list_checkpoints(self, *, limit: int = 100) -> list[dict[str, object]]:
        data = self._run_json("checkpoint", "list", "--json")
        if not isinstance(data, list):
            return []
        return [d for d in data if isinstance(d, dict)][:limit]

    def list_sessions(self, *, limit: int = 50) -> list[dict[str, object]]:
        """Raw ``entire session list --json`` rows (session_id, agent, status, …).

        Empty list when the CLI is absent, disabled, or the subcommand changed -
        never raises. A session can span many checkpoints and commits (§7).
        """
        data = self._run_json("session", "list", "--json")
        if not isinstance(data, list):
            return []
        return [d for d in data if isinstance(d, dict)][:limit]

    def transcript(self, checkpoint_id: str, *, session_index: int = 0) -> str | None:
        """Compact JSONL transcript for a checkpoint session (CLI, then git ref)."""
        proc = self._run(
            "checkpoint",
            "explain",
            checkpoint_id,
            "--transcript",
            "--session-index",
            str(session_index),
        )
        if proc is not None and proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
        if self._git is not None:
            ref = self._find_ref(checkpoint_id)
            if ref is not None:
                return self._git.cat_ref_blob(ref, f"{session_index}/transcript.jsonl")
        return None

    # -- assembly -----------------------------------------------------

    def _assemble(
        self, checkpoint_id: str, *, commit_sha: str | None
    ) -> CheckpointReference | None:
        """Merge CLI ``explain --json`` (session metadata) with the git-ref tree
        (intent, strategy, commit) into one normalized reference.
        """
        ref = CheckpointReference(checkpoint_id=checkpoint_id, commit_sha=commit_sha)
        found_anything = False

        envelope = self._explain_json(checkpoint_id=checkpoint_id, commit_sha=None)
        if envelope is not None:
            _merge_envelope(ref, envelope)
            found_anything = True

        git_ref = self._find_ref(checkpoint_id)
        if git_ref is not None and self._git is not None:
            ref.ref = git_ref
            if self._merge_git_ref(ref, git_ref):
                found_anything = True

        if not found_anything:
            return None
        if commit_sha and not ref.commit_sha:
            ref.commit_sha = commit_sha

        # Privacy boundary: check for redacted/missing fields and set context status
        redacted = list(ref.redacted_fields)
        if ref.intent is None or is_redacted(ref.intent):
            ref.intent = None
            if "intent" not in redacted:
                redacted.append("intent")

        ref.redacted_fields = sorted(set(redacted))
        ref.context_status = compute_context_status(
            has_checkpoint=True,
            intent=ref.intent,
            redacted_fields=ref.redacted_fields,
        )
        return ref

    def _explain_json(
        self, *, checkpoint_id: str | None = None, commit_sha: str | None = None
    ) -> dict[str, object] | None:
        if commit_sha:
            data = self._run_json("checkpoint", "explain", "--commit", commit_sha, "--json")
        elif checkpoint_id:
            data = self._run_json("checkpoint", "explain", checkpoint_id, "--json")
        else:  # pragma: no cover - guarded by callers
            return None
        return data if isinstance(data, dict) else None

    def _merge_git_ref(self, ref: CheckpointReference, git_ref: str) -> bool:
        assert self._git is not None  # noqa: S101 - callers guard
        root = self._git.cat_ref_blob(git_ref, "metadata.json")
        if root is None:
            return False
        try:
            meta = json.loads(root)
        except json.JSONDecodeError:
            return False
        if not isinstance(meta, dict):
            return False

        ref.strategy = ref.strategy or _str_or_none(meta.get("strategy"))
        ref.commit_sha = ref.commit_sha or _str_or_none(meta.get("commit_sha"))
        ref.imported = bool(meta.get("imported", ref.imported))
        _merge_token_usage(ref.tokens, meta.get("token_usage"))

        sessions = meta.get("sessions")
        if isinstance(sessions, list):
            for idx, session in enumerate(sessions):
                if not isinstance(session, dict):
                    continue
                self._merge_session_from_ref(ref, git_ref, idx, session)
        if ref.intent is None:
            ref.intent = self._read_intent(git_ref, 0)
        if ref.sessions and ref.agent is None:
            ref.agent = ref.sessions[0].agent
            ref.model = ref.model or ref.sessions[0].model
            ref.created_at = ref.created_at or ref.sessions[0].created_at
        return True

    def _merge_session_from_ref(
        self,
        ref: CheckpointReference,
        git_ref: str,
        idx: int,
        session_ptr: dict[str, object],
    ) -> None:
        assert self._git is not None  # noqa: S101
        meta_path = _strip_slash(session_ptr.get("metadata")) or f"{idx}/metadata.json"
        blob = self._git.cat_ref_blob(git_ref, meta_path)
        session = _session_at(ref, idx)
        if blob:
            try:
                sm = json.loads(blob)
            except json.JSONDecodeError:
                sm = {}
            if isinstance(sm, dict):
                session.session_id = session.session_id or _str_or_none(sm.get("session_id"))
                session.agent = session.agent or _str_or_none(sm.get("agent"))
                session.model = session.model or _str_or_none(sm.get("model"))
                session.kind = session.kind or _str_or_none(sm.get("kind"))
                session.created_at = session.created_at or _parse_dt(sm.get("created_at"))
                _merge_token_usage(session.tokens, sm.get("token_usage"))
        if idx == 0 and ref.intent is None:
            ref.intent = self._read_intent(git_ref, idx, session_ptr.get("prompt"))

    def _read_intent(self, git_ref: str, idx: int, prompt_ptr: object | None = None) -> str | None:
        if self._git is None:
            return None
        path = _strip_slash(prompt_ptr) or f"{idx}/prompt.txt"
        text = self._git.cat_ref_blob(git_ref, path)
        if not text:
            return None
        trimmed = text.strip()[:_INTENT_MAX_CHARS] or None
        if trimmed is not None and is_redacted(trimmed):
            return None
        return trimmed

    def _find_ref(self, checkpoint_id: str) -> str | None:
        if self._git is None:
            return None
        for _sha, name in self._git.list_refs(_CHECKPOINT_REF_PREFIX):
            if name.rsplit("/", 1)[-1] == checkpoint_id:
                return name
        return None

    def _heuristic_for_commit(
        self,
        commit_sha: str,
        committed_at: datetime | None,
        branch: str | None,
    ) -> CheckpointReference | None:
        if committed_at is None:
            return None
        best: tuple[float, dict[str, object]] | None = None
        for entry in self.list_checkpoints():
            when = _parse_dt(entry.get("date"))
            if when is None:
                continue
            delta = abs((when - committed_at).total_seconds())
            if delta > _HEURISTIC_WINDOW.total_seconds():
                continue
            if best is None or delta < best[0]:
                best = (delta, entry)
        if best is None:
            return None

        _, entry = best
        checkpoint_id = _str_or_none(entry.get("checkpoint_id")) or _str_or_none(entry.get("id"))
        if not checkpoint_id:
            return None
        ref = self._assemble(checkpoint_id, commit_sha=commit_sha) or CheckpointReference(
            checkpoint_id=checkpoint_id, commit_sha=commit_sha
        )
        ref.association_method = AssociationMethod.HEURISTIC_TIME
        ref.association_confidence = round(
            max(0.2, 0.5 - best[0] / _HEURISTIC_WINDOW.total_seconds() * 0.3), 2
        )
        _log.info(
            "entire.heuristic_match",
            commit=commit_sha[:12],
            checkpoint=checkpoint_id,
            confidence=ref.association_confidence,
        )
        return ref


# --- envelope parsing -------------------------------------------------------------


def _merge_envelope(ref: CheckpointReference, envelope: dict[str, object]) -> None:
    ref.strategy = ref.strategy or _str_or_none(envelope.get("strategy"))
    sessions = envelope.get("sessions")
    if not isinstance(sessions, list):
        return
    for entry in sessions:
        if not isinstance(entry, dict):
            continue
        idx = int(entry.get("index", 0)) if isinstance(entry.get("index"), int) else 0
        session = _session_at(ref, idx)
        session.session_id = session.session_id or _str_or_none(entry.get("session_id"))
        session.agent = session.agent or _str_or_none(entry.get("agent"))
        session.model = session.model or _str_or_none(entry.get("model"))
        session.kind = session.kind or _str_or_none(entry.get("kind"))
        session.created_at = session.created_at or _parse_dt(entry.get("created_at"))
        _merge_token_usage(session.tokens, entry.get("token_usage"))
    if ref.sessions:
        first = ref.sessions[0]
        ref.agent = ref.agent or first.agent
        ref.model = ref.model or first.model
        ref.created_at = ref.created_at or first.created_at
        for session in ref.sessions:
            _merge_token_usage(ref.tokens, session.tokens.model_dump())


def _session_at(ref: CheckpointReference, idx: int) -> CheckpointSession:
    while len(ref.sessions) <= idx:
        ref.sessions.append(CheckpointSession())
    return ref.sessions[idx]


def _merge_token_usage(target: TokenUsage, raw: object) -> None:
    if not isinstance(raw, dict):
        return
    for field in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"):
        value = raw.get(field)
        if isinstance(value, (int, float)) and value > getattr(target, field):
            setattr(target, field, int(value))
    calls = raw.get("api_call_count")
    if isinstance(calls, (int, float)) and calls > target.api_call_count:
        target.api_call_count = int(calls)


# --- small helpers --------------------------------------------------------------


def _str_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _strip_slash(value: object) -> str | None:
    text = _str_or_none(value)
    return text.lstrip("/") if text else None


def _parse_dt(value: object) -> datetime | None:
    text = _str_or_none(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_binary() -> str | None:
    found = shutil.which("entire")
    if found:
        return found
    for candidate in (
        Path.home() / ".local" / "bin" / "entire.exe",
        Path.home() / ".local" / "bin" / "entire",
        Path.home() / "go" / "bin" / "entire.exe",
        Path.home() / "go" / "bin" / "entire",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


__all__ = ["EntireAdapter"]
