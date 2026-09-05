"""Service layer - the single waist between adapters/storage and the CLI/API/MCP.

Nothing above this layer imports ``sqlite3`` or an adapter directly; nothing in
this layer imports FastAPI or Typer.
"""

from devmemory.services.context import ProjectContext

__all__ = ["ProjectContext"]
