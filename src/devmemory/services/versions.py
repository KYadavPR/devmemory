"""Development-version services: create from an event, read, list, diff, search."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel

from devmemory.domain.enums import AssociationMethod, FeatureStatus, VersionStatus
from devmemory.domain.errors import DevMemoryError
from devmemory.domain.models import (
    ChangedFile,
    DevelopmentEvent,
    DevelopmentVersion,
    DiffStat,
    Regression,
)
from devmemory.logging import get_logger
from devmemory.services.context import ProjectContext
from devmemory.storage.repositories import FeatureRepository
from devmemory.storage.versions import VersionRepository

_log = get_logger(__name__)


class VersionExistsError(DevMemoryError):
    """A version already exists for this commit."""

    exit_code = 8

    def __init__(self, version: DevelopmentVersion) -> None:
        super().__init__(
            f"{version.version_id} already records commit {version.git_commit[:12]}.",
            hint="Nothing to do. Use `--force` to supersede it (a later phase).",
        )
        self.version = version


class VersionNotFoundError(DevMemoryError):
    exit_code = 9


class VersionDiff(BaseModel):
    from_version_id: str
    to_version_id: str
    from_commit: str
    to_commit: str
    files: list[ChangedFile]
    stat: DiffStat
    diff_text: str
    metric_changes: dict[str, dict[str, float | None]]
    test_changes: dict[str, int | None]
    status_from: VersionStatus
    status_to: VersionStatus


def create_version_from_event(
    ctx: ProjectContext,
    event: DevelopmentEvent,
    *,
    force: bool = False,
    regressions: list[Regression] | None = None,
) -> DevelopmentVersion:
    """Persist a normalized event as a new :class:`DevelopmentVersion`.

    The checkpoint pipeline assembles ``event`` (status, tests, metrics) and the
    detected ``regressions`` before calling in; the analysis layer is applied
    afterwards via :func:`~devmemory.services.versions.set_analysis`.
    """
    repo = VersionRepository(ctx.db)

    existing = repo.find_by_commit(event.project_id, event.commit.sha)
    if existing is not None and not force:
        raise VersionExistsError(existing)

    if existing is not None:
        number = existing.version_number
        version_id = existing.version_id
    else:
        number = repo.next_version_number(event.project_id)
        version_id = f"v{number}"

    feature_id = _resolve_feature(ctx, event)

    checkpoint = event.checkpoint
    version = DevelopmentVersion(
        version_id=version_id,
        version_number=number,
        project_id=event.project_id,
        intent=event.intent or (checkpoint.intent if checkpoint else None) or event.commit.subject,
        agent=event.agent or (checkpoint.agent if checkpoint else None),
        model=event.model or (checkpoint.model if checkpoint else None),
        git_commit=event.commit.sha,
        parent_commit=event.parent_commit or event.commit.parent,
        branch=event.branch,
        feature_id=feature_id,
        status=event.status or VersionStatus.NEEDS_REVIEW,
        files_changed=len(event.changed_files),
        lines_added=event.diff_stat.additions,
        lines_removed=event.diff_stat.deletions,
        changed_files=event.changed_files,
        primary_checkpoint=checkpoint,
        checkpoint_ids=[checkpoint.checkpoint_id] if checkpoint else [],
        entire_association_method=(
            checkpoint.association_method if checkpoint else AssociationMethod.NONE
        ),
        entire_association_confidence=(checkpoint.association_confidence if checkpoint else 0.0),
        tests=event.tests,
        metrics=event.metrics,
        regressions=[r.model_copy(update={"version_id": version_id}) for r in (regressions or [])],
        environment=event.environment,
        run_id=event.run_id,
        created_at=datetime.now(UTC),
        committed_at=event.commit.committed_at,
    )

    replaced = existing is not None
    stored = (
        repo.replace(version, source_event=event)
        if replaced
        else repo.create(version, source_event=event)
    )

    _record_event(
        ctx,
        version_id=stored.version_id,
        event_type="version.replaced" if replaced else "version.created",
        payload={
            "commit": stored.git_commit,
            "status": stored.status.value,
            "checkpoint": stored.primary_checkpoint.checkpoint_id
            if stored.primary_checkpoint
            else None,
            "regressions": len(stored.regressions),
        },
    )
    _log.info(
        "version.replaced" if replaced else "version.created",
        version=stored.version_id,
        commit=stored.git_commit[:12],
        status=stored.status.value,
        checkpoint=stored.primary_checkpoint.checkpoint_id if stored.primary_checkpoint else None,
    )
    return stored


def get_version(ctx: ProjectContext, ref: str) -> DevelopmentVersion:
    repo = VersionRepository(ctx.db)
    project = _project_id(ctx)
    version = repo.resolve(project, ref)
    if version is None:
        raise VersionNotFoundError(
            f"No version matches {ref!r}.",
            hint="Run `devmemory history` to list versions.",
        )
    return version


def list_versions(
    ctx: ProjectContext, *, limit: int = 100, offset: int = 0, ascending: bool = True
) -> list[DevelopmentVersion]:
    return VersionRepository(ctx.db).page(
        _project_id(ctx), limit=limit, offset=offset, ascending=ascending
    )


def version_diff(ctx: ProjectContext, from_ref: str, to_ref: str) -> VersionDiff:
    a = get_version(ctx, from_ref)
    b = get_version(ctx, to_ref)

    files = ctx.git.changed_files(a.git_commit, b.git_commit)
    diff_text = ctx.git.diff_text(a.git_commit, b.git_commit)

    metrics_a = {m.name: m for m in a.metrics}
    metrics_b = {m.name: m for m in b.metrics}
    metric_changes: dict[str, dict[str, float | None]] = {}
    for name in sorted(set(metrics_a) | set(metrics_b)):
        before = metrics_a[name].after if name in metrics_a else None
        after = metrics_b[name].after if name in metrics_b else None
        metric_changes[name] = {
            "before": before,
            "after": after,
            "delta": (after - before) if before is not None and after is not None else None,
        }

    return VersionDiff(
        from_version_id=a.version_id,
        to_version_id=b.version_id,
        from_commit=a.git_commit,
        to_commit=b.git_commit,
        files=files,
        stat=DiffStat.from_files(files),
        diff_text=diff_text,
        metric_changes=metric_changes,
        test_changes={
            "passed": _delta(
                a.tests.passed if a.tests else None, b.tests.passed if b.tests else None
            ),
            "failed": _delta(
                a.tests.failed if a.tests else None, b.tests.failed if b.tests else None
            ),
        },
        status_from=a.status,
        status_to=b.status,
    )


def search_versions(
    ctx: ProjectContext, query: str, *, limit: int = 50
) -> list[DevelopmentVersion]:
    repo = VersionRepository(ctx.db)
    project = _project_id(ctx)
    ids = repo.search_ids(project, query, limit=limit)
    return [v for vid in ids if (v := repo.get(vid)) is not None]


# --- helpers -----------------------------------------------------------------------


def _resolve_feature(ctx: ProjectContext, event: DevelopmentEvent) -> str | None:
    if not event.feature:
        return None
    feature = FeatureRepository(ctx.db).upsert(
        event.project_id,
        event.feature,
        status=FeatureStatus.IN_PROGRESS,
        derived_from=event.feature_derived_from,
    )
    return feature.feature_id


def _record_event(
    ctx: ProjectContext,
    *,
    version_id: str | None,
    event_type: str,
    payload: dict[str, object],
) -> None:
    with ctx.db.transaction() as conn:
        conn.execute(
            "INSERT INTO events (event_id, project_id, version_id, type, source, payload_json, "
            "created_at) VALUES (?, ?, ?, ?, 'devmemory', ?, ?)",
            (
                uuid.uuid4().hex,
                _project_id(ctx),
                version_id,
                event_type,
                json.dumps(payload),
                datetime.now(UTC).isoformat(),
            ),
        )


def _project_id(ctx: ProjectContext) -> str:
    return ctx.config.project_id


def _delta(a: int | None, b: int | None) -> int | None:
    if a is None or b is None:
        return None
    return b - a


__all__ = [
    "VersionDiff",
    "VersionExistsError",
    "VersionNotFoundError",
    "create_version_from_event",
    "get_version",
    "list_versions",
    "search_versions",
    "version_diff",
]
