"""Git adapter - the only place DevMemory shells out to ``git``.

Design rules (see docs/IMPLEMENTATION_STRATEGY.md sec. 4):

* subprocess against the ``git`` CLI, no GitPython
* every call runs with an explicit ``cwd`` and a hardened environment
* ``-c core.autocrlf=false`` and ``--no-pager`` so output is stable on Windows
* NUL-delimited (``-z``) parsing wherever git offers it
* paths are returned POSIX-style; the working tree is never modified here
  (restore lives in a separate, guarded adapter method added in Phase 9)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from devmemory.domain.enums import ChangeType
from devmemory.domain.errors import GitError, GitRepositoryNotFoundError
from devmemory.domain.models import (
    ChangedFile,
    CommitInfo,
    DiffStat,
    WorkingTreeState,
)
from devmemory.logging import get_logger

_log = get_logger(__name__)

_NUL = "\x00"
_FIELD_SEP = "\x1f"  # unit separator - unlikely in commit metadata

# git show -s format: sha, parents, author name/email/date, committer name/email/date, subject, body
_COMMIT_FORMAT = _FIELD_SEP.join(["%H", "%P", "%an", "%ae", "%aI", "%cn", "%ce", "%cI", "%s", "%b"])


class GitAdapter:
    """Read-only git operations for one repository."""

    def __init__(self, repo_path: Path | str, *, git_binary: str | None = None) -> None:
        self._cwd = Path(repo_path).resolve()
        self._git = git_binary or shutil.which("git") or "git"

    # -- process plumbing ----------------------------------------------------

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = [
            self._git,
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.quotepath=false",
            "--no-pager",
            *args,
        ]
        env = {
            **os.environ,
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_PAGER": "cat",
            "LC_ALL": "C",
        }
        try:
            proc = subprocess.run(  # noqa: S603 - fixed binary, arg list, no shell
                cmd,
                cwd=self._cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except FileNotFoundError as exc:
            raise GitError(f"git executable not found: {self._git}") from exc
        except subprocess.TimeoutExpired as exc:
            raise GitError(f"git {' '.join(args)} timed out") from exc

        if check and proc.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
            )
        return proc

    def _out(self, *args: str) -> str:
        return self._run(*args).stdout.strip()

    def _raw(self, *args: str) -> str:
        """stdout with no stripping - for NUL-delimited (`-z`) output."""
        return self._run(*args).stdout

    def _run_bytes(self, *args: str) -> bytes:
        cmd = [self._git, "-c", "core.autocrlf=false", "--no-pager", *args]
        env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}
        try:
            proc = subprocess.run(  # noqa: S603 - fixed binary, arg list, no shell
                cmd, cwd=self._cwd, env=env, capture_output=True, timeout=300
            )
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise GitError(f"git {' '.join(args)} failed: {exc}") from exc
        if proc.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} failed ({proc.returncode}): "
                f"{proc.stderr.decode(errors='replace').strip()}"
            )
        return proc.stdout

    # -- repository ---------------------------------------------------------

    def is_repository(self) -> bool:
        proc = self._run("rev-parse", "--is-inside-work-tree", check=False)
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def require_repository(self) -> None:
        if not self.is_repository():
            raise GitRepositoryNotFoundError(
                f"{self._cwd} is not inside a git repository.",
            )

    def repo_root(self) -> Path:
        self.require_repository()
        return Path(self._out("rev-parse", "--show-toplevel"))

    def git_version(self) -> str | None:
        proc = self._run("--version", check=False)
        return proc.stdout.strip() or None if proc.returncode == 0 else None

    # -- refs & commits ---------------------------------------------------

    def has_commits(self) -> bool:
        return self._run("rev-parse", "--verify", "HEAD", check=False).returncode == 0

    def current_branch(self) -> str | None:
        """Current branch name, or ``None`` when detached or on an unborn branch."""
        proc = self._run("branch", "--show-current", check=False)
        branch = proc.stdout.strip() if proc.returncode == 0 else ""
        return branch or None

    def resolve(self, rev: str) -> str:
        """Resolve a revision (``HEAD``, ``v1``, a short sha, ...) to a full sha."""
        proc = self._run("rev-parse", "--verify", f"{rev}^{{commit}}", check=False)
        if proc.returncode != 0:
            raise GitError(f"cannot resolve revision {rev!r}")
        return proc.stdout.strip()

    def head_sha(self) -> str | None:
        return self.resolve("HEAD") if self.has_commits() else None

    def commit(self, rev: str = "HEAD") -> CommitInfo:
        """Full metadata for one commit, including parsed trailers."""
        sha = self.resolve(rev)
        raw = self._run("show", "-s", f"--format={_COMMIT_FORMAT}", sha).stdout
        parts = raw.split(_FIELD_SEP)
        # %b can itself contain newlines; everything after the 9th sep is the body.
        while len(parts) < 10:
            parts.append("")
        fields = parts[:9]
        body = _FIELD_SEP.join(parts[9:]).strip("\n")

        return CommitInfo(
            sha=fields[0].strip(),
            parents=fields[1].split() if fields[1].strip() else [],
            author_name=fields[2],
            author_email=fields[3],
            authored_at=_parse_iso(fields[4]),
            committer_name=fields[5],
            committer_email=fields[6],
            committed_at=_parse_iso(fields[7]),
            subject=fields[8],
            body=body,
            trailers=self._trailers(sha),
        )

    def _trailers(self, sha: str) -> dict[str, list[str]]:
        raw = self._run(
            "show",
            "-s",
            "--format=%(trailers:only=true,unfold=true,key_value_separator=%x1f)",
            sha,
        ).stdout
        trailers: dict[str, list[str]] = {}
        for line in raw.splitlines():
            if _FIELD_SEP not in line:
                continue
            key, _, value = line.partition(_FIELD_SEP)
            trailers.setdefault(key.strip(), []).append(value.strip())
        return trailers

    def entire_checkpoint_trailer(self, rev: str = "HEAD") -> str | None:
        """The ``Entire-Checkpoint`` trailer value for a commit, if present."""
        sha = self.resolve(rev)
        value = self._out(
            "show",
            "-s",
            "--format=%(trailers:key=Entire-Checkpoint,valueonly=true,unfold=true)",
            sha,
        ).strip()
        return value or None

    def parent_sha(self, rev: str = "HEAD") -> str | None:
        info = self.commit(rev)
        return info.parent

    # -- diffs -----------------------------------------------------------

    def changed_files(self, base: str | None, head: str) -> list[ChangedFile]:
        """Files changed between ``base`` and ``head`` (or introduced by ``head``).

        Parses ``git`` NUL-delimited (`-z`) output, in which name-status entries
        are ``<code>\\0<path>\\0`` (or ``<code>\\0<old>\\0<new>\\0`` for R/C) and
        numstat entries are ``<add>\\t<del>\\t<path>\\0`` (with an empty path and
        two following tokens for renames).
        """
        head_sha = self.resolve(head)
        if base is None:
            status_raw = self._raw(
                "show", "--first-parent", "-M", "-C", "--name-status", "--format=", "-z", head_sha
            )
            numstat_raw = self._raw("show", "--numstat", "--format=", "-z", head_sha)
        else:
            base_sha = self.resolve(base)
            status_raw = self._raw("diff", "-M", "-C", "--name-status", "-z", base_sha, head_sha)
            numstat_raw = self._raw("diff", "--numstat", "-z", base_sha, head_sha)

        stats = _parse_numstat_z(numstat_raw)
        result: list[ChangedFile] = []
        for code, old_path, path in _parse_name_status_z(status_raw):
            add, dele, binary = stats.get(path, (0, 0, False))
            result.append(
                ChangedFile(
                    path=path,
                    old_path=old_path,
                    change_type=ChangeType.from_git_status(code),
                    additions=add,
                    deletions=dele,
                    binary=binary,
                )
            )
        return result

    def diff_text(self, base: str | None, head: str, *, paths: list[str] | None = None) -> str:
        head_sha = self.resolve(head)
        if base is None:
            args = ["show", "--no-color", "--first-parent", "--format=", head_sha]
        else:
            args = ["diff", "--no-color", self.resolve(base), head_sha]
        if paths:
            args += ["--", *paths]
        return self._run(*args).stdout

    def diff_stat(self, base: str | None, head: str) -> DiffStat:
        return DiffStat.from_files(self.changed_files(base, head))

    def show_file(self, rev: str, path: str) -> str | None:
        proc = self._run("show", f"{self.resolve(rev)}:{path}", check=False)
        return proc.stdout if proc.returncode == 0 else None

    # -- history --------------------------------------------------------

    def commits_between(self, base: str | None, head: str, *, limit: int = 200) -> list[str]:
        rev_range = head if base is None else f"{base}..{head}"
        out = self._out("rev-list", f"--max-count={limit}", rev_range)
        return out.splitlines() if out else []

    def rev_list(
        self,
        *,
        limit: int = 200,
        since: str | None = None,
        first_parent: bool = True,
        no_merges: bool = True,
        rev: str = "HEAD",
    ) -> list[str]:
        """Commit shas from ``rev`` backwards, returned oldest-first.

        ``--max-count`` is applied before ``--reverse``, so this yields the
        oldest members of the most recent ``limit`` commits - the right window
        for backfilling a timeline.
        """
        args = ["rev-list", f"--max-count={limit}", "--reverse"]
        if first_parent:
            args.append("--first-parent")
        if no_merges:
            args.append("--no-merges")
        if since:
            args.append(f"--since={since}")
        args.append(rev)
        out = self._out(*args)
        return out.splitlines() if out else []

    def cat_ref_blob(self, ref: str, path: str) -> str | None:
        """Read a blob from an arbitrary ref/tree (used for Entire checkpoint refs)."""
        proc = self._run("cat-file", "-p", f"{ref}:{path}", check=False)
        return proc.stdout if proc.returncode == 0 else None

    def list_refs(self, pattern: str) -> list[tuple[str, str]]:
        """``(sha, refname)`` for refs matching a glob (e.g. ``refs/entire/checkpoints/``)."""
        out = self._out("for-each-ref", "--format=%(objectname)%09%(refname)", pattern)
        pairs: list[tuple[str, str]] = []
        for line in out.splitlines():
            if "\t" in line:
                sha, name = line.split("\t", 1)
                pairs.append((sha.strip(), name.strip()))
        return pairs

    # -- working tree --------------------------------------------------

    def working_tree_state(self) -> WorkingTreeState:
        branch = self.current_branch()
        state = WorkingTreeState(
            branch=branch,
            detached=branch is None and self.has_commits(),
            head=self.head_sha(),
        )
        for entry in _split_nul(self._raw("status", "--porcelain=v1", "-z")):
            if len(entry) < 4:
                continue
            x, y, name = entry[0], entry[1], entry[3:]
            if x == "?" and y == "?":
                state.untracked.append(name)
                continue
            if x not in (" ", "?"):
                state.staged.append(name)
            if y not in (" ", "?"):
                state.unstaged.append(name)
        return state

    def is_dirty(self) -> bool:
        return not self.working_tree_state().is_clean

    # -- snapshots & restore (the only mutating operations) --------------

    def archive_tar(self, rev: str) -> bytes:
        """The committed tree at ``rev`` as an uncompressed tar (bytes)."""
        return self._run_bytes("archive", "--format=tar", self.resolve(rev))

    def create_tag(self, name: str, rev: str = "HEAD", *, message: str | None = None) -> None:
        args = ["tag", name, self.resolve(rev)]
        if message:
            args = ["tag", "-a", name, "-m", message, self.resolve(rev)]
        self._run(*args)

    def stash_create(self) -> str | None:
        """Object id of a commit capturing the current dirty state, or ``None`` if clean.

        ``git stash create`` records but does not touch the working tree or the
        stash list - a pure safety reference.
        """
        out = self._out("stash", "create", "devmemory: pre-restore safety")
        return out or None

    def checkout_detached(self, rev: str) -> str:
        """Move HEAD to ``rev`` in detached state, keeping local changes out of the way."""
        sha = self.resolve(rev)
        self._run("checkout", "--detach", "--force", sha)
        return sha

    def reset_hard(self, rev: str) -> str:
        sha = self.resolve(rev)
        self._run("reset", "--hard", sha)
        return sha

    def restore_worktree_paths(self, rev: str, paths: list[str]) -> None:
        if paths:
            self._run("checkout", self.resolve(rev), "--", *paths)


# --- helpers ----------------------------------------------------------------------


def _parse_iso(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _split_nul(raw: str) -> list[str]:
    return [chunk for chunk in raw.split(_NUL) if chunk != ""]


def _parse_name_status_z(raw: str) -> list[tuple[str, str | None, str]]:
    """``[(code, old_path | None, path), ...]`` from ``--name-status -z`` output."""
    tokens = _split_nul(raw)
    entries: list[tuple[str, str | None, str]] = []
    i = 0
    while i < len(tokens):
        code = tokens[i]
        i += 1
        if not code or i >= len(tokens):
            break
        if code[:1].upper() in ("R", "C") and i + 1 < len(tokens) + 1:
            old_path = tokens[i]
            path = tokens[i + 1] if i + 1 < len(tokens) else old_path
            i += 2
            entries.append((code, old_path, path))
        else:
            entries.append((code, None, tokens[i]))
            i += 1
    return entries


def _parse_numstat_z(raw: str) -> dict[str, tuple[int, int, bool]]:
    """``{path: (additions, deletions, binary)}`` from ``--numstat -z`` output."""
    tokens = _split_nul(raw)
    stats: dict[str, tuple[int, int, bool]] = {}
    i = 0
    while i < len(tokens):
        bits = tokens[i].split("\t")
        if len(bits) < 3:
            i += 1
            continue
        add_s, del_s, path = bits[0], bits[1], bits[2]
        i += 1
        if path == "" and i + 1 < len(tokens):
            # Rename: the following two tokens are old, new.
            path = tokens[i + 1]
            i += 2
        binary = add_s == "-" or del_s == "-"
        stats[path] = (
            0 if binary else int(add_s or 0),
            0 if binary else int(del_s or 0),
            binary,
        )
    return stats


__all__ = ["GitAdapter"]
