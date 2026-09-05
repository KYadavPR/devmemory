-- 0002_versions: the development-version record and everything hanging off it.
--
-- Facts (git, entire, tests, metrics) and AI analysis are kept in separate
-- tables. A version can reference more than one Entire checkpoint.

CREATE TABLE versions (
    version_number   INTEGER NOT NULL,
    version_id       TEXT PRIMARY KEY,              -- "v7"
    project_id       TEXT NOT NULL,

    intent           TEXT,
    agent            TEXT,
    model            TEXT,

    git_commit       TEXT NOT NULL,
    parent_commit    TEXT,
    branch           TEXT,

    feature_id       TEXT,
    status           TEXT NOT NULL,

    files_changed    INTEGER NOT NULL DEFAULT 0,
    lines_added      INTEGER NOT NULL DEFAULT 0,
    lines_removed    INTEGER NOT NULL DEFAULT 0,

    entire_association_method     TEXT,
    entire_association_confidence REAL,

    environment_json TEXT,
    source_event_json TEXT,
    run_id           TEXT,

    created_at       TEXT NOT NULL,                 -- when DevMemory recorded it
    committed_at     TEXT,                          -- the git commit's own time

    UNIQUE (project_id, version_number),
    UNIQUE (project_id, git_commit),
    FOREIGN KEY (project_id) REFERENCES projects(project_id),
    FOREIGN KEY (feature_id) REFERENCES features(feature_id)
);

CREATE TABLE entire_checkpoints (
    checkpoint_id          TEXT PRIMARY KEY,
    project_id             TEXT NOT NULL,
    ref                    TEXT,
    agent                  TEXT,
    model                  TEXT,
    intent                 TEXT,
    strategy               TEXT,
    created_at             TEXT,
    git_commit             TEXT,
    association_method     TEXT,
    association_confidence REAL,
    tokens_json            TEXT,
    imported               INTEGER NOT NULL DEFAULT 0,
    sessions_json          TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE version_checkpoints (
    version_id    TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    is_primary    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (version_id, checkpoint_id),
    FOREIGN KEY (version_id) REFERENCES versions(version_id) ON DELETE CASCADE,
    FOREIGN KEY (checkpoint_id) REFERENCES entire_checkpoints(checkpoint_id)
);

CREATE TABLE changed_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id    TEXT NOT NULL,
    path          TEXT NOT NULL,
    old_path      TEXT,
    change_type   TEXT NOT NULL,
    additions     INTEGER NOT NULL DEFAULT 0,
    deletions     INTEGER NOT NULL DEFAULT 0,
    binary        INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (version_id) REFERENCES versions(version_id) ON DELETE CASCADE
);

CREATE TABLE features (
    feature_id   TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL,
    name         TEXT NOT NULL,
    status       TEXT NOT NULL,
    derived_from TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    UNIQUE (project_id, name),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE TABLE tests (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id       TEXT NOT NULL,
    command          TEXT,
    framework        TEXT,
    total            INTEGER NOT NULL DEFAULT 0,
    passed           INTEGER NOT NULL DEFAULT 0,
    failed           INTEGER NOT NULL DEFAULT 0,
    skipped          INTEGER NOT NULL DEFAULT 0,
    errors           INTEGER NOT NULL DEFAULT 0,
    exit_code        INTEGER,
    duration_seconds REAL,
    failing_json     TEXT,
    output           TEXT,
    collected_at     TEXT,
    FOREIGN KEY (version_id) REFERENCES versions(version_id) ON DELETE CASCADE
);

CREATE TABLE metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id    TEXT NOT NULL,
    name          TEXT NOT NULL,
    before_value  REAL,
    after_value   REAL,
    unit          TEXT,
    direction     TEXT,
    metadata_json TEXT,
    FOREIGN KEY (version_id) REFERENCES versions(version_id) ON DELETE CASCADE
);

CREATE TABLE regressions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id     TEXT NOT NULL,
    kind           TEXT NOT NULL,          -- 'metric' | 'test'
    metric         TEXT,
    before_value   REAL,
    after_value    REAL,
    change_percent REAL,
    severity       TEXT NOT NULL,          -- 'LOW' | 'MEDIUM' | 'HIGH'
    detail         TEXT,
    FOREIGN KEY (version_id) REFERENCES versions(version_id) ON DELETE CASCADE
);

CREATE TABLE analysis (
    version_id     TEXT PRIMARY KEY,
    summary        TEXT,
    reasoning      TEXT,
    recommendation TEXT,
    warnings_json  TEXT,
    risk           TEXT,
    provider       TEXT NOT NULL,          -- 'rules' | 'anthropic' | ...
    model          TEXT,
    generated_at   TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES versions(version_id) ON DELETE CASCADE
);

CREATE TABLE artifacts (
    artifact_id  TEXT PRIMARY KEY,
    version_id   TEXT NOT NULL,
    path         TEXT NOT NULL,
    type         TEXT NOT NULL,
    size_bytes   INTEGER,
    sha256       TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (version_id) REFERENCES versions(version_id) ON DELETE CASCADE
);

CREATE TABLE doc_flags (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id TEXT NOT NULL,
    doc_path   TEXT NOT NULL,
    reason     TEXT,
    FOREIGN KEY (version_id) REFERENCES versions(version_id) ON DELETE CASCADE
);

CREATE TABLE events (
    event_id     TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL,
    version_id   TEXT,
    type         TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT 'devmemory',
    payload_json TEXT,
    created_at   TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);

CREATE INDEX idx_versions_project        ON versions(project_id, version_number);
CREATE INDEX idx_versions_git_commit     ON versions(git_commit);
CREATE INDEX idx_versions_feature        ON versions(feature_id);
CREATE INDEX idx_versions_status         ON versions(status);
CREATE INDEX idx_changed_files_version   ON changed_files(version_id);
CREATE INDEX idx_changed_files_path      ON changed_files(path);
CREATE INDEX idx_metrics_version         ON metrics(version_id);
CREATE INDEX idx_metrics_name            ON metrics(name);
CREATE INDEX idx_tests_version           ON tests(version_id);
CREATE INDEX idx_regressions_version     ON regressions(version_id);
CREATE INDEX idx_checkpoints_project     ON entire_checkpoints(project_id);
CREATE INDEX idx_checkpoints_commit      ON entire_checkpoints(git_commit);
CREATE INDEX idx_version_checkpoints_cp  ON version_checkpoints(checkpoint_id);
CREATE INDEX idx_events_version          ON events(version_id);

-- Full-text search over normalized version metadata. Plain (not external-content)
-- FTS5 - the version repository keeps it in sync explicitly on write/delete.
CREATE VIRTUAL TABLE version_search USING fts5 (
    version_id UNINDEXED,
    intent,
    feature,
    agent,
    model,
    status,
    files,
    commit_sha,
    checkpoint_id,
    analysis,
    recommendation,
    errors,
    tokenize = 'unicode61 remove_diacritics 2'
);
