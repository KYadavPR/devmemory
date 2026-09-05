# DevMemory — Data & API Specification

## 1. Purpose

This document defines the data structures, local database model, external analytics schema, REST API, and AI/MCP interface for DevMemory.

The goal is to create one normalized representation of a development change that connects:

```text
Intent
   ↓
AI Agent
   ↓
Entire Checkpoint
   ↓
Git Commit
   ↓
Git Diff
   ↓
Tests
   ↓
Metrics
   ↓
Development Version
   ↓
Analysis
   ↓
Project Memory
````

DevMemory should use existing systems as sources of truth rather than duplicating their responsibilities.

---

# 2. Source-of-Truth Model

| Information              | Source of Truth           |
| ------------------------ | ------------------------- |
| Source code              | Git                       |
| Git history              | Git                       |
| Git diff                 | Git                       |
| AI development context   | Entire                    |
| Entire Checkpoint        | Entire                    |
| Local DevMemory metadata | SQLite                    |
| Development versions     | DevMemory                 |
| Feature history          | DevMemory                 |
| Test results             | DevMemory                 |
| Development metrics      | DevMemory                 |
| Project memory           | DevMemory                 |
| Analytics                | Databricks                |
| Artifacts/snapshots      | Filesystem/object storage |
| AI context interface     | DevMemory API/MCP         |

DevMemory should store references to external sources wherever possible.

---

# 3. Core Entity Relationship

The main relationship is:

```text
Project
   │
   ├── Features
   │
   └── Development Versions
           │
           ├── Entire Checkpoints
           │
           ├── Git Commit
           │
           ├── Changed Files
           │
           ├── Tests
           │
           ├── Metrics
           │
           ├── Artifacts
           │
           └── Analysis
```

A development version represents a meaningful development event.

It is not simply a Git commit.

---

# 4. Project

A project represents one repository being tracked by DevMemory.

Example:

```json
{
  "project_id": "visionai",
  "name": "VisionAI",
  "repository_path": "/projects/visionai",
  "created_at": "2026-09-06T01:00:00Z",
  "current_version_id": "v7"
}
```

Fields:

```text
project_id
name
repository_path
created_at
updated_at
current_version_id
```

---

# 5. DevelopmentVersion

This is the central entity.

Example:

```json
{
  "version_id": "v7",
  "project_id": "visionai",

  "intent": "Improve image classification accuracy",

  "agent": "Claude Code",

  "entire_checkpoint_id": "checkpoint-abc123",

  "git_commit": "7fa91c",
  "parent_commit": "91ac21",

  "feature_id": "image-classification",

  "status": "SUCCESS",

  "tests_passed": 143,
  "tests_failed": 5,

  "metrics": {
    "accuracy": {
      "before": 89.2,
      "after": 93.4
    }
  },

  "lines_added": 142,
  "lines_removed": 37,

  "created_at": "2026-09-06T01:20:00Z"
}
```

Required fields:

```text
version_id
project_id
git_commit
created_at
status
```

Recommended fields:

```text
intent
agent
parent_commit
entire_checkpoint_id
feature_id
tests
metrics
analysis
artifact
```

---

# 6. Version Status

Supported statuses:

```text
SUCCESS
PARTIAL_SUCCESS
ERROR
REGRESSION
IN_PROGRESS
NEEDS_REVIEW
```

Status should represent the development result rather than merely whether the Git commit exists.

Example:

```text
Git commit exists
+
Tests fail
+
Performance worsened
=
REGRESSION
```

---

# 7. EntireCheckpoint

DevMemory should store a lightweight representation of an Entire checkpoint.

Example:

```json
{
  "checkpoint_id": "checkpoint-abc123",
  "location": "entire://checkpoint/abc123",
  "agent": "Claude Code",
  "intent": "Improve image classification accuracy",
  "timestamp": "2026-09-06T01:15:00Z",
  "git_commit": "7fa91c",
  "association_method": "explicit",
  "association_confidence": 1.0
}
```

Fields:

```text
checkpoint_id
location
agent
intent
timestamp
git_commit
association_method
association_confidence
metadata
```

Do not duplicate the complete Entire checkpoint.

---

# 8. GitReference

Git data should be represented as references.

Example:

```json
{
  "commit": "7fa91c",
  "parent_commit": "91ac21",
  "branch": "main"
}
```

Git should be queried whenever the exact diff or history is required.

DevMemory does not become a second Git implementation.

---

# 9. ChangedFile

A version can contain multiple changed files.

Example:

```json
{
  "path": "model.py",
  "change_type": "modified",
  "lines_added": 80,
  "lines_removed": 22
}
```

Supported change types:

```text
added
modified
deleted
renamed
```

Fields:

```text
version_id
path
change_type
old_path
lines_added
lines_removed
```

---

# 10. Git Diff

The exact Git diff should be generated from Git.

Example:

```diff
- learning_rate = 0.001
+ learning_rate = 0.0001

