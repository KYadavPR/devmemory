"""FastAPI application serving the dashboard and its JSON API.

Thin transport over :mod:`devmemory.services`. A per-request
:class:`~devmemory.services.context.ProjectContext` owns its own SQLite
connection so the threadpool-executed handlers never share one.
"""

from devmemory.api.app import create_app

__all__ = ["create_app"]
