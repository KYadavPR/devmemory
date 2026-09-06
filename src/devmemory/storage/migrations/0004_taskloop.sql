-- 0004_taskloop: the state-aware coding loop.
--
-- A task is a live, multi-commit unit of work with an explicit requirement list.
-- Every refresh_state appends one immutable row to state_snapshots, so the loop
-- is observable as snapshot #1 -> #2 -> #3. Nothing here stores application code
-- or full transcripts.

CREATE TABLE tasks (
    id            TEXT PRIMARY KEY,               -- "TASK-001"
    goal          TEXT NOT NULL,                  -- the human task, verbatim
    status        TEXT NOT NULL DEFAULT 'IN_PROGRESS',
    branch        TEXT NOT NULL DEFAULT 'main',
    base_commit   TEXT,                           -- HEAD when the task was created
    test_command  TEXT,
    push_policy   TEXT NOT NULL DEFAULT 'manual',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE requirements (
    task_id       TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    req_id        TEXT NOT NULL,                  -- "R1"
    description   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'INCOMPLETE',
    reason        TEXT NOT NULL DEFAULT '',
    evidence_json TEXT NOT NULL DEFAULT '[]',
    evaluated_at  TEXT,
    evaluated_by  TEXT NOT NULL DEFAULT '',
    position      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id, req_id)
);

CREATE TABLE issues (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    description   TEXT NOT NULL,
    kind          TEXT NOT NULL DEFAULT 'agent',   -- agent | test | requirement | engine
    blocking      INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'OPEN',    -- OPEN | RESOLVED
    created_at    TEXT NOT NULL,
    resolved_at   TEXT
);

CREATE INDEX idx_issues_task ON issues(task_id, status);

CREATE TABLE task_test_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id          TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    command          TEXT NOT NULL,
    status           TEXT NOT NULL,               -- NOT_RUN | PASSED | FAILED | FAILED_TO_PARSE | ERROR
    passed           INTEGER NOT NULL DEFAULT 0,
    failed           INTEGER NOT NULL DEFAULT 0,
    skipped          INTEGER NOT NULL DEFAULT 0,
    exit_code        INTEGER,
    duration_seconds REAL,
    output_path      TEXT,
    created_at       TEXT NOT NULL
);

CREATE INDEX idx_test_runs_task ON task_test_runs(task_id, created_at);

-- The most important table: one immutable snapshot per refresh_state.
CREATE TABLE state_snapshots (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id        TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    overall_status TEXT NOT NULL,
    commit_sha     TEXT,
    checkpoint_id  TEXT,
    state_json     TEXT NOT NULL,                 -- the full NormalizedState
    created_at     TEXT NOT NULL
);

CREATE INDEX idx_snapshots_task ON state_snapshots(task_id, created_at);

-- Optional: link versions produced under a task (the existing versions table is
-- untouched; this is a side index).
CREATE TABLE task_commits (
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    commit_sha  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (task_id, commit_sha)
);