+ scheduler = ReduceLROnPlateau(...)
```

The MVP may store the diff for convenient display.

However, Git remains the source of truth.

The system should also be able to reconstruct:

```bash
git diff <parent_commit> <commit>
```

---

# 11. Feature

Features represent logical parts of the project.

Example:

```json
{
  "feature_id": "image-classification",
  "project_id": "visionai",
  "name": "Image Classification",
  "status": "COMPLETE"
}
```

Supported feature statuses:

```text
COMPLETE
PARTIAL
IN_PROGRESS
FAILED
NOT_STARTED
```

A feature can have many development versions.

Example:

```text
Image Classification

V3 → SUCCESS
V4 → SUCCESS
V5 → REGRESSION
V6 → SUCCESS
V7 → SUCCESS
```

---

# 12. TestResult

Tests are associated with a development version.

Example:

```json
{
  "version_id": "v7",
  "total": 148,
  "passed": 143,
  "failed": 5,
  "skipped": 0,
  "duration_seconds": 42.7,
  "command": "pytest"
}
```

Fields:

```text
version_id
total
passed
failed
skipped
duration_seconds
command
output
```

The MVP should support command-based test collection.

Example:

```bash
pytest
```

The system should capture:

```text
exit code
stdout
stderr
duration
pass/fail counts
```

Do not attempt to support every testing framework automatically in the MVP.

---

# 13. Metric

Metrics are arbitrary project measurements.

DevMemory must not assume that every project is an ML project.

Example ML metric:

```json
{
  "name": "accuracy",
  "before": 89.2,
  "after": 93.4,
  "unit": "%"
}
```

Example software metric:

```json
{
  "name": "latency",
  "before": 420,
  "after": 310,
  "unit": "ms"
}
```

Example:

```json
{
  "name": "error_rate",
  "before": 4.2,
  "after": 1.7,
  "unit": "%"
}
```

Schema:

```text
metric_id
version_id
name
before_value
after_value
unit
direction
metadata
```

`direction` may be:

```text
higher_is_better
lower_is_better
neutral
```

---

# 14. Regression

A regression represents a measurable deterioration caused by a development version.

Example:

```json
{
  "version_id": "v8",
  "metric": "accuracy",
  "before": 93.4,
  "after": 76.1,
  "change_percent": -18.5,
  "severity": "HIGH"
}
```

Regression detection can initially use simple rules.

Example:

```text
If metric direction = higher_is_better
and after < before
then possible regression.
```

For:

```text
lower_is_better
```

the opposite applies.

Test regressions can include:

```text
previously passing tests → failing tests
```

---

# 15. DevelopmentEvent

A normalized event allows different adapters to feed the same system.

Example:

```json
{
  "event_id": "event-123",
  "project_id": "visionai",

  "timestamp": "2026-09-06T01:20:00Z",

  "source": "devmemory",

  "checkpoint_id": "checkpoint-abc123",

  "agent": "Claude Code",

  "intent": "Improve image classification accuracy",

  "git_commit": "7fa91c",
  "parent_commit": "91ac21",

  "changed_files": [
    "model.py",
    "preprocessing.py"
  ],

  "feature": "Image Classification",

  "status": "SUCCESS",

  "tests": {
    "passed": 143,
    "failed": 5
  },

  "metrics": {
    "accuracy": {
      "before": 89.2,
      "after": 93.4
    }
  }
}
```

The normalized event is the bridge between adapters and storage.

---

# 16. Analysis

AI-generated analysis should be stored separately from raw development information.

Example:

```json
{
  "summary": "Preprocessing changes improved classification accuracy.",
  "reasoning": "Normalization reduced input variance.",
  "recommendation": "Keep this approach.",
  "warnings": []
}
```

Important:

AI analysis must never overwrite factual source information.

For example:

```text
Git says:
142 lines added
```

AI analysis cannot change that to:

```text
approximately 150 lines
```

The system should distinguish:

```text
FACT
```

from:

```text
AI ANALYSIS
```

---

# 17. PreviousAttempt

Previous attempts are derived from historical development versions.

Example:

```json
{
  "version_id": "v8",
  "feature": "Image Classification",
  "change_summary": "Changed learning rate to 0.0001",
  "status": "REGRESSION",
  "result": "Accuracy dropped from 93.4% to 76.1%"
}
```

The MVP can retrieve previous attempts using:

1. Same feature.
2. Same files.
3. Similar intent.
4. Similar metric.
5. Explicitly failed/regressed versions.

Semantic similarity can be added later.

---

# 18. Artifact

An artifact represents a snapshot associated with a version.

Example:

```json
{
  "artifact_id": "artifact-v7",
  "version_id": "v7",
  "path": ".devmemory/artifacts/v7.tar.gz",
  "type": "project_snapshot",
  "size_bytes": 382910,
  "created_at": "2026-09-06T01:21:00Z"
}
```

The MVP should use compressed project archives.

Do not build container-based reproducibility.

---

# 19. Environment Metadata

Optionally store:

```json
{
  "python_version": "3.12.5",
  "platform": "Windows",
  "package_manager": "pip"
}
```

Potential additional metadata:

```text
requirements.txt
pyproject.toml
package.json
lock files
OS
runtime version
```

This is metadata only.

Do not attempt to recreate the entire environment.

---

# 20. SQLite Database

The MVP should use SQLite.

Recommended database:

```text
.devmemory/metadata.db
```

---

# 21. Projects Table

```sql
CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    repository_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    current_version_id TEXT
);
```

---

# 22. Versions Table

```sql
CREATE TABLE versions (
    version_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,

    intent TEXT,
    agent TEXT,

    entire_checkpoint_id TEXT,

    git_commit TEXT NOT NULL,
    parent_commit TEXT,

    feature_id TEXT,

    status TEXT NOT NULL,

    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,

    analysis_json TEXT,

    created_at TEXT NOT NULL,

    FOREIGN KEY(project_id)
        REFERENCES projects(project_id),

    FOREIGN KEY(feature_id)
        REFERENCES features(feature_id)
);
```

---

# 23. Features Table

```sql
CREATE TABLE features (
    feature_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY(project_id)
        REFERENCES projects(project_id)
);
```

---

# 24. Changed Files Table

```sql
CREATE TABLE changed_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    version_id TEXT NOT NULL,

    path TEXT NOT NULL,
    old_path TEXT,

    change_type TEXT NOT NULL,

    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,

    FOREIGN KEY(version_id)
        REFERENCES versions(version_id)
);
```

---

# 25. Tests Table

```sql
CREATE TABLE tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    version_id TEXT NOT NULL,

    command TEXT,

    total INTEGER DEFAULT 0,
    passed INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,

    duration_seconds REAL,

    output TEXT,

    FOREIGN KEY(version_id)
        REFERENCES versions(version_id)
);
```

---

# 26. Metrics Table

```sql
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    version_id TEXT NOT NULL,

    name TEXT NOT NULL,

    before_value REAL,
    after_value REAL,

    unit TEXT,

    direction TEXT,

    metadata_json TEXT,

    FOREIGN KEY(version_id)
        REFERENCES versions(version_id)
);
```

---

# 27. Artifacts Table

```sql
CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,

    version_id TEXT NOT NULL,

    path TEXT NOT NULL,

    type TEXT NOT NULL,

    size_bytes INTEGER,

    created_at TEXT NOT NULL,

    FOREIGN KEY(version_id)
        REFERENCES versions(version_id)
);
```

---

# 28. Entire Checkpoints Table

```sql
CREATE TABLE entire_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,

    project_id TEXT NOT NULL,

    location TEXT,

    agent TEXT,

    intent TEXT,

    timestamp TEXT,

    git_commit TEXT,

    association_method TEXT,

    association_confidence REAL,

    metadata_json TEXT,

    FOREIGN KEY(project_id)
        REFERENCES projects(project_id)
);
```

---

# 29. Database Indexes

Add indexes for common queries:

```sql
CREATE INDEX idx_versions_project
ON versions(project_id);

