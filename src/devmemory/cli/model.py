"""``devmemory model`` - manage the bundled on-device LLM.

    devmemory model pull      # download the GGUF (~1 GB) and turn it on
    devmemory model status    # runtime, download state, config
    devmemory model remove    # delete the cached model file

Once pulled, the analysis chain and the dashboard's Ask chat use it with no API
key and nothing leaving the machine.
"""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.markup import escape
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn

from devmemory.adapters import local_model as lm
from devmemory.cli._render import console, hint, success, warn
from devmemory.config import LocalModelSettings
from devmemory.domain.errors import DevMemoryError
from devmemory.paths import find_project_paths

_PIP_EXTRA = escape('pip install "devmemory-cli[local-llm]"')

model_app = typer.Typer(
    name="model",
    help="Manage the bundled on-device LLM (no API key, fully local).",
    no_args_is_help=True,
)


def _settings() -> LocalModelSettings:
    """The project's local_model config if we're in a project, else defaults."""
    paths = find_project_paths()
    if paths is None:
        return LocalModelSettings()
    try:
        from devmemory.config import DevMemoryConfig

        return DevMemoryConfig.load(paths).local_model
    except DevMemoryError:
        return LocalModelSettings()


def _enable_in_config(settings: LocalModelSettings) -> bool:
    """Persist the model choice, set ``enabled``, and put ``local`` first in
    ``analysis.providers``.

    Returns False (with a warning) when run outside a project - the download
    still happened, it just isn't wired in anywhere.
    """
    paths = find_project_paths()
    if paths is None or not paths.config.is_file():
        return False
    data = json.loads(paths.config.read_text(encoding="utf-8"))
    local = data.setdefault("local_model", {})
    local.update(enabled=True, repo=settings.repo, filename=settings.filename)
    analysis = data.setdefault("analysis", {})
    providers = [p for p in analysis.get("providers", []) if p != "local"]
    analysis["providers"] = ["local", *providers] if providers else ["local", "rules"]
    paths.config.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


@model_app.command("pull")
def pull(
    repo: Annotated[str | None, typer.Option("--repo", help="Override the HF repo id.")] = None,
    filename: Annotated[str | None, typer.Option("--file", help="Override the GGUF filename.")] = None,
) -> None:
    """Download the model and enable it for this project."""
    settings = _settings()
    if repo or filename:
        settings = settings.model_copy(
            update={"repo": repo or settings.repo, "filename": filename or settings.filename}
        )

    if not lm.runtime_available():
        warn("the local-llm runtime is not installed.")
        hint(_PIP_EXTRA)
        raise typer.Exit(1)

    if lm.is_downloaded(settings):
        console.print(f"[dim]{settings.filename} already downloaded[/dim] ({lm.model_path(settings)})")
    else:
        console.print(f"Downloading [bold]{settings.filename}[/bold] from {settings.repo}")
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("model", total=None)

            def _on(done: int, total: int) -> None:
                progress.update(task, completed=done, total=total or None)

            path = lm.download_model(settings, on_progress=_on)
        success(f"downloaded to {path}")

    wired = _enable_in_config(settings)
    if wired:
        success("enabled - `analysis.providers` now starts with `local`")
        hint("Ask + `devmemory analyze` now use the on-device model. No key needed.")
    else:
        warn("not in a DevMemory project - downloaded but not wired into any config")
        hint("Run this again inside your project, or set local_model.enabled + analysis.providers.")


@model_app.command("status")
def status() -> None:
    """Show runtime, download state and where the model lives."""
    settings = _settings()
    runtime = lm.runtime_available()
    downloaded = lm.is_downloaded(settings)

    console.print(f"runtime      {'installed' if runtime else 'not installed'}")
    if not runtime:
        hint(_PIP_EXTRA)
    console.print(f"model        {settings.repo}/{settings.filename}")
    if downloaded:
        size = lm.model_path(settings).stat().st_size / 1e9
        console.print(f"downloaded   yes ({size:.2f} GB)  {lm.model_path(settings)}")
    else:
        console.print("downloaded   no")
        hint("run `devmemory model pull`")
    console.print(f"ready        {'yes' if lm.is_ready(settings) else 'no'}")


@model_app.command("remove")
def remove() -> None:
    """Delete the cached model file (config is left as-is)."""
    settings = _settings()
    if lm.remove_model(settings):
        success(f"removed {settings.filename}")
    else:
        console.print("[dim]nothing to remove[/dim]")


__all__ = ["model_app"]
