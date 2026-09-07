"""Backfill development versions from existing git history.

DevMemory normally records one version per commit going forward. ``backfill``
walks the commits that already exist so a project that adopts DevMemory late
still has a populated timeline (and data for the dashboard, analytics and Ask).

Each commit is recorded *lightweight*: no Entire checkpoint, no test run, no
source snapshot, and - unless ``analyze=True`` - no LLM analysis. Just the git
facts, feature detection, and a regression comparison against the previous
version. Commits DevMemory has already seen are left untouched.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel

from devmemory.domain.errors import DevMemoryError
from devmemory.logging import get_logger
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.storage.versions import VersionRepository

_log = get_logger(__name__)

ProgressFn = Callable[[int, int, str], None]


class BackfillItem(BaseModel):
    commit: str
    version_id: str | None = None
    created: bool = False
    skipped: bool = False
    error: str | None = None


class BackfillReport(BaseModel):
    scanned: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
    items: list[BackfillItem] = []


def backfill_history(
    ctx: ProjectContext,
    *,
    limit: int = 200,
    since: str | None = None,
    analyze: bool = False,
    snapshot: bool = False,
    on_progress: ProgressFn | None = None,
) -> BackfillReport:
    """Record a lightweight version for every unseen commit in the recent history."""
    if not ctx.git.is_repository() or not ctx.git.has_commits():
        raise DevMemoryError(
            "No git history to backfill.",
            hint="Commit something first, then run `devmemory backfill`.",
        )

    shas = ctx.git.rev_list(limit=limit, since=since)
    repo = VersionRepository(ctx.db)
    report = BackfillReport()
    total = len(shas)

    for i, sha in enumerate(shas, start=1):
        if on_progress is not None:
            on_progress(i, total, sha)
        report.scanned += 1

        if repo.find_by_commit(ctx.config.project_id, sha) is not None:
            report.skipped += 1
            report.items.append(BackfillItem(commit=sha, skipped=True))
            continue

        request = CheckpointRequest(
            target=sha,
            lightweight=True,
            skip_analysis=not analyze,
            snapshot=snapshot,
            run_tests=False,
            allow_no_entire=True,
        )
        try:
            result = run_checkpoint(ctx, request)
        except DevMemoryError as exc:
            report.failed += 1
            report.items.append(BackfillItem(commit=sha, error=exc.message))
            _log.warning("backfill.commit_failed", commit=sha[:12], error=exc.message)
            continue
        except Exception as exc:  # never abort the whole backfill for one bad commit
            report.failed += 1
            report.items.append(
                BackfillItem(commit=sha, error=f"{type(exc).__name__}: {exc}")
            )
            _log.warning("backfill.commit_errored", commit=sha[:12], error=str(exc))
            continue

        if result.created:
            report.created += 1
        else:
            report.skipped += 1
        report.items.append(
            BackfillItem(
                commit=sha,
                version_id=result.version.version_id,
                created=result.created,
            )
        )

    _log.info(
        "backfill.done",
        scanned=report.scanned,
        created=report.created,
        skipped=report.skipped,
        failed=report.failed,
    )
    return report


__all__ = ["BackfillItem", "BackfillReport", "backfill_history"]
