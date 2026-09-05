"""FastAPI app: the dashboard's JSON API plus the static single-page frontend.

Note: this module deliberately does *not* use ``from __future__ import
annotations`` - FastAPI needs the dependency ``Annotated[...]`` aliases to be real
objects at decoration time, and the local ``Ctx`` alias would not resolve as a
string.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from devmemory.__about__ import __version__
from devmemory.api import mappers
from devmemory.api.schemas import (
    ComparisonResponse,
    FeatureDetail,
    ProjectSummary,
    SearchResponse,
    VersionListItem,
)
from devmemory.domain.errors import DevMemoryError
from devmemory.domain.models import CheckpointReference, DevelopmentVersion
from devmemory.services.context import ProjectContext
from devmemory.services.features import get_feature, list_features
from devmemory.services.projects import project_status
from devmemory.services.trace import DevelopmentTrace, development_trace
from devmemory.services.versions import (
    get_version,
    list_versions,
    search_versions,
    version_diff,
)

_FRONTEND_DIR = Path(__file__).parent / "static"


def _context_for(repo_path: Path | None) -> Iterator[ProjectContext]:
    ctx = ProjectContext.load(repo_path)
    try:
        yield ctx
    finally:
        ctx.close()


def create_app(repo_path: Path | str | None = None, *, enable_restore: bool = False) -> FastAPI:
    resolved = Path(repo_path) if repo_path else None

    app = FastAPI(
        title="DevMemory",
        version=__version__,
        summary="Development-memory and version-intelligence dashboard API",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.enable_restore = enable_restore

    def get_ctx() -> Iterator[ProjectContext]:
        yield from _context_for(resolved)

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
        return mappers.project_summary(project_status(ctx, entire_probe=ctx.entire.probe()))

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
            return FileResponse(_FRONTEND_DIR / "index.html")

    return app


__all__ = ["create_app"]
