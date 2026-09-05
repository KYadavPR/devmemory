"""Structured logging with secret redaction.

DevMemory must be diagnosable (which operation failed, which integration, was
project state changed, what next) without ever writing a credential to a log.
``configure_logging`` wires up structlog; a redaction processor scrubs both
known-sensitive keys and any value that matches a live environment secret.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog

_REDACTED = "***redacted***"

_SENSITIVE_KEY_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "auth_header",
    "access_key",
    "private_key",
    "client_secret",
)

_SENSITIVE_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "API_KEY",
    "APIKEY",
    "ACCESS_KEY",
    "PRIVATE_KEY",
)

_configured = False


def _live_secret_values() -> set[str]:
    """Non-trivial values of environment variables that look like secrets."""
    values: set[str] = set()
    for name, value in os.environ.items():
        if not value or len(value) < 6:
            continue
        if any(marker in name.upper() for marker in _SENSITIVE_ENV_MARKERS):
            values.add(value)
    return values


def _redact_value(value: Any, secrets: set[str]) -> Any:
    if isinstance(value, str):
        if value in secrets:
            return _REDACTED
        redacted = value
        for secret in secrets:
            if secret and secret in redacted:
                redacted = redacted.replace(secret, _REDACTED)
        return redacted
    if isinstance(value, dict):
        return {k: _redact_mapping_entry(k, v, secrets) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(v, secrets) for v in value)
    return value


def _redact_mapping_entry(key: Any, value: Any, secrets: set[str]) -> Any:
    if isinstance(key, str) and any(marker in key.lower() for marker in _SENSITIVE_KEY_MARKERS):
        return _REDACTED
    return _redact_value(value, secrets)


def _redaction_processor(
    _logger: object, _method: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    secrets = _live_secret_values()
    return {k: _redact_mapping_entry(k, v, secrets) for k, v in event_dict.items()}


def configure_logging(*, level: str = "INFO", json_logs: bool | None = None) -> None:
    """Initialise structlog. Safe to call more than once (later calls reconfigure).

    ``json_logs`` defaults to ``True`` when stderr is not a TTY (CI, pipes),
    ``False`` (rich console renderer) when it is.
    """
    global _configured

    if json_logs is None:
        json_logs = not sys.stderr.isatty()

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=numeric_level,
        force=True,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _redaction_processor,
    ]

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger, configuring logging with defaults on first use."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)  # type: ignore[no-any-return]


__all__ = ["configure_logging", "get_logger"]
