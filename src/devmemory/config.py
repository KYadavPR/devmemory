"""Project configuration.

Precedence, lowest to highest:

1. Built-in defaults (this module).
2. ``.devmemory/config.json``     - committed, shared, never contains secrets.
3. ``.devmemory/config.local.json`` - git-ignored, per-developer overrides.
4. Environment variables          - the only place secrets are read from.

``DevMemoryConfig`` models (2) and (3). Secrets (Databricks token, LLM API keys)
are resolved separately, at call time, by the adapters that need them - they are
never loaded into this object, never logged, and never written back to disk.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from devmemory.domain.enums import MetricDirection
from devmemory.domain.errors import ConfigError
from devmemory.paths import ProjectPaths

# --- section models ------------------------------------------------------------------


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class EntireSettings(_Section):
    """How DevMemory talks to the Entire CLI."""

    enabled: bool = True
    binary: str | None = Field(
        default=None,
        description="Absolute path to the `entire` binary. Defaults to PATH lookup.",
    )
    repo: str | None = Field(
        default=None,
        description="`owner/name` passed to `entire --repo` when auto-detection fails.",
    )


class TestSettings(_Section):
    """Optional test collection during `devmemory checkpoint`."""

    command: str | None = Field(
        default=None,
        description="Shell command to run, e.g. `pytest -q`, `npm test`, `go test ./...`.",
    )
    parser: str = Field(
        default="auto",
        description="Result parser: auto | pytest | junitxml | generic.",
    )
    junit_xml: str | None = Field(
        default=None,
        description="Path to a JUnit XML report to parse instead of stdout.",
    )
    timeout_seconds: int = 900


class MetricSettings(_Section):
    """Where project metrics come from and which direction is 'better'."""

    file: str | None = Field(
        default=None,
        description="JSON file read after tests run; keys become metric names.",
    )
    command: str | None = Field(
        default=None,
        description="Command whose JSON stdout provides metrics.",
    )
    directions: dict[str, MetricDirection] = Field(default_factory=dict)


class ArtifactSettings(_Section):
    enabled: bool = True
    exclude: list[str] = Field(
        default_factory=lambda: [
            ".git",
            ".devmemory",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
        ]
    )


class DatabricksSettings(_Section):
    """Non-secret Databricks settings. Host / token / warehouse come from env."""

    enabled: bool = False
    catalog: str = "devmemory"
    schema_name: str = Field(default="analytics", alias="schema")


class RegressionSettings(_Section):
    """Thresholds for the rule-based regression detector."""

    metric_pct: float = 2.0
    metric_abs_floor: float = 1e-9
    high_pct: float = 15.0
    medium_pct: float = 6.0


class AnalysisSettings(_Section):
    """LLM-backed analysis. Providers are tried in order; `rules` never fails.

    Analysis is interpretation, kept structurally separate from facts - it can
    never overwrite Git / Entire / test / metric data.
    """

    enabled: bool = True
    providers: list[str] = Field(
        default_factory=lambda: ["rules"],
        description="Ordered fallback chain, e.g. ['anthropic', 'openai', 'rules']. "
        "Keys come from the environment. `rules` always succeeds.",
    )
    model: str | None = Field(
        default=None,
        description="Model id for the active LLM provider (provider default otherwise).",
    )
    include_diff: bool = Field(
        default=False,
        description="Send a truncated unified diff to the LLM. Off by default - "
        "otherwise only normalized facts leave the machine.",
    )
    max_diff_bytes: int = 4000


class GraphSettings(_Section):
    """Optional change-impact analysis via the Entire `graph` plugin.

    Off by default - it needs `entire plugin install graph` and rebuilds a local
    code graph per run (a few seconds). Fully local, no egress.
    """

    enabled: bool = False
    binary: str | None = Field(
        default=None,
        description="Absolute path to the `entire-graph` binary. Defaults to a managed-dir lookup.",
    )
    timeout_seconds: int = 90
    max_seconds: int = 120


class WebSettings(_Section):
    host: str = "127.0.0.1"
    port: int = 8760
    enable_restore: bool = False


# --- root model ---------------------------------------------------------------------


class DevMemoryConfig(_Section):
    """The complete project configuration (defaults + config.json + config.local.json)."""

    project_id: str
    project_name: str
    entire: EntireSettings = Field(default_factory=EntireSettings)
    tests: TestSettings = Field(default_factory=TestSettings)
    metrics: MetricSettings = Field(default_factory=MetricSettings)
    artifacts: ArtifactSettings = Field(default_factory=ArtifactSettings)
    regression: RegressionSettings = Field(default_factory=RegressionSettings)
    databricks: DatabricksSettings = Field(default_factory=DatabricksSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    graph: GraphSettings = Field(default_factory=GraphSettings)
    web: WebSettings = Field(default_factory=WebSettings)

    # -- construction --------------------------------------------------------------

    @classmethod
    def default_for(cls, *, project_id: str, project_name: str) -> DevMemoryConfig:
        return cls(project_id=project_id, project_name=project_name)

    @classmethod
    def load(cls, paths: ProjectPaths) -> DevMemoryConfig:
        """Load and validate config for a project, merging the local override file."""
        base = _read_json(paths.config)
        if not base:
            raise ConfigError(
                f"No configuration found at {paths.config}.",
                hint="Run `devmemory init` to create it.",
            )
        override = _read_json(paths.config_local)
        merged = _deep_merge(base, override)
        try:
            return cls.model_validate(merged)
        except ValidationError as exc:
            raise ConfigError(f"Invalid DevMemory configuration: {exc}") from exc

    # -- persistence -------------------------------------------------------------

    def to_config_dict(self) -> dict[str, Any]:
        """The JSON form written to ``config.json`` (by alias, secret-free by design)."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def save(self, paths: ProjectPaths) -> None:
        paths.root.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(paths.config, self.to_config_dict())


# --- runtime secret resolution (env only) ------------------------------------------


class DatabricksCredentials(BaseModel):
    host: str
    token: str
    warehouse_id: str


def resolve_databricks_credentials() -> DatabricksCredentials | None:
    """Read Databricks credentials from the environment. Returns ``None`` if incomplete.

    Recognised: ``DATABRICKS_HOST``, ``DATABRICKS_TOKEN``, ``DATABRICKS_WAREHOUSE_ID``.
    """
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")
    warehouse = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if host and token and warehouse:
        return DatabricksCredentials(host=host, token=token, warehouse_id=warehouse)
    return None


_LLM_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "google": "GOOGLE_API_KEY",
}


def resolve_llm_api_key(provider: str) -> str | None:
    """Return the API key for an LLM provider from the environment, if present."""
    env_var = _LLM_API_KEY_ENV.get(provider.lower())
    if env_var is None:
        return None
    key = os.environ.get(env_var)
    if not key and provider.lower() == "gemini":
        key = os.environ.get("GOOGLE_API_KEY")
    return key or None


# --- helpers ---------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object, got {type(data).__name__}.")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto ``base`` without mutating either."""
    result = dict(base)
    for key, value in override.items():
        existing = result.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            result[key] = _deep_merge(existing, value)
        else:
            result[key] = value
    return result


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


__all__ = [
    "AnalysisSettings",
    "ArtifactSettings",
    "DatabricksCredentials",
    "DatabricksSettings",
    "DevMemoryConfig",
    "EntireSettings",
    "GraphSettings",
    "MetricSettings",
    "RegressionSettings",
    "TestSettings",
    "WebSettings",
    "resolve_databricks_credentials",
    "resolve_llm_api_key",
]
