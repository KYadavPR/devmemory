"""Metrics adapter: collect arbitrary project metrics for a version.

Metrics come from a JSON file the project writes, or the JSON stdout of a
command. Two shapes are accepted per metric:

    {"accuracy": 93.4}                       -> after only
    {"accuracy": {"before": 89.2, "after": 93.4, "unit": "%"}}

The previous version's ``after`` fills any missing ``before`` (done by the
pipeline, not here). Direction comes from config, then a name heuristic.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from devmemory.domain.enums import MetricDirection
from devmemory.domain.errors import CollectionError
from devmemory.domain.models import Metric
from devmemory.logging import get_logger

_log = get_logger(__name__)

_LOWER_IS_BETTER = (
    "latency",
    "duration",
    "time_ms",
    "response_time",
    "loss",
    "val_loss",
    "train_loss",
    "error_rate",
    "errors",
    "failures",
    "cost",
    "memory",
    "mem_mb",
    "p50",
    "p90",
    "p95",
    "p99",
    "size_bytes",
    "bundle_size",
)


class MetricsAdapter:
    def __init__(self, repo_path: Path | str) -> None:
        self._cwd = Path(repo_path).resolve()

    def collect(
        self,
        *,
        file: str | None = None,
        command: str | None = None,
        directions: dict[str, MetricDirection] | None = None,
    ) -> list[Metric]:
        raw = self._load(file=file, command=command)
        if not raw:
            return []
        directions = directions or {}
        metrics: list[Metric] = []
        for name, value in raw.items():
            metric = _to_metric(str(name), value)
            if metric is None:
                continue
            metric.direction = directions.get(metric.name, guess_direction(metric.name))
            metrics.append(metric)
        _log.info("metrics.collected", count=len(metrics), names=[m.name for m in metrics])
        return metrics

    def _load(self, *, file: str | None, command: str | None) -> dict[str, object]:
        if file:
            path = (self._cwd / file).resolve()
            if not path.is_file():
                raise CollectionError(f"metrics file not found: {path}")
            return _as_dict(path.read_text(encoding="utf-8"), source=str(path))
        if command:
            try:
                proc = subprocess.run(  # noqa: S602 - user-configured command
                    command,
                    cwd=self._cwd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise CollectionError(f"metrics command failed: {command}: {exc}") from exc
            if proc.returncode != 0:
                raise CollectionError(
                    f"metrics command exited {proc.returncode}: {proc.stderr.strip()[:200]}"
                )
            return _as_dict(proc.stdout, source=f"`{command}`")
        return {}


def guess_direction(name: str) -> MetricDirection:
    lowered = name.lower().replace("-", "_")
    if any(hint in lowered for hint in _LOWER_IS_BETTER):
        return MetricDirection.LOWER_IS_BETTER
    return MetricDirection.HIGHER_IS_BETTER


def _as_dict(text: str, *, source: str) -> dict[str, object]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CollectionError(f"metrics from {source} are not valid JSON: {exc}") from exc
    if isinstance(data, dict) and "metrics" in data and isinstance(data["metrics"], dict):
        data = data["metrics"]
    if not isinstance(data, dict):
        raise CollectionError(f"metrics from {source} must be a JSON object")
    return data


def _to_metric(name: str, value: object) -> Metric | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Metric(name=name, after=float(value))
    if isinstance(value, dict):
        after = _num(value.get("after")) or _num(value.get("value"))
        before = _num(value.get("before"))
        if after is None and before is None:
            return None
        return Metric(
            name=name,
            before=before,
            after=after,
            unit=str(value["unit"]) if value.get("unit") is not None else None,
            metadata={
                k: v for k, v in value.items() if k not in ("before", "after", "value", "unit")
            },
        )
    return None


def _num(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


__all__ = ["MetricsAdapter", "guess_direction"]
