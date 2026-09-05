"""Databricks sync: an offline outbox that a live push drains.

Every published version is written to ``.devmemory/outbox/<version>.json`` first.
If Databricks is configured and reachable, the pipeline pushes immediately and
removes the file; otherwise it stays queued for ``devmemory databricks push``.
Local history never depends on any of this.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from devmemory.adapters.databricks import (
    DatabricksAdapter,
    DatabricksUnavailableError,
    outbox_event,
)
from devmemory.domain.errors import DatabricksError
from devmemory.domain.models import DevelopmentVersion
from devmemory.logging import get_logger
from devmemory.services.context import ProjectContext

_log = get_logger(__name__)


class SyncResult(BaseModel):
    configured: bool
    pushed: list[str] = []
    queued: list[str] = []
    failed: list[str] = []
    detail: str | None = None


def enqueue(ctx: ProjectContext, version: DevelopmentVersion) -> Path:
    ctx.paths.outbox_dir.mkdir(parents=True, exist_ok=True)
    path = ctx.paths.outbox_dir / f"{version.version_id}.json"
    path.write_text(json.dumps(outbox_event(version), indent=2), encoding="utf-8")
    return path


def push_version(ctx: ProjectContext, version: DevelopmentVersion) -> SyncResult:
    """Queue a version and, if Databricks is reachable, publish it now."""
    enqueue(ctx, version)
    if not (ctx.config.databricks.enabled and DatabricksAdapter(ctx.config).is_configured):
        return SyncResult(configured=False, queued=[version.version_id])
    return drain(ctx, only=version.version_id)


def drain(ctx: ProjectContext, *, only: str | None = None) -> SyncResult:
    """Publish every queued event (or just ``only``) to Databricks."""
    adapter = DatabricksAdapter(ctx.config)
    if not adapter.is_configured:
        return SyncResult(
            configured=False,
            queued=[p.stem for p in _outbox_files(ctx)],
            detail="Databricks credentials are not set (DATABRICKS_HOST/TOKEN/WAREHOUSE_ID).",
        )

    result = SyncResult(configured=True)
    try:
        adapter.bootstrap()
    except DatabricksError as exc:
        return SyncResult(
            configured=True,
            queued=[p.stem for p in _outbox_files(ctx)],
            detail=f"could not reach Databricks: {exc.message}",
        )

    for path in _outbox_files(ctx):
        if only is not None and path.stem != only:
            continue
        try:
            version = _rehydrate(ctx, path.stem)
            if version is None:
                path.unlink(missing_ok=True)
                continue
            adapter.publish_version(version)
        except (DatabricksUnavailableError, DatabricksError) as exc:
            result.failed.append(path.stem)
            result.detail = exc.message
            _log.warning("databricks.push_failed", version=path.stem, error=exc.message)
            break
        else:
            path.unlink(missing_ok=True)
            result.pushed.append(path.stem)

    result.queued = [p.stem for p in _outbox_files(ctx)]
    if result.pushed:
        _log.info("databricks.drained", pushed=result.pushed, remaining=result.queued)
    return result


def sync_status(ctx: ProjectContext) -> SyncResult:
    adapter = DatabricksAdapter(ctx.config)
    return SyncResult(
        configured=adapter.is_configured and ctx.config.databricks.enabled,
        queued=[p.stem for p in _outbox_files(ctx)],
        detail=(
            f"catalog {ctx.config.databricks.catalog}.{ctx.config.databricks.schema_name}"
            if adapter.is_configured
            else "not configured"
        ),
    )


def _outbox_files(ctx: ProjectContext) -> list[Path]:
    if not ctx.paths.outbox_dir.is_dir():
        return []
    return sorted(ctx.paths.outbox_dir.glob("*.json"))


def _rehydrate(ctx: ProjectContext, version_id: str) -> DevelopmentVersion | None:
    from devmemory.storage.versions import VersionRepository

    return VersionRepository(ctx.db).get(version_id)


__all__ = ["SyncResult", "drain", "enqueue", "push_version", "sync_status"]
