"""Entire adapter - the only place DevMemory invokes the ``entire`` CLI or reads
its git refs.

Phase 1 ships detection (:meth:`EntireAdapter.probe`). Checkpoint resolution -
the trailer -> ``entire checkpoint explain`` -> direct git-ref ladder - lands in
Phase 2. See docs/IMPLEMENTATION_STRATEGY.md sec. 3.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from devmemory.domain.models import EntireStatus
from devmemory.logging import get_logger

_log = get_logger(__name__)


class EntireAdapter:
    """Wraps the installed Entire CLI. Every method degrades gracefully when the
    CLI is absent, disabled, or returns something unexpected - it never raises for
    "Entire is just not here" and never fabricates checkpoint data.
    """

    def __init__(
        self,
        repo_path: Path | str,
        *,
        binary: str | None = None,
        repo: str | None = None,
    ) -> None:
        self._cwd = Path(repo_path).resolve()
        self._repo = repo
        self._binary = binary or _find_binary()

    # -- process plumbing --------------------------------------------------

    @property
    def binary_path(self) -> str | None:
        return self._binary

    def _run(self, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str] | None:
        if self._binary is None:
            return None
        cmd = [self._binary, *args]
        if self._repo and "--repo" not in args:
            cmd += ["--repo", self._repo]
        env = {**os.environ, "ENTIRE_TOKEN_STORE": os.environ.get("ENTIRE_TOKEN_STORE", "file")}
        try:
            return subprocess.run(  # noqa: S603 - resolved binary, arg list, no shell
                cmd,
                cwd=self._cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _log.warning("entire.run_failed", args=list(args), error=str(exc))
            return None

    def _run_json(self, *args: str, timeout: int = 30) -> object | None:
        proc = self._run(*args, timeout=timeout)
        if proc is None or proc.returncode != 0 or not proc.stdout.strip():
            return None
        try:
            parsed: object = json.loads(proc.stdout)
        except json.JSONDecodeError:
            _log.warning("entire.bad_json", args=list(args))
            return None
        return parsed

    # -- detection -------------------------------------------------------

    def is_installed(self) -> bool:
        return self._binary is not None

    def cli_version(self) -> str | None:
        proc = self._run("version")
        if proc is None or proc.returncode != 0:
            return None
        for line in proc.stdout.splitlines():
            if line.lower().startswith("entire cli"):
                return line.split("Entire CLI", 1)[-1].strip() or line.strip()
        return proc.stdout.splitlines()[0].strip() if proc.stdout.strip() else None

    def probe(self) -> EntireStatus:
        """Full detection snapshot for ``init`` / ``status`` / ``doctor``."""
        if self._binary is None:
            return EntireStatus(installed=False, detail="entire CLI not found on PATH")

        status = EntireStatus(
            installed=True,
            binary_path=self._binary,
            cli_version=self.cli_version(),
        )
        data = self._run_json("status", "--json")
        if isinstance(data, dict):
            status.enabled = bool(data.get("enabled"))
            agents = data.get("agents")
            if isinstance(agents, list):
                status.agents = [str(a) for a in agents]
            if not status.enabled:
                status.detail = "Entire is installed but not enabled in this repository"
        else:
            status.detail = "could not read `entire status --json`"
        return status


def _find_binary() -> str | None:
    found = shutil.which("entire")
    if found:
        return found
    for candidate in (
        Path.home() / ".local" / "bin" / "entire.exe",
        Path.home() / ".local" / "bin" / "entire",
        Path.home() / "go" / "bin" / "entire.exe",
        Path.home() / "go" / "bin" / "entire",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


__all__ = ["EntireAdapter"]
