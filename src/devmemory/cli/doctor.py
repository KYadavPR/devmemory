"""``devmemory doctor`` - check the environment and the project setup.

Reports credential *presence*, never values.
"""

from __future__ import annotations

import platform
import shutil
import sqlite3
import subprocess
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from devmemory.cli._render import console
from devmemory.config import DevMemoryConfig, resolve_databricks_credentials, resolve_llm_api_key
from devmemory.paths import find_project_paths
from devmemory.storage.db import Database, discover_migrations

_OK = "[green]ok[/green]"
_WARN = "[yellow]warn[/yellow]"
_MISS = "[dim]absent[/dim]"


def doctor_command(
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit non-zero if any check is not ok.")
    ] = False,
) -> None:
    """Diagnose the DevMemory environment: toolchain, project, storage, integrations."""
    rows: list[tuple[str, str, str]] = []

    # -- toolchain -----------------------------------------------------
    py = platform.python_version()
    rows.append(("python", _OK if _pyver_ok(py) else _WARN, f"{py} ({platform.system()})"))
    rows.append(_tool("git", "git", ["--version"]))

    from devmemory.adapters.graph import _find_binary as _find_graph

    entire = shutil.which("entire") or _fallback("entire")
    rows.append(
        ("entire cli", _OK if entire else _WARN, entire or "not found (checkpoints optional)")
    )
    graph = _find_graph()
    rows.append(
        ("entire graph", _OK if graph else _MISS, graph or "not installed (impact optional)")
    )

    # -- project -----------------------------------------------------
    paths = find_project_paths()
    if paths is None:
        rows.append(("project", _WARN, "no .devmemory/ here - run `devmemory init`"))
        _render(rows)
        raise typer.Exit(1 if strict else 0)

    rows.append(("project root", _OK, str(paths.repo_root)))
    try:
        config = DevMemoryConfig.load(paths)
        rows.append(("config", _OK, f"{config.project_name} ({config.project_id})"))
    except Exception as exc:
        rows.append(("config", _WARN, str(exc)))
        config = None

    # -- storage ---------------------------------------------------
    try:
        db = Database(paths.db)
        applied = db.schema_version()
        latest = len(discover_migrations())
        state = _OK if applied == latest else _WARN
        rows.append(("database", state, f"schema {applied}/{latest}"))
        db.close()
    except sqlite3.DatabaseError as exc:
        rows.append(("database", _WARN, str(exc)))

    outbox = list(paths.outbox_dir.glob("*.json")) if paths.outbox_dir.is_dir() else []
    rows.append(("databricks outbox", _OK if not outbox else _WARN, f"{len(outbox)} queued"))

    # -- integrations (presence only) ----------------------------
    if config is not None:
        rows.append(_llm_row(config))
    dbx = resolve_databricks_credentials()
    rows.append(
        (
            "databricks creds",
            _OK if dbx else _MISS,
            "DATABRICKS_HOST/TOKEN/WAREHOUSE_ID set" if dbx else "not set (analytics stay local)",
        )
    )

    _render(rows)
    if strict and any(state == _WARN for _, state, _ in rows):
        raise typer.Exit(1)


def _render(rows: list[tuple[str, str, str]]) -> None:
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="bold cyan", no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(overflow="fold")
    for name, state, detail in rows:
        table.add_row(name, state, detail)
    console.print()
    console.print(table)


def _pyver_ok(version: str) -> bool:
    major, minor, *_ = (int(p) for p in version.split("."))
    return (major, minor) >= (3, 11)


def _tool(label: str, exe: str, args: list[str]) -> tuple[str, str, str]:
    path = shutil.which(exe)
    if path is None:
        return (label, _WARN, "not found")
    try:
        out = subprocess.run(  # noqa: S603 - fixed exe, arg list, no shell
            [path, *args], capture_output=True, text=True, timeout=5, check=False
        )
        first = (out.stdout or out.stderr).strip().splitlines()
        return (label, _OK, first[0] if first else path)
    except (OSError, subprocess.SubprocessError):
        return (label, _WARN, "error running")


def _fallback(name: str) -> str | None:
    home = Path.home()
    for candidate in (
        home / ".local" / "bin" / name,
        home / ".local" / "bin" / f"{name}.exe",
        home / "AppData" / "Local" / "entire" / "plugins" / "bin" / f"{name}.exe",
        home / ".local" / "share" / "entire" / "plugins" / "bin" / name,
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def _llm_row(config: DevMemoryConfig) -> tuple[str, str, str]:
    configured = [p for p in config.analysis.providers if p != "rules"]
    have = [p for p in configured if resolve_llm_api_key(p)]
    if not configured:
        return ("llm analysis", _OK, "rules only (no LLM configured)")
    if have:
        return ("llm analysis", _OK, f"key present for: {', '.join(have)}")
    return ("llm analysis", _WARN, f"providers {configured} configured but no key in env")


__all__ = ["doctor_command"]
