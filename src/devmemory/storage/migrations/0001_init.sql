-- 0001_init: the project record.
--
-- One row per repository DevMemory tracks. The rich schema (versions,
-- changed_files, tests, metrics, features, regressions, entire_checkpoints,
-- analysis, artifacts, FTS) arrives in a later migration alongside the
-- persistence layer that fills it.

CREATE TABLE projects (
    project_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    repo_path           TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    current_version_id  INTEGER
);
