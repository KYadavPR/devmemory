-- 0005_project_brief: the project's single source of truth.
--
-- One editable document (specs, constraints, decisions, conventions) the human
-- uploads or pastes. It is fed into requirement normalization and the prompt
-- suggestions so the loop stays anchored to what the project is actually for.
-- One row, id = 1.

CREATE TABLE project_brief (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    content     TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);
