"""``devmemory restore`` - move the working tree back to an earlier version, safely."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from devmemory.cli._render import console, hint, kv_table, success, warn
from devmemory.services.context import ProjectContext
from devmemory.services.restore import restore_preview, restore_version


def restore_command(
    version: Annotated[str, typer.Argument(help="Version to restore: v7 / 7 / a commit prefix.")],
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt.")] = False,
    hard: Annotated[
        bool,
        typer.Option(
            "--hard", help="`git reset --hard` instead of a detached checkout (requires -y)."
        ),
    ] = False,
    allow_dirty: Annotated[
        bool,
        typer.Option(
            "--allow-dirty", help="Proceed with uncommitted changes (a safety stash is kept)."
        ),
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Restore the source tree to the git state of a previous development version.

    Always previews first. A safety tag is created at the current HEAD (and a
    ``git stash create`` reference if the tree is dirty) before anything moves.
    """
    with ProjectContext.load() as ctx:
        preview = restore_preview(ctx, version)

        if as_json and not yes:
            console.print_json(json.dumps(preview.model_dump(mode="json")))
            return

        if preview.already_there:
            success(f"Already at {preview.version_id.upper()} with a clean tree.")
            return

        console.print()
        console.print(f"[bold]Restore {preview.version_id.upper()}[/bold]")
        console.print(
            kv_table(
                [
                    ("target", f"{preview.target_commit[:12]}  {preview.target_subject}"),
                    (
                        "current",
                        f"{(preview.current_commit or '-')[:12]}"
                        + (f" ({preview.current_branch})" if preview.current_branch else ""),
                    ),
                    ("mode", "reset --hard" if hard else "detached checkout"),
                    ("safety tag", preview.safety_tag),
                ]
            )
        )
        if preview.uncommitted:
            warn(
                f"{len(preview.uncommitted)} uncommitted change(s): {', '.join(preview.uncommitted[:5])}"
            )
        console.print(f"\n[yellow]{preview.warning}[/yellow]\n")

        if hard and not yes:
            raise typer.BadParameter("--hard requires --yes")
        if not yes and not typer.confirm("Proceed with the restore?"):
            console.print("[dim]cancelled[/dim]")
            raise typer.Exit(1)

        result = restore_version(
            ctx,
            version,
            mode="hard" if hard else "detach",
            allow_dirty=allow_dirty,
        )

    if as_json:
        console.print_json(json.dumps(result.model_dump(mode="json")))
        return
    success(result.message)
    if result.stash_ref:
        hint(f"uncommitted work saved as {result.stash_ref[:12]}")


__all__ = ["restore_command"]
