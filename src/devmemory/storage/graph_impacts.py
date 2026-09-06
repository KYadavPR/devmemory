"""Persistence for graph change-impact results (Phase 12).

Kept out of the main version transaction: impact analysis is optional, slow, and
often backfilled after the fact.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from devmemory.adapters.graph import GraphImpact
from devmemory.storage.db import Database


class GraphImpactRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def set(self, version_id: str, impact: GraphImpact) -> None:
        generated = impact.generated_at or datetime.now(UTC).isoformat()
        stored = impact.model_copy(update={"version_id": version_id, "generated_at": generated})
        self._db.execute(
            """
            INSERT INTO graph_impacts
                (version_id, base_commit, head_commit, entity_count, max_dependents,
                 generated_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(version_id) DO UPDATE SET
                base_commit    = excluded.base_commit,
                head_commit    = excluded.head_commit,
                entity_count   = excluded.entity_count,
                max_dependents = excluded.max_dependents,
                generated_at   = excluded.generated_at,
                payload        = excluded.payload
            """,
            (
                version_id,
                stored.base_commit,
                stored.head_commit,
                stored.entity_count,
                stored.max_dependents,
                generated,
                stored.model_dump_json(),
            ),
        )

    def get(self, version_id: str) -> GraphImpact | None:
        row = self._db.query_one(
            "SELECT payload FROM graph_impacts WHERE version_id = ?", (version_id,)
        )
        if row is None:
            return None
        try:
            return GraphImpact.model_validate(json.loads(row["payload"]))
        except (json.JSONDecodeError, ValueError):
            return None

    def delete(self, version_id: str) -> None:
        self._db.execute("DELETE FROM graph_impacts WHERE version_id = ?", (version_id,))


__all__ = ["GraphImpactRepository"]
