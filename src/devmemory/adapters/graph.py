"""Change-impact analysis via the Entire ``graph`` plugin (optional).

``entire graph`` builds a deterministic, no-egress local code graph. We use its
``commit`` analysis: an entity-level change list (added / removed / renamed /
signature-changed / body-changed) with a dependent count, so a signature change
that many callers depend on stands out.

The plugin is opt-in (`entire plugin install graph`, `graph.enabled = true`).
Everything here degrades to ``None`` when it is missing or slow - it never blocks
a checkpoint.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field, computed_field

from devmemory.logging import get_logger

_log = get_logger(__name__)

# entity change types the plugin emits, ordered by how much they usually matter
_SEVERITY = {
    "removed": 4,
    "signature_changed": 3,
    "renamed": 2,
    "added": 1,
    "body_changed": 1,
}


class GraphStatus(BaseModel):
    installed: bool = False
    version: str | None = None
    binary_path: str | None = None
    detail: str | None = None


class ChangedEntity(BaseModel):
    path: str
    language: str | None = None
    file_status: str  # A | M | D | R
    change_type: str  # added | removed | renamed | signature_changed | body_changed
    kind: str  # function | method | type | section | ...
    name: str
    dependents_count: int = 0
    old_signature: str | None = None
    new_signature: str | None = None
    line: int | None = None

    @property
    def is_risky(self) -> bool:
        return self.change_type in ("removed", "signature_changed") and self.dependents_count > 0


class GraphImpact(BaseModel):
    version_id: str | None = None
    base_commit: str
    head_commit: str
    entities: list[ChangedEntity] = Field(default_factory=list)
    generated_at: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def entity_count(self) -> int:
        return len(self.entities)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_dependents(self) -> int:
        return max((e.dependents_count for e in self.entities), default=0)

    @property
    def hotspots(self) -> list[ChangedEntity]:
        ranked = sorted(
            self.entities,
            key=lambda e: (_SEVERITY.get(e.change_type, 0), e.dependents_count),
            reverse=True,
        )
        return [
            e
            for e in ranked
            if e.dependents_count > 0 or e.change_type in ("removed", "signature_changed")
        ][:10]


class GraphAdapter:
    def __init__(
        self,
        repo_path: Path | str,
        *,
        binary: str | None = None,
        timeout: int = 90,
        max_seconds: int = 120,
    ) -> None:
        self._cwd = Path(repo_path).resolve()
        self._binary = binary or _find_binary()
        self._timeout = timeout
        self._max_seconds = max_seconds

    @property
    def binary_path(self) -> str | None:
        return self._binary

    @property
    def is_available(self) -> bool:
        return self._binary is not None

    def probe(self) -> GraphStatus:
        if self._binary is None:
            return GraphStatus(
                installed=False,
                detail="entire-graph not found; run `entire plugin install graph`",
            )
        proc = self._run("version", "--json", timeout=15)
        version: str | None = None
        if proc is not None and proc.returncode == 0 and proc.stdout.strip():
            try:
                version = json.loads(proc.stdout).get("version")
            except (json.JSONDecodeError, AttributeError):
                version = None
        return GraphStatus(installed=True, version=version, binary_path=self._binary)

    def commit_impact(self, rev: str) -> GraphImpact | None:
        """Entity-level change list for ``rev`` versus its first parent."""
        if self._binary is None:
            return None
        proc = self._run(
            "commit",
            "--json",
            "--max-seconds",
            str(self._max_seconds),
            rev,
            timeout=self._timeout,
        )
        if proc is None or proc.returncode != 0 or not proc.stdout.strip():
            if proc is not None:
                _log.warning("graph.commit_failed", rev=rev, stderr=proc.stderr[:400])
            return None
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            _log.warning("graph.bad_json", rev=rev)
            return None
        return _parse_commit(data)

    # -- process plumbing ------------------------------------------------

    def _run(self, *args: str, timeout: int = 90) -> subprocess.CompletedProcess[str] | None:
        if self._binary is None:
            return None
        try:
            return subprocess.run(  # noqa: S603 - resolved binary, arg list, no shell
                [self._binary, *args, "--repo", str(self._cwd)],
                cwd=self._cwd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            _log.warning("graph.run_failed", args=list(args), error=str(exc))
            return None


def _parse_commit(data: object) -> GraphImpact | None:
    if not isinstance(data, dict):
        return None
    files = data.get("files")
    if not isinstance(files, list):
        return None
    entities: list[ChangedEntity] = []
    for f in files:
        if not isinstance(f, dict):
            continue
        path = str(f.get("path", ""))
        language = f.get("language")
        file_status = str(f.get("status", "M"))
        for change in f.get("changes", []) or []:
            if not isinstance(change, dict):
                continue
            entities.append(
                ChangedEntity(
                    path=path,
                    language=language if isinstance(language, str) else None,
                    file_status=file_status,
                    change_type=str(change.get("type", "body_changed")),
                    kind=str(change.get("kind", "symbol")),
                    name=str(change.get("name", "?")),
                    dependents_count=int(change.get("dependents_count") or 0),
                    old_signature=_opt_str(change.get("old_signature")),
                    new_signature=_opt_str(change.get("new_signature")),
                    line=_opt_int(
                        change.get("after_start_line") or change.get("before_start_line")
                    ),
                )
            )
    return GraphImpact(
        base_commit=str(data.get("base", "")),
        head_commit=str(data.get("head", "")),
        entities=entities,
    )


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _opt_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _find_binary() -> str | None:
    found = shutil.which("entire-graph")
    if found:
        return found

    candidates: list[Path] = []
    home = Path.home()
    local_appdata = os.environ.get("LOCALAPPDATA")
    xdg_data = os.environ.get("XDG_DATA_HOME")
    plugin_env = os.environ.get("ENTIRE_PLUGIN_DIR")

    for base in (
        Path(plugin_env) if plugin_env else None,
        Path(local_appdata) / "entire" / "plugins" if local_appdata else None,
        Path(xdg_data) / "entire" / "plugins" if xdg_data else None,
        home / "AppData" / "Local" / "entire" / "plugins",
        home / ".local" / "share" / "entire" / "plugins",
    ):
        if base is None:
            continue
        candidates.append(base / "bin" / "entire-graph.exe")
        candidates.append(base / "bin" / "entire-graph")
        candidates.append(base / "pkg" / "graph" / "entire-graph.exe")
        candidates.append(base / "pkg" / "graph" / "entire-graph")

    for path in candidates:
        if path.is_file():
            return str(path)
    return None


__all__ = ["ChangedEntity", "GraphAdapter", "GraphImpact", "GraphStatus"]
