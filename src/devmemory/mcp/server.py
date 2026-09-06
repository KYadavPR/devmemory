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

from devmemory.adapters.graph import GraphImpact
from devmemory.domain.enums import RequirementStatus
from devmemory.domain.taskloop import Issue, NormalizedState
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
from devmemory.services.taskloop import engine as taskloop
from devmemory.services.trace import DevelopmentTrace, development_trace

if TYPE_CHECKING:
    from fastmcp import FastMCP

_INSTRUCTIONS = """\
DevMemory records every AI-assisted change as a Development Version: the Git diff,
the Entire checkpoint (intent + agent + model), the test and metric results, and
whether it regressed anything.

State-aware coding loop: call get_state(task_id) before starting or resuming
work, do the implementation with your own tools, commit, then refresh_state to
re-collect evidence and get the new status (IN_PROGRESS / NEEDS_WORK / READY /
BLOCKED). Continue while NEEDS_WORK; stop at READY; escalate at BLOCKED.

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
        symbols: list[str] | None = None,
    ) -> ChangeGuidance:
        """Pre-flight check: given the files you are about to edit (and optionally
        your intent / the feature / the specific functions or types you will
        change), returns a verdict - proceed | caution | high-risk - with the
        prior failures to read first AND the live code-graph blast radius for each
        named symbol (direct + transitive callers, type consumers, co-changing
        files). Pass ``symbols`` as names or ``path/to/file.py:line``. Call this
        before editing."""
        return change_guidance(
            ctx(),
            files=files or [],
            intent=intent or None,
            feature=feature,
            symbols=symbols or [],
        )

    @mcp.tool
    def search_versions(query: str, limit: int = 10) -> list[VersionBrief]:
        """Full-text search over version intents, features, and changed files."""
        from devmemory.services.versions import search_versions as _search

        return [version_brief(v) for v in _search(ctx(), query, limit=limit)]

    @mcp.tool
    def get_change_impact(ref: str) -> GraphImpact | None:
        """The entity-level blast radius for a version (Entire `graph` plugin):
        added / removed / renamed / signature-changed / body-changed symbols with
        dependent counts. ``None`` if the plugin is not installed."""
        from devmemory.services.impact import version_impact

        return version_impact(ctx(), ref)

    @mcp.tool
    def graph_search(query: str, top_k: int = 5) -> list[dict[str, object]]:
        """Find the code for a task from a plain-language description, via the
        Entire `graph` plugin: ranked source regions with file:line, symbol name,
        and signature. Empty list if the plugin is not installed. Use this to
        locate the right edit site before changing code."""
        return [h.model_dump() for h in ctx().graph.search(query, top_k=top_k)]

    @mcp.tool
    def symbol_blast_radius(symbol: str) -> dict[str, object] | None:
        """Everything downstream of one symbol (Entire `graph` plugin): direct +
        transitive callers, callees, type consumers, co-changing files. ``symbol``
        is a name or ``path/to/file.py:line``. Run before changing a function or
        type's behaviour. ``None`` if the plugin is not installed."""
        si = ctx().graph.symbol_impact(symbol)
        return si.model_dump() if si is not None else None

    @mcp.tool
    def get_analytics() -> AnalyticsSummary:
        """Development intelligence across all versions: regression leaderboard,
        feature attempts, file churn, agent effectiveness, trend, and
        repeatedly-failed approaches."""
        return analytics_summary(ctx())

    # -- the state-aware coding loop -------------------------------------

    @mcp.tool
    def create_task(goal: str, test_command: str | None = None) -> NormalizedState:
        """Start a task: normalize ``goal`` into explicit requirements, pin the
        base commit, and return the first state. Call this once per human task,
        then drive the loop with get_state / refresh_state."""
        task = taskloop.create_task(ctx(), goal=goal, test_command=test_command)
        return taskloop.get_state(ctx(), task.id)

    @mcp.tool
    def get_state(task_id: str) -> NormalizedState:
        """The current normalized project state for a task: requirements, git,
        checkpoint, tests, impact, unresolved items, recommended focus, and the
        overall status. Read this before starting or resuming work. It orients
        you - still inspect the real repository with your own tools."""
        return taskloop.get_state(ctx(), task_id)

    @mcp.tool
    def refresh_state(task_id: str) -> NormalizedState:
        """Re-collect all evidence (git, Entire, tests, optional graph),
        re-evaluate requirements, recompute the overall status, store a snapshot,
        and return the complete new state. Call this after you commit meaningful
        progress."""
        return taskloop.refresh_state(ctx(), task_id)

    @mcp.tool
    def get_checkpoint(checkpoint_id: str) -> dict[str, object]:
        """Compact metadata for one Entire checkpoint: intent, agent, model,
        associated commit, sessions, token total. Not a full transcript."""
        return taskloop.get_checkpoint(ctx(), checkpoint_id)

    @mcp.tool
    def report_issue(task_id: str, description: str, blocking: bool = False) -> Issue:
        """Record an unresolved item for a task. Set ``blocking=True`` when you
        cannot safely continue without a human decision - that forces the task to
        BLOCKED on the next refresh."""
        return taskloop.report_issue(
            ctx(), task_id=task_id, description=description, blocking=blocking
        )

    @mcp.tool
    def set_requirement_status(
        task_id: str, requirement_id: str, status: str, note: str = ""
    ) -> NormalizedState:
        """Record your own verdict for one requirement (status: COMPLETE |
        PARTIAL | INCOMPLETE | UNKNOWN) after you have implemented and verified
        it. The engine still independently checks tests + tree state before it
        will report READY. Returns the refreshed state."""
        return taskloop.set_requirement_status(
            ctx(),
            task_id=task_id,
            requirement_id=requirement_id,
            status=RequirementStatus(status.upper()),
            note=note,
        )

    @mcp.tool
    def mark_complete(task_id: str) -> NormalizedState:
        """Request a completion evaluation. This runs a full refresh and returns
        the state - it never blindly marks READY. You are done only if the
        returned overall_status is READY."""
        return taskloop.mark_complete(ctx(), task_id)

    return mcp


__all__ = ["build_server"]
