"""LLM-backed analysis providers (Anthropic / OpenAI / Gemini).

One class, three back ends, selected by name. Each call sends only the normalized
:class:`AnalysisInput` (plus a diff excerpt *iff* explicitly enabled in config) -
never raw source, never a transcript. The API key comes from the environment.
Any failure returns ``None`` so the fallback chain moves on; ``rules`` is always
the tail.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from devmemory.analysis.base import AnalysisInput, AnalysisProvider
from devmemory.config import resolve_llm_api_key
from devmemory.domain.models import Analysis
from devmemory.logging import get_logger

_log = get_logger(__name__)

_DEFAULT_MODEL = {
    "anthropic": "claude-opus-5",
    "openai": "gpt-5",
    "gemini": "gemini-2.5-pro",
}

_SYSTEM = (
    "You are a senior engineer reviewing one AI-assisted change. You are given "
    "NORMALIZED FACTS (Git stats, test results, metric deltas, regressions, prior "
    "attempts, change-impact). Treat every number as exact and correct - never "
    "hedge it, never restate it as approximate, never contradict it. Your job is "
    "interpretation only.\n\n"
    "Reply with ONLY a JSON object, no prose around it:\n"
    '{"summary": str (<= 3 sentences), "reasoning": str|null, '
    '"recommendation": str|null, "warnings": [str], '
    '"risk": "low"|"medium"|"high"}\n'
    "If the facts show a regression or failing tests, risk is 'high'."
)


class LLMProvider(AnalysisProvider):
    def __init__(self, provider: str, model: str | None = None) -> None:
        self.name = provider.lower()
        self._model = model or _DEFAULT_MODEL.get(self.name)

    def analyze(self, data: AnalysisInput) -> Analysis | None:
        key = resolve_llm_api_key(self.name)
        if not key or self._model is None:
            return None
        prompt = _prompt(data)
        try:
            if self.name == "anthropic":
                raw = _call_anthropic(key, self._model, prompt)
            elif self.name == "openai":
                raw = _call_openai(key, self._model, prompt)
            elif self.name == "gemini":
                raw = _call_gemini(key, self._model, prompt)
            else:
                return None
        except Exception as exc:
            _log.warning("analysis.llm_failed", provider=self.name, error=str(exc))
            return None

        parsed = _parse(raw)
        if parsed is None:
            _log.warning("analysis.llm_unparseable", provider=self.name)
            return None
        return Analysis(
            version_id=data.version_id,
            summary=str(parsed.get("summary", "")).strip(),
            reasoning=_opt(parsed.get("reasoning")),
            recommendation=_opt(parsed.get("recommendation")),
            warnings=[str(w) for w in parsed.get("warnings", []) if str(w).strip()],
            risk=_opt(parsed.get("risk")),
            provider=self.name,
            model=self._model,
            generated_at=datetime.now(UTC),
        )


# --- prompt -------------------------------------------------------------------


def _prompt(d: AnalysisInput) -> str:
    facts: dict[str, Any] = {
        "intent": d.intent,
        "feature": d.feature,
        "agent": d.agent,
        "status": d.status,
        "is_adverse": d.is_adverse,
        "files_changed": d.files_changed,
        "lines_added": d.lines_added,
        "lines_removed": d.lines_removed,
        "changed_paths": d.changed_paths[:30],
        "tests": d.test_summary,
        "metric_deltas": [m.model_dump() for m in d.metric_deltas],
        "regressions": d.regressions,
        "previous_attempts": [a.model_dump() for a in d.previous_attempts],
        "impact_hotspots": [h.model_dump() for h in d.impact_hotspots],
    }
    text = "NORMALIZED FACTS:\n" + json.dumps(facts, indent=2, default=str)
    if d.diff_excerpt:
        text += f"\n\nDIFF EXCERPT (truncated):\n{d.diff_excerpt}"
    return text


def _parse(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].removeprefix("json").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _opt(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


# --- back ends (lazy SDK imports) -------------------------------------------


def _call_anthropic(key: str, model: str, prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=model,
        max_tokens=1500,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low"},
    )
    return "".join(b.text for b in message.content if b.type == "text")


def _call_openai(key: str, model: str, prompt: str) -> str:
    import openai

    client = openai.OpenAI(api_key=key)
    resp = client.responses.create(
        model=model,
        instructions=_SYSTEM,
        input=prompt,
    )
    return resp.output_text or ""


def _call_gemini(key: str, model: str, prompt: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=_SYSTEM),
    )
    return resp.text or ""


def call_llm(
    prompt: str, *, system: str, providers: list[str], model: str | None = None
) -> str | None:
    """Try each provider in order; return the first non-empty completion, or None.

    Used by callers outside the analysis chain (e.g. the task-loop requirement
    evaluator). Keys come from the environment; any error falls through.
    """
    for raw_name in providers:
        name = raw_name.strip().lower()
        if name not in ("anthropic", "openai", "gemini"):
            continue
        key = resolve_llm_api_key(name)
        chosen = model or _DEFAULT_MODEL.get(name)
        if not key or chosen is None:
            continue
        try:
            if name == "anthropic":
                text = _call_anthropic_with_system(key, chosen, prompt, system)
            elif name == "openai":
                text = _call_openai_with_system(key, chosen, prompt, system)
            else:
                text = _call_gemini_with_system(key, chosen, prompt, system)
        except Exception as exc:
            _log.warning("llm.call_failed", provider=name, error=str(exc))
            continue
        if text and text.strip():
            return text
    return None


def _call_anthropic_with_system(key: str, model: str, prompt: str, system: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=key)
    message = client.messages.create(
        model=model,
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low"},
    )
    return "".join(b.text for b in message.content if b.type == "text")


def _call_openai_with_system(key: str, model: str, prompt: str, system: str) -> str:
    import openai

    client = openai.OpenAI(api_key=key)
    resp = client.responses.create(model=model, instructions=system, input=prompt)
    return resp.output_text or ""


def _call_gemini_with_system(key: str, model: str, prompt: str, system: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key)
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=system),
    )
    return resp.text or ""


__all__ = ["LLMProvider", "call_llm"]
