"""The deterministic provider. Never calls out, never fails - the guaranteed
tail of every fallback chain."""

from __future__ import annotations

from datetime import UTC, datetime

from devmemory.analysis.base import AnalysisInput, AnalysisProvider
from devmemory.domain.models import Analysis


class RulesProvider(AnalysisProvider):
    name = "rules"

    def analyze(self, data: AnalysisInput) -> Analysis:
        summary = _summary(data)
        warnings = _warnings(data)
        return Analysis(
            version_id=data.version_id,
            summary=summary,
            reasoning=_reasoning(data),
            recommendation=_recommendation(data),
            warnings=warnings,
            risk=_risk(data),
            provider=self.name,
            model=None,
            generated_at=datetime.now(UTC),
        )


def _summary(d: AnalysisInput) -> str:
    if d.intent:
        what = d.intent
    elif d.context_status == "PARTIAL":
        what = f"a {d.files_changed}-file change (prompt context unavailable/redacted)"
    elif d.context_status == "MISSING":
        what = f"a {d.files_changed}-file change (no checkpoint context)"
    else:
        what = f"a {d.files_changed}-file change"

    scope = f"{d.files_changed} file(s), +{d.lines_added}/-{d.lines_removed}"
    if d.status == "REGRESSION" or d.regressions:
        return f"{what} - regressed ({'; '.join(d.regressions) or 'status set to REGRESSION'}). {scope}."
    if d.status == "SUCCESS":
        gain = next((m for m in d.metric_deltas if m.improved), None)
        tail = f" {gain.name} {gain.before:g} -> {gain.after:g}." if gain else ""
        return f"{what} - landed successfully. {scope}.{tail}"
    if d.tests_failed:
        return f"{what} - {d.tests_failed} test(s) failing. {scope}."
    return f"{what}. {scope}. Status: {d.status}."


def _reasoning(d: AnalysisInput) -> str | None:
    bits: list[str] = []
    if d.context_status in ("PARTIAL", "MISSING"):
        bits.append(f"Prompt context is {d.context_status.lower()}; reasoning from code evidence only")
    for m in d.metric_deltas:
        if m.before is not None and m.after is not None and m.before != m.after:
            move = "improved" if m.improved else "worsened" if m.worsened else "changed"
            bits.append(f"{m.name} {move} ({m.before:g} -> {m.after:g})")
    if d.previous_attempts:
        adverse = [a for a in d.previous_attempts if a.status in ("REGRESSION", "ERROR")]
        if adverse:
            bits.append(
                f"{len(adverse)} earlier attempt(s) in this area went wrong "
                f"({', '.join(a.version_id.upper() for a in adverse)})"
            )
    if d.impact_hotspots:
        top = d.impact_hotspots[0]
        bits.append(f"{top.change_type} on {top.entity} affects {top.dependents} dependent(s)")
    return "; ".join(bits) or None


def _recommendation(d: AnalysisInput) -> str | None:
    if d.status == "REGRESSION" or d.regressions:
        return "Revert or fix the cause before building on this - it regressed here."
    if d.status == "ERROR":
        return "This attempt errored; review the follow-up fix before retrying the approach."
    risky = [h for h in d.impact_hotspots if h.change_type in ("removed", "signature_changed")]
    if risky:
        return (
            f"{risky[0].change_type} on {risky[0].entity} has "
            f"{risky[0].dependents} dependents - check every caller."
        )
    if any(a.status in ("REGRESSION", "ERROR") for a in d.previous_attempts):
        return "A similar change failed before - compare against that version first."
    if d.status == "SUCCESS":
        return "Safe to build on."
    return None


def _warnings(d: AnalysisInput) -> list[str]:
    out: list[str] = []
    if d.context_status in ("PARTIAL", "MISSING"):
        out.append(
            f"Context completeness is {d.context_status}: developer prompt context was unavailable or redacted. "
            "Analysis is based strictly on observable code changes, tests, and metrics."
        )
    for a in d.previous_attempts:
        if a.status in ("REGRESSION", "ERROR"):
            out.append(f"{a.version_id.upper()} [{a.status}]: {a.result}")
    for h in d.impact_hotspots:
        if h.change_type in ("removed", "signature_changed") and h.dependents > 0:
            out.append(f"{h.change_type} {h.entity}: {h.dependents} dependent(s)")
    return out


def _risk(d: AnalysisInput) -> str:
    if d.status in ("REGRESSION", "ERROR") or d.regressions:
        return "high"
    if d.tests_failed:
        return "high"
    if any(a.status in ("REGRESSION", "ERROR") for a in d.previous_attempts):
        return "medium"
    if any(
        h.change_type in ("removed", "signature_changed") and h.dependents > 2
        for h in d.impact_hotspots
    ):
        return "medium"
    if any(m.worsened for m in d.metric_deltas):
        return "medium"
    return "low"


__all__ = ["RulesProvider"]
