"""Best-effort snapshot of the local toolchain.

Attached to development versions (Phase 3+) so history records what produced it.
Collects nothing personal - versions and platform strings only.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from devmemory.domain.models import EnvironmentInfo


def _first_line(executable: str, *args: str) -> str | None:
    path = shutil.which(executable)
    if path is None:
        return None
    try:
        proc = subprocess.run(  # noqa: S603 - fixed executable, arg list, no shell
            [path, *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (proc.stdout or proc.stderr).strip()
    return text.splitlines()[0].strip() if text else None


def _detect_package_manager(repo_path: Path) -> str | None:
    markers = {
        "uv.lock": "uv",
        "poetry.lock": "poetry",
        "Pipfile.lock": "pipenv",
        "pdm.lock": "pdm",
        "requirements.txt": "pip",
        "pyproject.toml": "pip",
        "package-lock.json": "npm",
        "pnpm-lock.yaml": "pnpm",
        "yarn.lock": "yarn",
        "go.mod": "go",
        "Cargo.toml": "cargo",
    }
    for marker, name in markers.items():
        if (repo_path / marker).exists():
            return name
    return None


def collect_environment(repo_path: Path | str = ".") -> EnvironmentInfo:
    repo_path = Path(repo_path)
    return EnvironmentInfo(
        python_version=platform.python_version(),
        platform=f"{platform.system()} {platform.release()}",
        machine=platform.machine(),
        git_version=_first_line("git", "--version"),
        entire_version=_first_line("entire", "version"),
        package_manager=_detect_package_manager(repo_path),
    )


__all__ = ["collect_environment"]
