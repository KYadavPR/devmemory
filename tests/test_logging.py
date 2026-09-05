"""Structured logging and secret redaction."""

from __future__ import annotations

import json

import pytest

from devmemory import logging as dm_logging
from devmemory.logging import configure_logging, get_logger


def _redact(event: dict[str, object]) -> dict[str, object]:
    return dm_logging._redaction_processor(None, "info", event)


def test_sensitive_keys_are_redacted() -> None:
    out = _redact({"api_key": "super-secret", "nested": {"password": "hunter2", "ok": 1}})
    assert out["api_key"] == "***redacted***"
    assert out["nested"]["password"] == "***redacted***"  # type: ignore[index]
    assert out["nested"]["ok"] == 1  # type: ignore[index]


def test_list_and_tuple_values_are_walked() -> None:
    out = _redact({"items": [{"token": "abc"}, {"fine": "yes"}]})
    assert out["items"][0]["token"] == "***redacted***"  # type: ignore[index]
    assert out["items"][1]["fine"] == "yes"  # type: ignore[index]


def test_live_env_secret_value_is_scrubbed_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapiSECRET1234567890")
    out = _redact({"url": "https://x?token=dapiSECRET1234567890&z=1", "note": "clean"})
    assert "dapiSECRET1234567890" not in json.dumps(out)
    assert out["note"] == "clean"


def test_short_env_values_are_not_treated_as_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "abc")  # too short to scrub blindly
    out = _redact({"msg": "abc def"})
    assert out["msg"] == "abc def"


def test_plain_values_pass_through() -> None:
    out = _redact({"commit": "7fa91c", "count": 3})
    assert out == {"commit": "7fa91c", "count": 3}


def test_configure_and_get_logger_do_not_raise() -> None:
    configure_logging(level="DEBUG", json_logs=True)
    get_logger("fresh").info("hello", commit="7fa91c")
    configure_logging(level="INFO", json_logs=False)
    get_logger().warning("again")
