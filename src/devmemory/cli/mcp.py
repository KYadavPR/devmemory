"""``devmemory mcp`` - run the Model Context Protocol server over stdio."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from devmemory.cli._render import err_console
from devmemory.domain.errors import DevMemoryError
from devmemory.services.context import ProjectContext


def mcp_command(
    repo: Annotated[
        Path | None,
        typer.Option("--repo", help="Repository to serve (default: discover from the cwd)."),
    ] = None,
    print_config: Annotated[
        bool,
        typer.Option(
            "--print-config",
            help="Print an .mcp.json fragment for this repo and exit (no server).",
        ),
    ] = False,
) -> None:
    """Expose this project's development memory to an AI agent over MCP (stdio).

    Wire it into an MCP client (Claude Code, Cursor, ...) with the fragment from
    `devmemory mcp --print-config`. The server is read-only.
    """
    with ProjectContext.load(repo) as ctx:
        root = ctx.paths.repo_root

    if print_config:
        fragment = {
            "mcpServers": {
                "devmemory": {
                    "command": "devmemory",
                    "args": ["mcp", "--repo", str(root)],
                }
            }
        }
        # plain stdout, not Rich - this is meant to be copy-pasted into a JSON file
        sys.stdout.write(json.dumps(fragment, indent=2) + "\n")
        return

    try:
        import fastmcp  # noqa: F401
    except ImportError as exc:  # pragma: no cover - extra not installed
        raise DevMemoryError(
            "the 'mcp' extra is not installed",
            hint="pip install 'devmemory[mcp]'",
        ) from exc

    from devmemory.mcp.server import build_server

    # stdio transport owns stdout; keep our chatter on stderr.
    err_console.print(f"[dim]devmemory mcp: serving {root} over stdio[/dim]")
    build_server(root).run(transport="stdio", show_banner=False)


__all__ = ["mcp_command"]
