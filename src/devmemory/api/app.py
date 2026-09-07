"""FastAPI app: the dashboard's JSON API plus the static single-page frontend.

Note: this module deliberately does *not* use ``from __future__ import
annotations`` - FastAPI needs the dependency ``Annotated[...]`` aliases to be real
objects at decoration time, and the local ``Ctx`` alias would not resolve as a
string.
"""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from devmemory.__about__ import __version__
from devmemory.adapters.ask_rules import RulesAskAdapter
from devmemory.adapters.genie import GenieAdapter, GenieAnswer, GenieUnavailableError
from devmemory.adapters.graph import GraphImpact
from devmemory.adapters.local_ask import LocalAskAdapter
from devmemory.api import mappers
from devmemory.api.schemas import (
    AgentCheckRequest,
    ComparisonResponse,
    FeatureDetail,
    GenieAskRequest,
    GenieStatus,
    IssueRequest,
    ProjectBriefDoc,
    ProjectBriefRequest,
    ProjectSummary,
    RequirementUpdateRequest,
    SearchResponse,
    SnapshotSummary,
    TaskCreateRequest,
    TaskSummary,
    VersionListItem,
)
from devmemory.domain.enums import RequirementStatus
from devmemory.domain.errors import DevMemoryError
from devmemory.domain.models import (
    Analysis,
    CheckpointReference,
    DevelopmentVersion,
    EntireStatus,
)
from devmemory.domain.taskloop import NormalizedState
from devmemory.services import brief as briefsvc
from devmemory.services import taskloop
from devmemory.services.agent_context import (
    ChangeGuidance,
    ProjectBrief,
    VersionBrief,
    change_guidance,
    project_brief,
    recent_history,
)
from devmemory.services.analysis import analyze_version
from devmemory.services.analytics import AnalyticsSummary, analytics_summary
from devmemory.services.context import ProjectContext
from devmemory.services.features import get_feature, list_features
from devmemory.services.impact import version_impact
from devmemory.services.memory import MemoryQuery, PreviousAttempt, previous_attempts
from devmemory.services.projects import project_status
from devmemory.services.restore import (
    RestorePreview,
    RestoreResult,
    restore_preview,
    restore_version,
)
from devmemory.services.trace import DevelopmentTrace, development_trace
from devmemory.services.versions import (
    get_version,
    list_versions,
    search_versions,
    version_diff,
)

# The dashboard is a Vite/React app. Its source lives in src/devmemory/web/frontend/
# and the built bundle is committed to src/devmemory/web/static/ (the wheel ships
# it, so `devmemory serve` needs no Node). Run `npm run build` there to refresh it.
_FRONTEND_DIR = Path(__file__).parents[1] / "web" / "static"
_PROBE_TTL = 20.0


class _ProbeCache:
    """The Entire probe shells out; cache it briefly so the dashboard stays snappy."""

    def __init__(self) -> None:
        self._at = 0.0
        self._value: EntireStatus | None = None

    def get(self, ctx: ProjectContext) -> EntireStatus:
        now = time.monotonic()
        if self._value is None or now - self._at > _PROBE_TTL:
            self._value = ctx.entire.probe()
            self._at = now
        return self._value


