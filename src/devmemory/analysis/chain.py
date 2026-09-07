"""The provider fallback chain.

Try each configured provider in order; the first that returns an Analysis wins,
after passing through :func:`fact_guard`. ``rules`` is always appended as the
guaranteed tail, so :func:`run_analysis` never raises and never returns ``None``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from devmemory.analysis.base import AnalysisInput, AnalysisProvider, fact_guard
from devmemory.analysis.llm import LLMProvider
from devmemory.analysis.rules import RulesProvider
from devmemory.domain.models import Analysis
from devmemory.logging import get_logger

if TYPE_CHECKING:
    from devmemory.config import LocalModelSettings

_log = get_logger(__name__)

_LLM_PROVIDERS = {"anthropic", "openai", "gemini", "openrouter", "local"}


def build_providers(
    names: list[str],
    *,
    model: str | None = None,
    local_model: LocalModelSettings | None = None,
) -> list[AnalysisProvider]:
    providers: list[AnalysisProvider] = []
    seen: set[str] = set()
    for raw in names:
        name = raw.strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        if name == "rules":
            providers.append(RulesProvider())
        elif name == "local":
            providers.append(LLMProvider(name, model, local_model=local_model))
        elif name in _LLM_PROVIDERS:
            providers.append(LLMProvider(name, model))
        else:
            _log.warning("analysis.unknown_provider", provider=name)
    if not any(isinstance(p, RulesProvider) for p in providers):
        providers.append(RulesProvider())  # guaranteed tail
    return providers


def run_analysis(data: AnalysisInput, providers: list[AnalysisProvider]) -> Analysis:
    for provider in providers:
        try:
            result = provider.analyze(data)
        except Exception as exc:
            _log.warning("analysis.provider_error", provider=provider.name, error=str(exc))
            continue
        if result is not None:
            return fact_guard(result, data, provider=provider.name)
    # build_providers guarantees a RulesProvider tail, so this is unreachable
    return fact_guard(RulesProvider().analyze(data), data, provider="rules")


__all__ = ["build_providers", "run_analysis"]
