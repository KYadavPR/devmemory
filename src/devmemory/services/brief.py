"""The project brief - a single, human-owned source of truth.

The brief is one markdown document: what the project is for, its constraints,
the decisions already made, the conventions to follow. It is fed into
requirement normalization (:mod:`devmemory.services.taskloop.requirements`) so
the loop's requirements and prompt suggestions stay anchored to the project
rather than to the wording of one task.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from devmemory.services.context import ProjectContext

_MAX_CHARS = 60_000


@dataclass(frozen=True)
class ProjectBrief:
    content: str
    updated_at: str | None


def get_brief(ctx: ProjectContext) -> ProjectBrief:
    row = ctx.db.query_one("SELECT content, updated_at FROM project_brief WHERE id = 1")
    if row is None:
        return ProjectBrief(content="", updated_at=None)
    return ProjectBrief(content=row["content"], updated_at=row["updated_at"])


def set_brief(ctx: ProjectContext, content: str) -> ProjectBrief:
    text = content.strip()[:_MAX_CHARS]
    now = datetime.now(UTC).isoformat()
    ctx.db.execute(
        "INSERT INTO project_brief (id, content, updated_at) VALUES (1, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET content = excluded.content, "
        "updated_at = excluded.updated_at",
        (text, now),
    )
    return ProjectBrief(content=text, updated_at=now)


def brief_context(ctx: ProjectContext, *, limit: int = 4000) -> str | None:
    """The brief trimmed for use as LLM context, or ``None`` when empty."""
    text = get_brief(ctx).content.strip()
    if not text:
        return None
    return text[:limit]


__all__ = ["ProjectBrief", "brief_context", "get_brief", "set_brief"]
