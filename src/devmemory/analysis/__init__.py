"""AI analysis layer.

Analysis is *interpretation*, stored separately from facts and never able to
overwrite them. Providers are tried in a fallback chain; ``rules`` (deterministic,
offline) is always the tail.
"""

from __future__ import annotations

from devmemory.analysis.base import AnalysisInput, AnalysisProvider, fact_guard
from devmemory.analysis.chain import build_providers, run_analysis

__all__ = [
    "AnalysisInput",
    "AnalysisProvider",
    "build_providers",
    "fact_guard",
    "run_analysis",
]
