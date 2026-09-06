"""Privacy boundary enforcement for DevMemory.

Track 1: Privacy Boundary rules:
1. Raw Entire Checkpoint prompts and transcripts must NOT be sent to any external service.
2. DevMemory must continue providing useful output when sensitive Checkpoint fields are redacted, missing, or unavailable.
3. Existing local functionality must continue working without requiring external services.
4. Local dashboard and APIs must clearly indicate context completeness (COMPLETE / PARTIAL / MISSING).
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from devmemory.domain.enums import AnalysisConfidence, ContextStatus

# Fields that MUST NEVER be sent across privacy boundaries to external analytics / services
SENSITIVE_FIELDS: frozenset[str] = frozenset({
    "prompt",
    "prompt.txt",
    "transcript",
    "transcripts",
    "intent",
    "raw_context",
    "messages",
    "conversation",
    "user_prompt",
    "full_transcript",
    "diff_content",
    "patch",
    "secret",
    "token",
    "api_key",
    "password",
})

# Safe fields permitted to cross boundaries to Databricks / external analytics
SAFE_EXPORT_FIELDS: frozenset[str] = frozenset({
    "project_id",
    "version_id",
    "version_number",
    "context_status",
    "agent",
    "model",
    "checkpoint_id",
    "association_method",
    "association_confidence",
    "git_commit",
    "parent_commit",
    "branch",
    "feature",
    "status",
    "files_changed",
    "lines_added",
    "lines_removed",
    "is_regression",
    "regression_severity",
    "tests_total",
    "tests_passed",
    "tests_failed",
    "committed_at",
    "recorded_at",
})

_REDACTED_EXACT = {
    "[REDACTED]",
    "<REDACTED>",
    "REDACTED",
    "***",
    "[MASKED]",
    "<MASKED>",
    "[REMOVED]",
    "REDACTED_BY_USER",
    "[CONFIDENTIAL]",
}

_REDACTED_PATTERN = re.compile(
    r"^(\[|\<|\*\*\*|)(REDACTED|MASKED|REMOVED|CONFIDENTIAL)(\]|\>|\*\*\*|)$",
    re.IGNORECASE,
)


def is_redacted(value: object) -> bool:
    """Return True if a string or object represents a redaction marker."""
    if value is None:
        return False
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if stripped.upper() in _REDACTED_EXACT:
        return True
    return bool(_REDACTED_PATTERN.match(stripped))


def is_missing_or_redacted(value: object) -> bool:
    """Return True if value is None, empty string, or an explicit redaction marker."""
    if value is None:
        return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        return is_redacted(stripped)
    return False


def detect_redacted_fields(raw_data: dict[str, Any]) -> list[str]:
    """Inspect dictionary keys/values and return names of fields that contain redactions."""
    redacted: list[str] = []
    for key, val in raw_data.items():
        if is_redacted(val):
            redacted.append(key)
    return sorted(set(redacted))


def compute_context_status(
    *,
    has_checkpoint: bool,
    intent: str | None = None,
    redacted_fields: list[str] | None = None,
) -> ContextStatus:
    """Determine the normalized ContextStatus based on available context evidence."""
    if not has_checkpoint:
        return ContextStatus.MISSING

    if is_missing_or_redacted(intent) or (redacted_fields and len(redacted_fields) > 0):
        return ContextStatus.PARTIAL

    return ContextStatus.COMPLETE


def determine_analysis_confidence(context_status: ContextStatus | str) -> AnalysisConfidence:
    """Map context completeness to analysis confidence."""
    status_str = str(context_status).upper()
    if status_str == ContextStatus.COMPLETE:
        return AnalysisConfidence.FULL
    if status_str == ContextStatus.PARTIAL:
        return AnalysisConfidence.LIMITED
    return AnalysisConfidence.CODE_EVIDENCE_ONLY


def sanitize_for_export(record: dict[str, Any]) -> dict[str, Any]:
    """Produce a privacy-sanitized projection of a record for external export (e.g. Databricks).

    Guarantees:
    - No fields in SENSITIVE_FIELDS are included (e.g. intent, transcript, prompt).
    - Only fields in SAFE_EXPORT_FIELDS are returned.
    - An explicit context_status is included.
    """
    cleaned: dict[str, Any] = {}
    for key, val in record.items():
        if key in SENSITIVE_FIELDS:
            continue
        if key in SAFE_EXPORT_FIELDS:
            cleaned[key] = val

    # Ensure context_status is always present
    if "context_status" not in cleaned:
        cleaned["context_status"] = record.get("context_status", ContextStatus.COMPLETE)

    return cleaned


class ContextEnvelope(BaseModel):
    """Encapsulates context metadata and boundaries for agents and APIs."""

    context_status: ContextStatus = ContextStatus.COMPLETE
    redacted_fields: list[str] = Field(default_factory=list)
    context_sources: list[str] = Field(default_factory=list)
    analysis_confidence: AnalysisConfidence = AnalysisConfidence.FULL
    analysis_limitations: list[str] = Field(default_factory=list)
