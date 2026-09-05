"""Restoring the working tree to an earlier development version - safely.

Restore is potentially destructive, so:

1. Resolve the target version to its git commit.
2. Inspect the working tree; refuse if there are uncommitted changes unless the
   caller explicitly allows it.
3. Record a safety reference: a tag at the current HEAD, plus a ``git stash
   create`` object if the tree is dirty.
4. Only then move HEAD - detached checkout by default, ``git reset --hard`` only
   when explicitly asked.
5. Record a ``restore`` event.

``preview`` performs steps 1-2 and reports what *would* happen, touching nothing.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel

from devmemory.domain.errors import DevMemoryError, RestoreSafetyError
from devmemory.logging import get_logger
from devmemory.services.context import ProjectContext
from devmemory.services.versions import get_version

_log = get_logger(__name__)


class RestorePreview(BaseModel):
    version_id: str
    target_commit: str
    target_subject: str
    current_commit: str | None
    current_branch: str | None
    already_there: bool
    working_tree_clean: bool
    uncommitted: list[str]
    untracked: list[str]
    safety_tag: str
    warning: str


class RestoreResult(BaseModel):
    version_id: str
    mode: str  # 'detach' | 'hard'
    target_commit: str
    previous_commit: str | None
    safety_tag: str
    stash_ref: str | None
    message: str


def restore_preview(ctx: ProjectContext, ref: str) -> RestorePreview:
    v = get_version(ctx, ref)
    state = ctx.git.working_tree_state()
    current = ctx.git.head_sha()
    target_info = ctx.git.commit(v.git_commit)

    return RestorePreview(
        version_id=v.version_id,
        target_commit=v.git_commit,
        target_subject=target_info.subject,
        current_commit=current,
        current_branch=state.branch,
        already_there=current == v.git_commit,
        working_tree_clean=state.is_clean,
        uncommitted=[*state.staged, *state.unstaged],
        untracked=state.untracked,
        safety_tag=_safety_tag_name(),
        warning=(
            f"This moves the working tree to the state of {v.version_id.upper()} "
            f"(git {v.git_commit[:12]}). "
            + (
                "Your uncommitted changes would be at risk."
                if state.has_uncommitted_changes
                else "A safety tag is created at the current HEAD first."
            )
        ),
    )


def restore_version(
    ctx: ProjectContext,
    ref: str,
    *,
    mode: str = "detach",
    allow_dirty: bool = False,
) -> RestoreResult:
    if mode not in ("detach", "hard"):
        raise DevMemoryError(f"unknown restore mode {mode!r}")

    v = get_version(ctx, ref)
    state = ctx.git.working_tree_state()
    current = ctx.git.head_sha()

    if current == v.git_commit and state.is_clean:
        return RestoreResult(
            version_id=v.version_id,
            mode=mode,
            target_commit=v.git_commit,
            previous_commit=current,
            safety_tag="",
            stash_ref=None,
            message=f"Already at {v.version_id.upper()} with a clean tree; nothing to do.",
        )

    if state.has_uncommitted_changes and not allow_dirty:
        raise RestoreSafetyError(
            f"{len(state.staged) + len(state.unstaged)} uncommitted change(s) would be at risk.",
            hint="Commit or stash them, or pass --allow-dirty to keep a safety stash and proceed.",
        )

    safety_tag = _safety_tag_name()
    ctx.git.create_tag(
        safety_tag,
        "HEAD",
        message=f"devmemory: state before restoring {v.version_id}",
    )
    stash_ref = ctx.git.stash_create() if state.has_uncommitted_changes else None

    try:
        if mode == "hard":
            ctx.git.reset_hard(v.git_commit)
        else:
            ctx.git.checkout_detached(v.git_commit)
    except DevMemoryError:
        _log.error("restore.failed", version=v.version_id, safety_tag=safety_tag)
        raise

    _record_restore(ctx, v.version_id, v.git_commit, current, safety_tag, stash_ref, mode)
    _log.info(
        "restore.done",
        version=v.version_id,
        commit=v.git_commit[:12],
        mode=mode,
        safety_tag=safety_tag,
    )
    recover = f"git reset --hard {safety_tag}" if mode == "hard" else "git switch -"
    return RestoreResult(
        version_id=v.version_id,
        mode=mode,
        target_commit=v.git_commit,
        previous_commit=current,
        safety_tag=safety_tag,
        stash_ref=stash_ref,
        message=(
            f"Working tree restored to {v.version_id.upper()} ({v.git_commit[:12]}). "
            f"Recover the previous state with `{recover}`"
            + (f" and `git stash apply {stash_ref}`" if stash_ref else "")
            + "."
        ),
    )


def _safety_tag_name() -> str:
    return "devmemory/safety/" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _record_restore(
    ctx: ProjectContext,
    version_id: str,
    target: str,
    previous: str | None,
    safety_tag: str,
    stash_ref: str | None,
    mode: str,
) -> None:
    with ctx.db.transaction() as conn:
        conn.execute(
            "INSERT INTO events (event_id, project_id, version_id, type, source, payload_json, "
            "created_at) VALUES (?, ?, ?, 'restore', 'devmemory', ?, ?)",
            (
                uuid.uuid4().hex,
                ctx.config.project_id,
                version_id,
                json.dumps(
                    {
                        "target": target,
                        "previous": previous,
                        "safety_tag": safety_tag,
                        "stash_ref": stash_ref,
                        "mode": mode,
                    }
                ),
                datetime.now(UTC).isoformat(),
            ),
        )


__all__ = ["RestorePreview", "RestoreResult", "restore_preview", "restore_version"]
