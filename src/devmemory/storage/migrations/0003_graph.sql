-- Phase 12: change-impact analysis from the Entire `graph` plugin.
-- One row per version. `payload` is the full GraphImpact JSON; the summary
-- columns are denormalized for cheap listing. Local-only telemetry - never
-- published to Databricks.

CREATE TABLE graph_impacts (
    version_id      TEXT PRIMARY KEY REFERENCES versions(version_id) ON DELETE CASCADE,
    base_commit     TEXT NOT NULL DEFAULT '',
    head_commit     TEXT NOT NULL DEFAULT '',
    entity_count    INTEGER NOT NULL DEFAULT 0,
    max_dependents  INTEGER NOT NULL DEFAULT 0,
    generated_at    TEXT NOT NULL,
    payload         TEXT NOT NULL
);
