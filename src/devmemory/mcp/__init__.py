"""DevMemory's Model Context Protocol server.

``build_server`` returns a configured :class:`fastmcp.FastMCP` exposing the same
development memory the dashboard shows - so an AI coding agent can ask "what
happened here before?" before it makes a change. Requires the ``mcp`` extra.
"""

from __future__ import annotations

from devmemory.mcp.server import build_server

__all__ = ["build_server"]