CREATE INDEX idx_versions_git_commit
ON versions(git_commit);

CREATE INDEX idx_versions_feature
ON versions(feature_id);

CREATE INDEX idx_versions_status
ON versions(status);

CREATE INDEX idx_changed_files_path
ON changed_files(path);

CREATE INDEX idx_metrics_name
ON metrics(name);

CREATE INDEX idx_checkpoints_commit
ON entire_checkpoints(git_commit);
```

---

# 30. Version Comparison

The comparison API should accept:

```text
version_a
version_b
```

Example:

```text
V6 → V7
```

The backend should:

1. Resolve V6 to its Git commit.
2. Resolve V7 to its Git commit.
3. Generate the Git diff.
4. Compare changed files.
5. Compare tests.
6. Compare metrics.
7. Compare status.
8. Compare feature state.

Example response:

```json
{
  "from_version": "v6",
  "to_version": "v7",

  "git": {
    "from_commit": "91ac21",
    "to_commit": "7fa91c",
    "lines_added": 142,
    "lines_removed": 37
  },

  "files": [
    "model.py",
    "preprocessing.py"
  ],

  "metrics": {
    "accuracy": {
      "before": 89.2,
      "after": 93.4
    }
  },

  "tests": {
    "before_passed": 138,
    "after_passed": 143
  },

  "status": "SUCCESS"
}
```

---

# 31. Restore

Restore should operate using Git.

The API:

```text
POST /api/versions/{version_id}/restore
```

should NOT immediately destroy the current state.

Preferred MVP behavior:

```text
1. Check working tree.
2. Refuse if there are uncommitted changes unless explicitly overridden.
3. Identify target Git commit.
4. Create a safety reference/current-state record.
5. Restore the requested state.
6. Inform the user.
```

The UI must clearly warn:

```text
Restore Version 10

