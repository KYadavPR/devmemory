"""The analysis contract: a normalized input, a provider interface, a fact guard.

Analysis is *interpretation*. It is stored in its own table and can only ever
populate the interpretive fields (``summary``, ``reasoning``, ``recommendation``,
``warnings``, ``risk``). It can never touch a fact - Git line counts, test
results, metric values, the Entire checkpoint - because those live on the
``DevelopmentVersion`` and are never handed to a provider for writing.
"""

from __future__ import annotations

import abc

from pydantic import BaseModel, Field

from devmemory.domain.models import Analysis
from devmemory.logging import redact_secrets

_RISK_LEVELS = ("low", "medium", "high")
_MAX_SUMMARY = 1200
_MAX_FIELD = 2000


class MetricDelta(BaseModel):
    name: str
    before: float | None
    after: float | None
    direction: str
    improved: bool
    worsened: bool


class AttemptRef(BaseModel):
    version_id: str
    status: str
    result: str
    matched_on: list[str]


class ImpactRef(BaseModel):
    entity: str
    change_type: str
    dependents: int


class AnalysisInput(BaseModel):
    """Everything a provider is allowed to see. Normalized facts, no raw source
    unless ``diff_excerpt`` was explicitly enabled in config."""

    version_id: str
    intent: str | None
    context_status: str = "COMPLETE"
    analysis_confidence: str = "FULL"
    redacted_fields: list[str] = Field(default_factory=list)
    feature: str | None
    agent: str | None
    model: str | None
    status: str
    is_adverse: bool
    files_changed: int
    lines_added: int
    lines_removed: int
    changed_paths: list[str] = Field(default_factory=list)
    test_summary: str | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    metric_deltas: list[MetricDelta] = Field(default_factory=list)
    regressions: list[str] = Field(default_factory=list)
    previous_attempts: list[AttemptRef] = Field(default_factory=list)
    impact_hotspots: list[ImpactRef] = Field(default_factory=list)
    diff_excerpt: str | None = None


class AnalysisProvider(abc.ABC):
    """One way to turn an :class:`AnalysisInput` into an :class:`Analysis`."""

    #: stable identifier, also stored on the Analysis row
    name: str = "base"

    @abc.abstractmethod
    def analyze(self, data: AnalysisInput) -> Analysis | None:
        """Return an Analysis, or ``None`` to fall through to the next provider."""


def fact_guard(analysis: Analysis, data: AnalysisInput, *, provider: str) -> Analysis:
    """Sanitize a provider's Analysis so it cannot misrepresent the facts.

    - ``provider`` / ``model`` are set by us, never by the model.
    - ``risk`` is clamped to low|medium|high and can never sit *below* what the
      recorded status implies (an adverse version is at least ``medium``).
    - all free text is secret-scrubbed and length-capped.
    """
    risk = (analysis.risk or "").strip().lower()
    if risk not in _RISK_LEVELS:
        risk = "medium" if data.is_adverse else "low"

    warnings = [redact_secrets(w)[:_MAX_FIELD] for w in analysis.warnings if w.strip()]
    if data.is_adverse and risk == "low":
        risk = "medium"
        warnings.append(
            "Risk raised to 'medium': this version is recorded as "
            f"{data.status} with {len(data.regressions)} regression(s)."
        )

    return analysis.model_copy(
        update={
            "summary": redact_secrets(analysis.summary)[:_MAX_SUMMARY],
            "reasoning": _clip(analysis.reasoning),
            "recommendation": _clip(analysis.recommendation),
            "warnings": warnings,
            "risk": risk,
            "provider": provider,
            "model": analysis.model,
        }
    )


def _clip(text: str | None) -> str | None:
    if not text or not text.strip():
        return None
    return redact_secrets(text)[:_MAX_FIELD]


__all__ = [
    "AnalysisInput",
    "AnalysisProvider",
    "AttemptRef",
    "ImpactRef",
    "MetricDelta",
    "fact_guard",
]
