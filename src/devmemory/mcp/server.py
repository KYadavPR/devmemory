"""The DevMemory MCP server.

Read-only. Every tool returns collected facts (Git, Entire, tests, metrics) or a
rule-based risk read over them - never an LLM interpretation. The server holds
one thread-safe :class:`ProjectContext` for its lifetime.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from devmemory.services.agent_context import (
    ChangeGuidance,
    ProjectBrief,
    VersionBrief,
    VersionReport,
    change_guidance,
    project_brief,
    recent_history,
    version_brief,
    version_report,
)
from devmemory.services.analytics import AnalyticsSummary, analytics_summary
from devmemory.services.context import ProjectContext
from devmemory.services.memory import MemoryQuery, PreviousAttempt, previous_attempts
from devmemory.services.trace import DevelopmentTrace, development_trace

if TYPE_CHECKING:
    from fastmcp import FastMCP

_INSTRUCTIONS = """\
DevMemory records every AI-assisted change as a Development Version: the Git diff,
the Entire checkpoint (intent + agent + model), the test and metric results, and
whether it regressed anything.

Call check_before_change BEFORE editing files - it reports whether this area has
failed here before. Use get_project_context for orientation, get_version_history
and get_previous_attempts to look back, and get_development_trace to see how one
version's intent led to its result.
"""


def build_server(repo_path: Path | str | None = None) -> FastMCP:
    from fastmcp import FastMCP

    resolved = Path(repo_path) if repo_path is not None else None
    holder: dict[str, ProjectContext] = {}

    def ctx() -> ProjectContext:
        if "ctx" not in holder:
            holder["ctx"] = ProjectContext.load(resolved, thread_safe=True)
        return holder["ctx"]

    @asynccontextmanager
    async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
        try:
            yield
        finally:
            existing = holder.pop("ctx", None)
            if existing is not None:
                existing.close()

    mcp: FastMCP = FastMCP("devmemory", instructions=_INSTRUCTIONS, lifespan=lifespan)

    @mcp.tool
    def get_project_context() -> ProjectBrief:
        """Orientation for this repo: branch/HEAD, whether HEAD is checkpointed,
        version count and success rate, open features, the latest version, recent
        adverse versions, and things to be careful about."""
        return project_brief(ctx())

    @mcp.tool
    def get_version_history(limit: int = 20, feature: str | None = None) -> list[VersionBrief]:
        """Recent development versions, newest first. Optionally filter by feature."""
        return recent_history(ctx(), limit=limit, feature=feature)

    @mcp.tool
    def get_version(ref: str) -> VersionReport:
        """One version in full: the flattened brief, its intent->result trace, and
        its parent commit. ``ref`` accepts ``v7``, ``7``, or a commit prefix."""
        return version_report(ctx(), ref)

    @mcp.tool
    def get_development_trace(ref: str) -> DevelopmentTrace:
        """The ordered chain for one version: intent -> agent -> checkpoint ->
        commit -> files -> tests -> metrics -> status -> analysis."""
        return development_trace(ctx(), ref)

    @mcp.tool
    def get_previous_attempts(
        files: list[str] | None = None,
        intent: str | None = None,
        feature: str | None = None,
        include_successes: bool = False,
        limit: int = 10,
    ) -> list[PreviousAttempt]:
        """Past versions that touched the same files / feature / intent, ranked by
        relevance. Adverse attempts only unless ``include_successes`` is set. Each
        result explains why it matched and what to do about it."""
        return previous_attempts(
            ctx(),
            MemoryQuery(
                files=files or [],
                intent=intent,
                feature=feature,
                include_successes=include_successes,
                limit=limit,
            ),
        )

    @mcp.tool
    def check_before_change(
        files: list[str] | None = None,
        intent: str = "",
        feature: str | None = None,
    ) -> ChangeGuidance:
        """Pre-flight check: given the files you are about to edit (and optionally
        your intent / the feature), returns a verdict - proceed | caution |
        high-risk - with the specific prior failures to read first. Call this
        before editing."""
        return change_guidance(ctx(), files=files or [], intent=intent or None, feature=feature)

    @mcp.tool
    def search_versions(query: str, limit: int = 10) -> list[VersionBrief]:
        """Full-text search over version intents, features, and changed files."""
        from devmemory.services.versions import search_versions as _search

        return [version_brief(v) for v in _search(ctx(), query, limit=limit)]

    @mcp.tool
    def get_analytics() -> AnalyticsSummary:
        """Development intelligence across all versions: regression leaderboard,
        feature attempts, file churn, agent effectiveness, trend, and
        repeatedly-failed approaches."""
        return analytics_summary(ctx())

    return mcp


__all__ = ["build_server"]