This will restore the project source code to the Git state
associated with Version 10.

Current uncommitted changes may be affected.
```

---

# 32. REST API

The backend should expose a simple REST API.

Base:

```text
/api
```

---

## Project

```http
GET /api/project
```

Returns project information.

---

## Status

```http
GET /api/status
```

Example:

```json
{
  "current_version": "v14",
  "completion": 82,
  "features": {
    "completed": 8,
    "total": 10
  },
  "tests": {
    "passed": 143,
    "failed": 5
  }
}
```

---

## Versions

```http
GET /api/versions
```

Returns version history.

Optional:

```http
GET /api/versions/{version_id}
```

Returns complete version information.

---

## Version Diff

```http
GET /api/versions/{version_id}/diff
```

Returns the exact Git diff associated with the version.

---

## Compare

```http
GET /api/compare?from=v6&to=v7
```

Returns comparison data.

---

## Features

```http
GET /api/features
```

Returns feature status.

```http
GET /api/features/{feature_id}
```

Returns feature history.

---

## Previous Attempts

```http
GET /api/attempts
```

Returns previous development attempts.

Optional filters:

```text
feature
status
query
```

---

## Checkpoint

```http
GET /api/versions/{version_id}/checkpoint
```

Returns Entire checkpoint information.

---

## Context

```http
GET /api/context
```

Returns AI-oriented project context.

---

## Restore

```http
POST /api/versions/{version_id}/restore
```

Restores a previous version after safety checks.

---

# 33. Checkpoint API Response

Example:

```json
{
  "checkpoint_id": "checkpoint-abc123",
  "agent": "Claude Code",
  "intent": "Improve image classification accuracy",
  "timestamp": "2026-09-06T01:15:00Z",
  "git_commit": "7fa91c",
  "association": {
    "method": "explicit",
    "confidence": 1.0
  },
  "location": "entire://checkpoint/abc123"
}
```

---

# 34. AI Context API

The most important AI endpoint is:

```http
GET /api/context
```

It should return concise, useful project memory.

Example:

```json
{
  "project": "VisionAI",

  "current_version": "v14",

  "current_status": "IN_PROGRESS",

  "completed_features": [
    "Authentication",
    "Image Classification"
  ],

  "incomplete_features": [
    "Notifications"
  ],

  "recent_changes": [
    {
      "version": "v14",
      "intent": "Improve inference performance",
      "status": "SUCCESS"
    }
  ],

  "previous_failures": [
    {
      "version": "v12",
      "change": "learning_rate=0.0001",
      "result": "Accuracy dropped from 91.7% to 76.3%"
    }
  ],

  "important_decisions": []
}
```

The response should prioritize actionable information rather than dumping the entire database.

---

# 35. MCP Interface

DevMemory should expose project memory to AI coding agents through MCP where practical.

Recommended tools:

```text
get_project_status
get_current_version
get_version_history
get_version
get_version_diff
compare_versions
get_feature_status
get_feature_history
get_previous_attempts
get_failed_changes
get_checkpoint_context
get_development_trace
get_project_context
```

---

# 36. MCP: get_project_status

Example request:

```text
get_project_status()
```

Response:

```json
{
  "project": "VisionAI",
  "current_version": "v14",
  "completion": 82,
  "features_completed": 8,
  "features_total": 10,
  "current_status": "IN_PROGRESS"
}
```

---

# 37. MCP: get_previous_attempts

Example:

```text
get_previous_attempts(
    feature="Image Classification"
)
```

Response:

```json
{
  "attempts": [
    {
      "version": "v8",
      "change": "learning_rate=0.0001",
      "status": "REGRESSION",
      "result": "Accuracy dropped from 93.4% to 76.1%",
      "recommendation": "Avoid repeating this configuration."
    }
  ]
}
```

---

# 38. MCP: get_version_diff

Example:

```text
get_version_diff(
    from_version="v6",
    to_version="v7"
)
```

Response should contain:

```text
changed files
lines added
lines removed
exact diff
metric changes
test changes
```

---

# 39. MCP: get_checkpoint_context

Example:

```text
get_checkpoint_context(
    version_id="v7"
)
```

Response:

```json
{
  "version": "v7",
  "checkpoint_id": "checkpoint-abc123",
  "agent": "Claude Code",
  "intent": "Improve image classification accuracy",
  "git_commit": "7fa91c"
}
```

---

# 40. MCP: get_development_trace

This should provide the complete lineage.

Example:

```json
{
  "version": "v7",

  "intent": "Improve image classification accuracy",

  "agent": "Claude Code",

  "entire": {
    "checkpoint_id": "checkpoint-abc123"
  },

  "git": {
    "commit": "7fa91c",
    "parent": "91ac21"
  },

  "changes": {
    "files": [
      "model.py",
      "preprocessing.py"
    ],
    "lines_added": 142,
    "lines_removed": 37
  },

  "tests": {
    "passed": 143,
    "failed": 5
  },

  "metrics": {
    "accuracy": {
      "before": 89.2,
      "after": 93.4
    }
  },

  "status": "SUCCESS"
}
```

---

# 41. Databricks Normalized Event

Every meaningful development version should be convertible into a Databricks event.

Example:

```json
{
  "project_id": "visionai",
  "version_id": "v7",

  "timestamp": "2026-09-06T01:20:00Z",

  "source": "devmemory",

  "checkpoint_id": "checkpoint-abc123",

  "agent": "Claude Code",

  "intent": "Improve image classification accuracy",

  "feature": "Image Classification",

  "git_commit": "7fa91c",

  "parent_commit": "91ac21",

  "status": "SUCCESS",

  "files_changed": 2,

  "lines_added": 142,
  "lines_removed": 37,

  "tests_passed": 143,
  "tests_failed": 5,

  "metrics": {
    "accuracy_before": 89.2,
    "accuracy_after": 93.4
  },

  "regression": false
}
```

---

# 42. Databricks Tables

The initial Databricks model should contain:

```text
projects
development_versions
development_events
features
tests
metrics
agent_sessions
```

The implementation may simplify this for the MVP if necessary.

The important requirement is that development data can be queried analytically.

---

# 43. Useful Databricks Queries

The system should support analytics such as:

### Regression history

```text
Which versions caused regressions?
```

### Feature attempts

```text
Which features required the most development attempts?
```

### Agent performance

```text
Which AI-assisted sessions produced the most successful changes?
```

### Frequently changed files

```text
Which files change most frequently?
```

### Development trend

```text
Are test results and metrics improving over time?
```

### Failed approaches

```text
Which approaches repeatedly failed?
```

These analytics should appear in the dashboard where practical.

---

# 44. Search

Search should operate across normalized DevMemory metadata.

Example:

```http
GET /api/search?q=authentication
```

Searchable fields should include:

```text
version ID
intent
agent
feature
status
changed file paths
commit SHA
checkpoint ID
analysis
errors
```

Example results:

```json
{
  "results": [
    {
      "version": "v3",
      "type": "version",
      "summary": "Added JWT authentication"
    },
    {
      "version": "v7",
      "type": "version",
      "summary": "Modified authentication middleware"
    }
  ]
}
```

---

# 45. API Design Principle

The API should expose development intelligence rather than database internals.

Bad:

```text
GET /api/sql/versions
```

Good:

```text
GET /api/versions
GET /api/context
GET /api/attempts
GET /api/features
```

The frontend and MCP layer should consume domain-level APIs.

---

# 46. Serialization

Internal Python models should use typed structures.

Prefer:

```python
@dataclass
class DevelopmentVersion:
    version_id: str
    project_id: str
    git_commit: str
    parent_commit: str | None
    intent: str | None
    agent: str | None
    status: str
