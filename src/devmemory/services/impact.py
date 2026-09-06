"""Change-impact for a version: stored result, or computed on demand.

Thin service over :class:`GraphAdapter` + :class:`GraphImpactRepository`. When a
version has no stored impact and the plugin is available, it is computed once and
cached.
"""

from __future__ import annotations

from devmemory.adapters.graph import GraphImpact, GraphStatus
from devmemory.services.context import ProjectContext
from devmemory.services.versions import get_version
from devmemory.storage.graph_impacts import GraphImpactRepository


def graph_status(ctx: ProjectContext) -> GraphStatus:
    status = ctx.graph.probe()
    return status.model_copy(update={"detail": status.detail or _enabled_note(ctx)})


def version_impact(
    ctx: ProjectContext, ref: str, *, compute_if_missing: bool = True
) -> GraphImpact | None:
    version = get_version(ctx, ref)
    repo = GraphImpactRepository(ctx.db)

    stored = repo.get(version.version_id)
    if stored is not None:
        return stored
    if not compute_if_missing or not ctx.graph.is_available:
        return None

    impact = ctx.graph.commit_impact(version.git_commit)
    if impact is None:
        return None
    computed = impact.model_copy(update={"version_id": version.version_id})
    repo.set(version.version_id, computed)
    return computed


def _enabled_note(ctx: ProjectContext) -> str | None:
    if not ctx.config.graph.enabled:
        return "graph.enabled is false; impact is computed on request only"
    return None


__all__ = ["graph_status", "version_impact"]
