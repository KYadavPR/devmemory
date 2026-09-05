"""Per-run structured log for ``devmemory checkpoint``.

Answers, after the fact: what ran, what each stage did, what failed, which
integration caused it, and whether project state changed. Written to
``.devmemory/runs/<run_id>.json``.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from devmemory.logging import get_logger

_log = get_logger(__name__)


class StageRecord(BaseModel):
    name: str
    status: str = "ok"  # ok | skipped | degraded | failed
    started_at: str
    duration_ms: float = 0.0
    detail: str | None = None
    data: dict[str, object] = Field(default_factory=dict)


class RunLog(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    command: str = "checkpoint"
    started_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    outcome: str = "running"  # running | success | error
    project_state_changed: bool = False
    version_id: str | None = None
    stages: list[StageRecord] = Field(default_factory=list)
    error: str | None = None

    @contextmanager
    def stage(self, name: str) -> Iterator[StageRecord]:
        record = StageRecord(name=name, started_at=datetime.now(UTC).isoformat())
        start = time.perf_counter()
        self.stages.append(record)
        try:
            yield record
        except Exception as exc:
            record.status = "failed"
            record.detail = f"{type(exc).__name__}: {exc}"
            record.duration_ms = round((time.perf_counter() - start) * 1000, 1)
            raise
        else:
            record.duration_ms = round((time.perf_counter() - start) * 1000, 1)
            _log.debug("pipeline.stage", stage=name, status=record.status, ms=record.duration_ms)

    def finish(self, *, outcome: str, error: str | None = None) -> None:
        self.outcome = outcome
        self.error = error
        self.finished_at = datetime.now(UTC).isoformat()

    def write(self, runs_dir: Path) -> Path:
        runs_dir.mkdir(parents=True, exist_ok=True)
        path = runs_dir / f"{self.run_id}.json"
        path.write_text(json.dumps(self.model_dump(), indent=2), encoding="utf-8")
        return path


__all__ = ["RunLog", "StageRecord"]