```

Pydantic models can be used at API boundaries.

Example:

```python
class VersionResponse(BaseModel):
    version_id: str
    git_commit: str
    status: str
```

Keep persistence models and API response models separable where useful.

---

# 47. IDs

Use stable identifiers.

Recommended:

```text
project_id:
human-readable slug

version_id:
v1, v2, v3...

checkpoint_id:
Entire-provided identifier

git_commit:
Git SHA

artifact_id:
UUID or deterministic artifact identifier
```

Version numbers are scoped to a project.

---

# 48. Version Creation Rules

When:

```bash
devmemory checkpoint
```

is executed:

```text
1. Verify project is initialized.
2. Verify Git repository exists.
3. Inspect Git state.
4. Discover relevant Entire checkpoint.
5. Determine Git commit.
6. Determine parent commit.
7. Calculate changed files.
8. Calculate diff statistics.
9. Collect configured tests.
10. Collect configured metrics.
11. Determine feature.
12. Determine status.
13. Detect regression.
14. Generate optional AI analysis.
15. Create DevelopmentVersion.
16. Store metadata in SQLite.
17. Create artifact snapshot if enabled.
18. Send normalized event to Databricks.
19. Update dashboard data.
```

The entire operation should be traceable.

---

# 49. Idempotency

Running:

```bash
devmemory checkpoint
```

twice for the same Git commit should not create duplicate versions accidentally.

Before creating a new version:

```text
Check whether git_commit already belongs to a DevMemory version.
```

If it does:

```text
Version already exists for commit 7fa91c.

Version: V7
```

Allow an explicit force option only if needed.

---

# 50. MVP Simplifications

The following may be simplified during initial implementation:

```text
Advanced semantic search
Complex feature detection
Automatic metric discovery
Automatic documentation analysis
Sophisticated graph analysis
Multiple artifact backends
Complex Databricks architecture
Advanced MCP authentication
Distributed storage
```

The core data model must remain capable of supporting these later.

---

# 51. MVP Definition of Done

The data/API layer is complete when the following flow works:

```text
Entire Checkpoint
        ↓
Git Commit
        ↓
DevelopmentEvent
        ↓
DevelopmentVersion
        ↓
SQLite
        ↓
REST API
        ↓
Dashboard
```

And the same version can provide context to an AI agent:

```text
DevelopmentVersion
        ↓
Project Context
        ↓
MCP/API
        ↓
Future AI Agent
```

The minimum useful version record must answer:

```text
What changed?
Why did it change?
Which AI agent worked on it?
Which Entire checkpoint is associated?
Which Git commit contains the change?
Which files changed?
What was the result?
Did tests pass?
Did metrics improve?
Was this a regression?
What should happen next?
```

This data model is the foundation of DevMemory.
