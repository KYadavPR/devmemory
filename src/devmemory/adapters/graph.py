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


class SymbolRef(BaseModel):
    name: str
    file_path: str
    kind: str = "symbol"
    start_line: int | None = None
    depth: int = 1
    via: str | None = None  # intermediate symbol on a 2-hop path


class SymbolImpact(BaseModel):
    """`entire graph impact` for one symbol: who breaks if you change it."""

    query: str
    resolved: bool = False
    callers_total: int = 0
    callees_total: int = 0
    type_consumers_total: int = 0
    callers: list[SymbolRef] = Field(default_factory=list)
    callees: list[SymbolRef] = Field(default_factory=list)
    cochange_files: list[str] = Field(default_factory=list)
    definitions: list[SymbolRef] = Field(default_factory=list)  # set when the name is ambiguous

    @computed_field  # type: ignore[prop-decorator]
    @property
    def blast_radius(self) -> int:
        """Everything downstream that a behaviour change could break."""
        return self.callers_total + self.type_consumers_total

    @property
    def affected_files(self) -> list[str]:
        """Files with a caller that could break - not the softer co-change set."""
        return sorted({r.file_path for r in self.callers if r.file_path})


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

    def diff_impact(self, base: str, head: str = "HEAD") -> GraphImpact | None:
        """Entity-level change list between two refs (cumulative, unlike ``commit``)."""
        if self._binary is None or not base:
            return None
        proc = self._run(
            "diff",
            "--json",
            "--max-seconds",
            str(self._max_seconds),
            "--base",
            base,
            "--head",
            head,
            timeout=self._timeout,
        )
        if proc is None or proc.returncode != 0 or not proc.stdout.strip():
            if proc is not None:
                _log.warning("graph.diff_failed", base=base, head=head, stderr=proc.stderr[:400])
            return None
        try:
            return _parse_commit(json.loads(proc.stdout))
        except json.JSONDecodeError:
            _log.warning("graph.bad_json", base=base, head=head)
            return None

    def symbol_impact(self, symbol: str, *, depth: int = 2, limit: int = 15) -> SymbolImpact | None:
        """Blast radius for changing one symbol: direct + transitive callers, callees,
        type consumers, historically co-changing files.

        ``symbol`` is a bare name or ``path/to/file.py:line`` (the file:line form is
        unambiguous - prefer it when you have a location).
        """
        if self._binary is None or not symbol.strip():
            return None
        proc = self._run(
            "impact",
            "--symbol",
            symbol,
            "--format",
            "json",
            "--depth",
            str(depth),
            "--limit",
            str(limit),
            timeout=self._timeout,
        )
        if proc is None or not proc.stdout.strip():
            return None
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            _log.warning("graph.bad_json", symbol=symbol)
            return None
        return _parse_symbol_impact(symbol, data)

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


def _sym_section(node: object) -> tuple[int, list[SymbolRef]]:
    if not isinstance(node, dict):
        return 0, []
    total = int(node.get("total") or 0)
    refs: list[SymbolRef] = []
    for entry in node.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        ep = entry.get("endpoint")
        if not isinstance(ep, dict):
            continue
        refs.append(
            SymbolRef(
                name=str(ep.get("name") or ep.get("qualified_name") or "?"),
                file_path=str(ep.get("file_path") or ""),
                kind=str(ep.get("kind") or "symbol"),
                start_line=_opt_int(ep.get("start_line")),
                depth=int(entry.get("depth") or 1),
                via=_opt_str(entry.get("via")),
            )
        )
    return total, refs


def _parse_symbol_impact(query: str, data: object) -> SymbolImpact:
    if not isinstance(data, dict):
        return SymbolImpact(query=query)
    callers_total, callers = _sym_section(data.get("callers"))
    callees_total, callees = _sym_section(data.get("callees"))
    types_total, _ = _sym_section(data.get("type_consumers"))
    _, cochange = _sym_section(data.get("co_changes"))
    matched = int(data.get("focus_matches_total") or 0)
    defs: list[SymbolRef] = []
    if data.get("disambiguation_required"):
        for d in data.get("definitions") or []:
            if isinstance(d, dict):
                defs.append(
                    SymbolRef(
                        name=str(d.get("name") or "?"),
                        file_path=str(d.get("file_path") or ""),
                        kind=str(d.get("kind") or "symbol"),
                        start_line=_opt_int(d.get("start_line")),
                    )
                )
    return SymbolImpact(
        query=query,
        resolved=matched > 0 and not data.get("disambiguation_required"),
        callers_total=callers_total,
        callees_total=callees_total,
        type_consumers_total=types_total,
        callers=callers,
        callees=callees,
        cochange_files=[r.file_path for r in cochange if r.file_path],
        definitions=defs,
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


__all__ = [
    "ChangedEntity",
    "GraphAdapter",
    "GraphImpact",
    "GraphStatus",
    "SymbolImpact",
    "SymbolRef",
]
