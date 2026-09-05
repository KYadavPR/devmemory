"""FastAPI Application factory for DevMemory Web Dashboard."""

import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from devmemory.web.api import create_api_router


def create_app(project_path: str = ".") -> FastAPI:
    """Create and configure the FastAPI web app for DevMemory."""
    app = FastAPI(
        title="DevMemory Dashboard",
        description="Development-Memory & Version-Intelligence Platform",
        version="0.1.0",
    )

    # API routes
    api_router = create_api_router(project_path)
    app.include_router(api_router)

    # Static assets
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def index():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "DevMemory dashboard static files initializing..."}

    return app
