"""Configuration loading, merging, and secret hygiene."""

from __future__ import annotations

import json

import pytest

from devmemory.config import (
    DevMemoryConfig,
    resolve_databricks_credentials,
    resolve_llm_api_key,
)
from devmemory.domain.enums import MetricDirection
from devmemory.domain.errors import ConfigError
from devmemory.paths import ProjectPaths


def test_save_then_load_roundtrip(project_paths: ProjectPaths) -> None:
    original = DevMemoryConfig.default_for(project_id="visionai", project_name="VisionAI")
    original.tests.command = "pytest -q"
    original.metrics.directions = {"latency_ms": MetricDirection.LOWER_IS_BETTER}
    original.save(project_paths)

    loaded = DevMemoryConfig.load(project_paths)

    assert loaded.project_id == "visionai"
    assert loaded.tests.command == "pytest -q"
    assert loaded.metrics.directions["latency_ms"] is MetricDirection.LOWER_IS_BETTER


def test_local_override_is_deep_merged(project_paths: ProjectPaths) -> None:
    DevMemoryConfig.default_for(project_id="p", project_name="P").save(project_paths)
    project_paths.config_local.write_text(
        json.dumps({"web": {"port": 9999}, "databricks": {"enabled": True}}),
        encoding="utf-8",
    )

    loaded = DevMemoryConfig.load(project_paths)

    assert loaded.web.port == 9999
    assert loaded.web.host == "127.0.0.1"  # untouched default
    assert loaded.databricks.enabled is True


def test_schema_alias_is_used_on_disk(project_paths: ProjectPaths) -> None:
    cfg = DevMemoryConfig.default_for(project_id="p", project_name="P")
    cfg.databricks.schema_name = "intelligence"
    cfg.save(project_paths)

    on_disk = json.loads(project_paths.config.read_text(encoding="utf-8"))

    assert on_disk["databricks"]["schema"] == "intelligence"
    assert "schema_name" not in on_disk["databricks"]


def test_saved_config_contains_no_secret_keys(project_paths: ProjectPaths) -> None:
    DevMemoryConfig.default_for(project_id="p", project_name="P").save(project_paths)
    text = project_paths.config.read_text(encoding="utf-8").lower()
    for marker in ("token", "secret", "password", "api_key", "apikey"):
        assert marker not in text


def test_load_without_config_raises(project_paths: ProjectPaths) -> None:
    with pytest.raises(ConfigError):
        DevMemoryConfig.load(project_paths)


def test_load_rejects_unknown_keys(project_paths: ProjectPaths) -> None:
    project_paths.config.write_text(
        json.dumps({"project_id": "p", "project_name": "P", "bogus": 1}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        DevMemoryConfig.load(project_paths)


def test_databricks_credentials_need_all_three(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABRICKS_HOST", raising=False)
    monkeypatch.delenv("DATABRICKS_TOKEN", raising=False)
    monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
    assert resolve_databricks_credentials() is None

    monkeypatch.setenv("DATABRICKS_HOST", "https://x.databricks.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapiXXXXXXXX")
    assert resolve_databricks_credentials() is None  # warehouse still missing

    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "abc123")
    creds = resolve_databricks_credentials()
    assert creds is not None
    assert creds.warehouse_id == "abc123"


def test_llm_api_key_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-123")
    assert resolve_llm_api_key("anthropic") == "sk-ant-123"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert resolve_llm_api_key("openai") is None
    assert resolve_llm_api_key("unknown-provider") is None