def create_app(repo_path: Path | str | None = None, *, enable_restore: bool = False) -> FastAPI:
    resolved = Path(repo_path) if repo_path else None
    holder: dict[str, ProjectContext] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        holder["ctx"] = ProjectContext.load(resolved, thread_safe=True)
        try:
            yield
        finally:
            holder.pop("ctx").close()

    app = FastAPI(
        title="DevMemory",
        version=__version__,
        summary="Development-memory and version-intelligence dashboard API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.state.enable_restore = enable_restore
    probe_cache = _ProbeCache()

    def get_ctx() -> ProjectContext:
        # One shared, thread-safe context for the life of the server.
        if "ctx" not in holder:  # pragma: no cover - only outside the lifespan
            holder["ctx"] = ProjectContext.load(resolved, thread_safe=True)
        return holder["ctx"]

    Ctx = Annotated[ProjectContext, Depends(get_ctx)]  # noqa: N806 - a type alias

    @app.exception_handler(DevMemoryError)
    async def _domain_error(_request: object, exc: DevMemoryError) -> PlainTextResponse:
        code = 404 if exc.exit_code in (3, 9) else 400
        return PlainTextResponse(exc.message, status_code=code)

    # -- project / status ------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/project", response_model=ProjectSummary)
    @app.get("/api/status", response_model=ProjectSummary)
    def project(ctx: Ctx) -> ProjectSummary:
        return mappers.project_summary(project_status(ctx, entire_probe=probe_cache.get(ctx)))

    @app.get("/api/project/brief", response_model=ProjectBriefDoc)
    def get_project_brief(ctx: Ctx) -> ProjectBriefDoc:
        doc = briefsvc.get_brief(ctx)
        return ProjectBriefDoc(content=doc.content, updated_at=doc.updated_at)

    @app.put("/api/project/brief", response_model=ProjectBriefDoc)
    def put_project_brief(ctx: Ctx, body: ProjectBriefRequest) -> ProjectBriefDoc:
        doc = briefsvc.set_brief(ctx, body.content)
        return ProjectBriefDoc(content=doc.content, updated_at=doc.updated_at)

    # -- Ask chat (Databricks Genie, or a local LLM fallback) --------

    @app.get("/api/genie/status", response_model=GenieStatus)
    def genie_status(ctx: Ctx) -> GenieStatus:
        g = GenieAdapter(ctx.config)
        if g.is_configured:
            return GenieStatus(
                configured=True,
                mode="genie",
                engine="Databricks Genie",
                space_id=g.space_id or None,
            )
        local = LocalAskAdapter(ctx)
        if local.is_available:
            return GenieStatus(configured=True, mode="local", engine=local.engine_label)
        # The built-in rules engine always works - no key, no Databricks.
        return GenieStatus(
            configured=True,
            mode="rules",
            engine=RulesAskAdapter(ctx).engine_label,
            reason=(
                "Answering common questions from your local history. Add an LLM API "
                "key (OPENROUTER_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY / "
                "OPENAI_API_KEY) or a Genie space for open-ended questions."
            ),
        )

    @app.post("/api/genie/ask", response_model=GenieAnswer)
    def genie_ask(ctx: Ctx, body: GenieAskRequest) -> GenieAnswer:
        question = body.question.strip()
        if not question:
            raise HTTPException(status_code=422, detail="question is empty")
        g = GenieAdapter(ctx.config)
        if g.is_configured:
            try:
                return g.ask(question, conversation_id=body.conversation_id)
            except GenieUnavailableError as exc:
                raise HTTPException(status_code=502, detail=exc.message) from exc
        local = LocalAskAdapter(ctx)
        if local.is_available:
            try:
                return local.ask(question, conversation_id=body.conversation_id)
            except DevMemoryError as exc:  # pragma: no cover - defensive
                raise HTTPException(status_code=502, detail=exc.message) from exc
        return RulesAskAdapter(ctx).ask(question, conversation_id=body.conversation_id)

    # -- versions ------------------------------------------------------

    @app.get("/api/versions", response_model=list[VersionListItem])
    def versions(
        ctx: Ctx,
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[VersionListItem]:
        items = list_versions(ctx, limit=limit, offset=offset, ascending=True)
        return [mappers.version_list_item(v) for v in items]

    @app.get("/api/versions/{ref}", response_model=DevelopmentVersion)
    def version(ctx: Ctx, ref: str) -> DevelopmentVersion:
        return get_version(ctx, ref)

    @app.get("/api/versions/{ref}/diff", response_class=PlainTextResponse)
    def version_diff_text(ctx: Ctx, ref: str) -> str:
        v = get_version(ctx, ref)
        return ctx.git.diff_text(v.parent_commit, v.git_commit)

    @app.get("/api/versions/{ref}/checkpoint", response_model=CheckpointReference)
    def version_checkpoint(ctx: Ctx, ref: str) -> CheckpointReference:
        v = get_version(ctx, ref)
        if v.primary_checkpoint is None:
            raise HTTPException(status_code=404, detail="no checkpoint linked to this version")
        return v.primary_checkpoint

    @app.get("/api/versions/{ref}/trace", response_model=DevelopmentTrace)
    def version_trace(ctx: Ctx, ref: str) -> DevelopmentTrace:
        return development_trace(ctx, ref)

    @app.post("/api/versions/{ref}/analysis", response_model=Analysis)
    def regenerate_analysis(ctx: Ctx, ref: str) -> Analysis:
        """Re-run the analysis provider chain for a version (interpretation only)."""
        return analyze_version(ctx, ref)

    @app.get("/api/versions/{ref}/impact", response_model=GraphImpact)
    def version_impact_endpoint(ctx: Ctx, ref: str) -> GraphImpact:
        impact = version_impact(ctx, ref, compute_if_missing=ctx.config.graph.enabled)
        if impact is None:
            raise HTTPException(
                status_code=404,
                detail="no change-impact analysis for this version "
                "(install the Entire `graph` plugin)",
            )
        return impact

    # -- comparison --------------------------------------------------

    @app.get("/api/compare", response_model=ComparisonResponse)
    def compare(
        ctx: Ctx,
        from_: Annotated[str, Query(alias="from")],
        to: Annotated[str, Query(alias="to")],
    ) -> ComparisonResponse:
        return mappers.comparison_response(version_diff(ctx, from_, to))

    # -- features ---------------------------------------------------

    @app.get("/api/features", response_model=list[FeatureDetail])
    def features(ctx: Ctx) -> list[FeatureDetail]:
        return [mappers.feature_detail(f) for f in list_features(ctx)]

    @app.get("/api/features/{ref}", response_model=FeatureDetail)
    def feature(ctx: Ctx, ref: str) -> FeatureDetail:
        return mappers.feature_detail(get_feature(ctx, ref))

    # -- analytics ---------------------------------------------

    @app.get("/api/analytics", response_model=AnalyticsSummary)
    def analytics(ctx: Ctx) -> AnalyticsSummary:
        return analytics_summary(ctx)

    # -- agent context (the REST half of the MCP surface) ------

    @app.get("/api/agent/context", response_model=ProjectBrief)
    def agent_context(ctx: Ctx) -> ProjectBrief:
        return project_brief(ctx)

    @app.get("/api/agent/history", response_model=list[VersionBrief])
    def agent_history(
        ctx: Ctx,
        limit: Annotated[int, Query(ge=1, le=200)] = 20,
        feature: Annotated[str | None, Query()] = None,
    ) -> list[VersionBrief]:
        return recent_history(ctx, limit=limit, feature=feature)

    @app.post("/api/agent/check", response_model=ChangeGuidance)
    def agent_check(ctx: Ctx, body: AgentCheckRequest) -> ChangeGuidance:
        return change_guidance(
            ctx,
            files=body.files,
            intent=body.intent,
            feature=body.feature,
            symbols=body.symbols,
        )

    # -- the state-aware coding loop -----------------------------------

    @app.get("/api/tasks", response_model=list[TaskSummary])
    def tasks(ctx: Ctx) -> list[TaskSummary]:
        return [mappers.task_summary(t) for t in taskloop.list_tasks(ctx)]

    @app.post("/api/tasks", response_model=NormalizedState, status_code=201)
    def create_task(ctx: Ctx, body: TaskCreateRequest) -> NormalizedState:
        task = taskloop.create_task(ctx, goal=body.goal, test_command=body.test_command)
        return taskloop.get_state(ctx, task.id)

    @app.get("/api/tasks/{task_id}/state", response_model=NormalizedState)
    def task_state(ctx: Ctx, task_id: str) -> NormalizedState:
        return taskloop.get_state(ctx, task_id)

    @app.post("/api/tasks/{task_id}/refresh", response_model=NormalizedState)
    def task_refresh(ctx: Ctx, task_id: str) -> NormalizedState:
        return taskloop.refresh_state(ctx, task_id)

    @app.post("/api/tasks/{task_id}/complete", response_model=NormalizedState)
    def task_complete(ctx: Ctx, task_id: str) -> NormalizedState:
        return taskloop.mark_complete(ctx, task_id)

    @app.get("/api/tasks/{task_id}/snapshots", response_model=list[SnapshotSummary])
    def task_snapshots(
        ctx: Ctx,
        task_id: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 40,
    ) -> list[SnapshotSummary]:
        return [
            mappers.snapshot_summary(s) for s in taskloop.list_snapshots(ctx, task_id, limit=limit)
        ]

    @app.post("/api/tasks/{task_id}/issues", response_model=NormalizedState)
    def task_issue(ctx: Ctx, task_id: str, body: IssueRequest) -> NormalizedState:
        taskloop.report_issue(
            ctx, task_id=task_id, description=body.description, blocking=body.blocking
        )
        return taskloop.refresh_state(ctx, task_id)

    @app.post("/api/tasks/{task_id}/issues/{issue_id}/resolve", response_model=NormalizedState)
    def task_issue_resolve(ctx: Ctx, task_id: str, issue_id: int) -> NormalizedState:
        taskloop.resolve_issue(ctx, issue_id=issue_id)
        return taskloop.refresh_state(ctx, task_id)

    @app.post("/api/tasks/{task_id}/requirements/{req_id}", response_model=NormalizedState)
    def task_set_requirement(
        ctx: Ctx, task_id: str, req_id: str, body: RequirementUpdateRequest
    ) -> NormalizedState:
        try:
            status = RequirementStatus(body.status.upper())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"invalid status {body.status!r}") from exc
        return taskloop.set_requirement_status(
            ctx, task_id=task_id, requirement_id=req_id, status=status, note=body.note
        )

    # -- restore ------------------------------------------------

    @app.get("/api/versions/{ref}/restore/preview", response_model=RestorePreview)
    def restore_preview_endpoint(ctx: Ctx, ref: str) -> RestorePreview:
        return restore_preview(ctx, ref)

    @app.post("/api/versions/{ref}/restore", response_model=RestoreResult)
    def restore_endpoint(
        ctx: Ctx,
        ref: str,
        mode: Annotated[str, Query(pattern="^(detach|hard)$")] = "detach",
        allow_dirty: Annotated[bool, Query()] = False,
    ) -> RestoreResult:
        if not app.state.enable_restore:
            raise HTTPException(
                status_code=403,
                detail="restore is disabled; start the server with `devmemory serve --enable-restore`",
            )
        return restore_version(ctx, ref, mode=mode, allow_dirty=allow_dirty)

    # -- development memory --------------------------------------

    @app.get("/api/attempts", response_model=list[PreviousAttempt])
    def attempts(
        ctx: Ctx,
        feature: Annotated[str | None, Query()] = None,
        q: Annotated[str | None, Query()] = None,
        file: Annotated[list[str] | None, Query()] = None,
        include_successes: Annotated[bool, Query()] = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 25,
    ) -> list[PreviousAttempt]:
        return previous_attempts(
            ctx,
            MemoryQuery(
                files=file or [],
                feature=feature,
                intent=q,
                include_successes=include_successes,
                limit=limit,
            ),
        )

    @app.get("/api/versions/{ref}/attempts", response_model=list[PreviousAttempt])
    def version_attempts(ctx: Ctx, ref: str) -> list[PreviousAttempt]:
        v = get_version(ctx, ref)
        found = previous_attempts(
            ctx,
            MemoryQuery(
                files=[f.path for f in v.changed_files],
                feature=v.feature_id.split(":", 1)[-1] if v.feature_id else None,
                intent=v.intent,
                limit=6,
            ),
        )
        return [a for a in found if a.version_id != v.version_id]

    # -- search ---------------------------------------------------

    @app.get("/api/search", response_model=SearchResponse)
    def search(
        ctx: Ctx,
        q: Annotated[str, Query(min_length=1)],
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> SearchResponse:
        hits = [mappers.search_hit(v) for v in search_versions(ctx, q, limit=limit)]
        return SearchResponse(query=q, count=len(hits), results=hits)

    # -- frontend (hash-routed SPA, no build step) ----------------

    if (_FRONTEND_DIR / "index.html").is_file():
        app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            # Never let a browser hold a stale index.html: it points at
            # content-hashed asset filenames that change on every rebuild, so a
            # cached copy boots old JS against the current API. The hashed
            # /static/assets/* are immutable and cache freely.
            return FileResponse(
                _FRONTEND_DIR / "index.html",
                headers={"Cache-Control": "no-cache, must-revalidate"},
            )

    return app


__all__ = ["create_app"]
