"""Lightweight feature attribution.

Phase 4 only uses cheap signals - an explicit flag, a conventional-commit scope,
or a keyword in the intent. LLM classification is a later phase.
"""

from __future__ import annotations

import re

_CC_SCOPE = re.compile(r"^\s*\w+\(([^)]+)\)\s*:", re.IGNORECASE)

_KEYWORD_FEATURES: dict[str, tuple[str, ...]] = {
    "Authentication": ("auth", "login", "jwt", "token", "oauth", "session", "password", "signup"),
    "Payments": ("payment", "billing", "checkout", "stripe", "invoice", "subscription"),
    "Notifications": ("notification", "email", "webhook", "push notification", "alerting"),
    "Search": ("search", "index", "query", "elasticsearch", "full-text"),
    "API": ("endpoint", "route", "rest api", "graphql", "api gateway"),
    "Inference": ("inference", "serving", "latency", "throughput", "tensorrt", "onnx"),
    "Training": ("training", "train", "epoch", "learning rate", "optimizer", "loss"),
    "Data Pipeline": ("etl", "pipeline", "ingest", "preprocessing", "dataset"),
}


def detect_feature(
    *,
    explicit: str | None,
    intent: str | None,
    commit_subject: str | None,
) -> tuple[str, str] | None:
    """Return ``(feature_name, derived_from)`` or ``None``."""
    if explicit:
        return explicit, "cli"

    for text, source in ((commit_subject, "commit"), (intent, "intent")):
        if not text:
            continue
        match = _CC_SCOPE.match(text)
        if match:
            return _titleize(match.group(1)), source

    haystack = f"{intent or ''} {commit_subject or ''}".lower()
    for feature, keywords in _KEYWORD_FEATURES.items():
        if any(kw in haystack for kw in keywords):
            return feature, "intent"
    return None


def _titleize(scope: str) -> str:
    return scope.replace("-", " ").replace("_", " ").strip().title()


__all__ = ["detect_feature"]
