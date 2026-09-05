"""``devmemory serve`` - the local dashboard + API."""

from __future__ import annotations

import contextlib
import socket
import webbrowser
from typing import Annotated

import typer

from devmemory.cli._render import console, success
from devmemory.services.context import ProjectContext


def serve_command(
    host: Annotated[str | None, typer.Option("--host", help="Bind address.")] = None,
    port: Annotated[int | None, typer.Option("--port", "-p", help="Preferred port.")] = None,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the dashboard in a browser.")
    ] = True,
    enable_restore: Annotated[
        bool,
        typer.Option("--enable-restore", help="Allow the restore endpoint (off by default)."),
    ] = False,
    reload: Annotated[bool, typer.Option("--reload", hidden=True)] = False,
) -> None:
    """Start the DevMemory web dashboard on localhost."""
    # Imported here so `fastapi`/`uvicorn` don't slow down every other command.
    import uvicorn

    from devmemory.api.app import create_app

    with ProjectContext.load() as ctx:
        repo_root = ctx.paths.repo_root
        bind_host = host or ctx.config.web.host
        want_port = port or ctx.config.web.port
        allow_restore = enable_restore or ctx.config.web.enable_restore

    chosen = _pick_port(bind_host, want_port)
    url = f"http://{bind_host}:{chosen}"

    app = create_app(repo_root, enable_restore=allow_restore)
    success(f"DevMemory dashboard → [bold]{url}[/bold]")
    console.print(f"[dim]API docs: {url}/api/docs   ·   Ctrl-C to stop[/dim]")
    if open_browser:
        with contextlib.suppress(Exception):
            webbrowser.open(url)

    uvicorn.run(app, host=bind_host, port=chosen, log_level="warning", reload=reload)


def _pick_port(host: str, preferred: int) -> int:
    for candidate in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, candidate))
            except OSError:
                continue
            return candidate
    return preferred


__all__ = ["serve_command"]
