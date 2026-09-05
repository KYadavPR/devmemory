"""REST API router for DevMemory web dashboard."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from devmemory import DevMemoryProject


def _get_proj(project_path: str = ".") -> DevMemoryProject:
    return DevMemoryProject(project_path)


def create_api_router(project_path: str = ".") -> APIRouter:
    api = APIRouter(prefix="/api")

    @api.get("/project")
    def get_project_summary():
        proj = _get_proj(project_path)
        return proj.status()

    @api.get("/versions")
    def get_versions(limit: int = Query(100, ge=1, le=500)):
        proj = _get_proj(project_path)
        return proj.history(limit=limit)

    # CRITICAL: /versions/compare MUST come BEFORE /versions/{version_id}
    # so FastAPI does not match 'compare' as an integer version_id!
    @api.get("/versions/compare")
    @api.get("/compare")
    def compare_versions(a: str = Query(...), b: str = Query(...)):
        proj = _get_proj(project_path)
        try:
            val_a = int(str(a).lower().lstrip("v"))
            val_b = int(str(b).lower().lstrip("v"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid version IDs provided. Expected integers, e.g. 2, 3 or v2, v3")

        res = proj.diff(val_a, val_b)
        if "error" in res:
            raise HTTPException(status_code=400, detail=res["error"])
        return res

    @api.get("/versions/{version_id}")
    def get_version_detail(version_id: int):
        proj = _get_proj(project_path)
        v = proj.db.get_version(version_id)
        if not v:
            raise HTTPException(status_code=404, detail="Version not found")
        hist = proj.history(limit=500)
        found = next((item for item in hist if item["version_id"] == version_id), dict(v))
        return found

    @api.get("/features")
    def get_features():
        proj = _get_proj(project_path)
        return proj.features()

    @api.get("/search")
    def search(q: str = Query(..., min_length=1)):
        proj = _get_proj(project_path)
        return proj.search(q)

    @api.get("/warnings")
    def get_warnings(feature: Optional[str] = "", intent: Optional[str] = ""):
        proj = _get_proj(project_path)
        return proj.context(feature=feature or "", intent=intent or "")

    @api.post("/versions/{version_id}/restore")
    def restore_version(version_id: int):
        proj = _get_proj(project_path)
        res = proj.restore(version_id)
        if "error" in res:
            raise HTTPException(status_code=400, detail=res["error"])
        return res

    @api.get("/analytics")
    def get_analytics():
        proj = _get_proj(project_path)
        return proj.analytics()

    return api
