# DevMemory Architecture

## 1. Purpose

This document defines the technical architecture of DevMemory.

DevMemory is a development-memory and version-intelligence layer that sits alongside existing development tools.

It connects:

```text
AI-assisted development
        ↓
Entire Checkpoints
        ↓
Git history
        ↓
Tests / metrics
        ↓
Development Versions
        ↓
Local project memory
        ↓
Databricks analytics
        ↓
Web dashboard
        ↓
AI context / MCP
```

The architecture must remain modular.

DevMemory should integrate with existing tools rather than replace them.

---

# 2. Architectural Principles

## Principle 1: Do not replace existing tools

DevMemory should not replace:

* Git
* Entire
* Claude Code
* VS Code
* Cursor
* Databricks
* existing testing frameworks
* existing CI/CD systems

Instead:

```text
Existing tools
      ↓
DevMemory adapters
      ↓
Normalized development event
```

---

## Principle 2: Git remains the source of truth for code

Git owns:

* commits
* branches
* source history
* diffs
* changed files
* file renames
* additions
* deletions
* exact code state

DevMemory stores Git references rather than creating another source-control system.

---

## Principle 3: Entire remains the source of truth for AI development context

Entire owns the AI-assisted development checkpoint/session context.

DevMemory should store:

* checkpoint ID
* checkpoint reference
* agent
* relevant session metadata
* timestamp
* association with Git

DevMemory should not duplicate the entire Entire session.

---

## Principle 4: DevMemory owns the normalized development record

DevMemory is responsible for connecting:

```text
Intent
+
AI context
+
Entire checkpoint
+
Git commit
+
Git diff
+
tests
+
metrics
+
feature
+
status
+
analysis
```

into a single Development Version.

---

## Principle 5: Build adapters around external systems

External systems should be isolated behind adapters.

Example:

```text
EntireAdapter
GitAdapter
TestAdapter
MetricsAdapter
DatabricksAdapter
AgentAdapter
ArtifactAdapter
```

The core domain should not depend directly on Entire CLI commands, Git subprocesses, or Databricks APIs.

---

# 3. High-Level Architecture

```text
                         ┌─────────────────────┐
                         │ Developer / AI Agent │
                         └──────────┬──────────┘
                                    │
                                    ↓
                         ┌─────────────────────┐
                         │ Existing Dev Tools  │
                         │ Claude Code / VSCode │
                         │ Cursor / Terminal   │
                         └──────────┬──────────┘
                                    │
                                    ↓
                         ┌─────────────────────┐
                         │      Entire         │
                         │ AI session/checkpoint│
                         └──────────┬──────────┘
                                    │
                                    │
             ┌──────────────────────┴──────────────────────┐
             │                                             │
             ↓                                             ↓
      ┌─────────────┐                              ┌──────────────┐
      │     Git     │                              │ Test/Metrics │
      │ code history│                              │   adapters   │
      └──────┬──────┘                              └──────┬───────┘
             │                                             │
             └──────────────────┬──────────────────────────┘
                                ↓
                    ┌────────────────────────┐
                    │     DevMemory Core     │
                    │                        │
                    │ DevelopmentVersion     │
                    │ DevelopmentEvent       │
                    │ Feature                │
                    │ Analysis               │
                    └───────────┬────────────┘
                                │
                ┌───────────────┼────────────────┐
                ↓               ↓                ↓
        ┌─────────────┐ ┌──────────────┐ ┌──────────────┐
        │   SQLite    │ │  Artifacts   │ │  Databricks  │
        │ local state │ │  snapshots   │ │   analytics  │
        └──────┬──────┘ └──────────────┘ └──────┬───────┘
               │                                │
               └───────────────┬────────────────┘
                               ↓
                     ┌────────────────────┐
                     │ FastAPI Web Server │
                     └─────────┬──────────┘
                               ↓
                     ┌────────────────────┐
                     │     Dashboard      │
                     └────────────────────┘

                               +
                               ↓

                     ┌────────────────────┐
                     │ AI Context / MCP   │
                     └────────────────────┘
```

---

# 4. System Components

The initial implementation should contain these major components:

```text
1. CLI
2. Core domain
3. External adapters
4. Local persistence
5. Artifact storage
6. Intelligence layer
7. REST API
8. Web dashboard
9. Databricks integration
10. AI context / MCP
```

These components should remain loosely coupled.

---

# 5. Recommended Repository Structure

Use a Python package with a clear separation between domain logic and integrations.

Recommended structure:

```text
devmemory/
│
├── pyproject.toml
├── README.md
├── LICENSE
│
├── docs/
│   ├── PROJECT_SPEC.md
│   ├── ENTIRE_QUICKSTART.md
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── API.md
│   ├── DEVELOPMENT.md
│   └── DEMO.md
│
├── src/
│   └── devmemory/
│       │
│       ├── __init__.py
│       ├── cli.py
│       ├── config.py
│       │
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── enums.py
│       │   └── services.py
│       │
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── entire.py
│       │   ├── git.py
│       │   ├── tests.py
│       │   ├── metrics.py
│       │   ├── databricks.py
│       │   └── agents.py
│       │
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── database.py
│       │   ├── repositories.py
│       │   └── artifacts.py
│       │
│       ├── intelligence/
│       │   ├── __init__.py
│       │   ├── analyzer.py
│       │   ├── regression.py
│       │   ├── features.py
│       │   └── memory.py
│       │
│       ├── collectors/
│       │   ├── __init__.py
│       │   ├── checkpoint.py
│       │   ├── tests.py
│       │   └── metrics.py
│       │
│       ├── context/
│       │   ├── __init__.py
│       │   └── provider.py
│       │
│       ├── mcp/
│       │   ├── __init__.py
│       │   └── server.py
│       │
│       └── web/
│           ├── __init__.py
│           ├── app.py
│           ├── routes.py
│           └── templates/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
└── examples/
    └── demo-project/
```

The structure can be simplified during implementation if necessary.

Do not create empty abstractions purely for architectural appearance.

---

# 6. Domain Layer

The domain layer contains concepts that belong to DevMemory itself.

Important domain objects:

```text
Project
DevelopmentVersion
DevelopmentEvent
CheckpointReference
Feature
TestResult
Metric
Artifact
Analysis
```

These models should not depend on:

* FastAPI
* SQLite
* Databricks SDK
* Git subprocesses
* Entire implementation details

The domain layer should represent the data and business rules.

---

# 7. Development Version

The central domain object is:

```text
DevelopmentVersion
```

Conceptually:

```python
DevelopmentVersion(
    id,
    project_id,
    version_number,

    intent,

    entire_checkpoint,
    agent,

    git_commit,
    parent_commit,

    changed_files,
    diff_summary,

    feature,

    tests,
    metrics,

    status,

    analysis,
    recommendation,

    artifact,

    timestamp
)
```

The exact implementation should use typed Python models.

Pydantic is recommended.

---

# 8. Development Event

A Development Event represents normalized information collected from an external source.

Example:

```python
DevelopmentEvent(
    project_id="vision-ai",
    timestamp=...,
    source="entire",

    checkpoint_id="abc123",

    agent="Claude Code",

    intent="Improve image classification accuracy",

    git_commit="7fa91c",
    parent_commit="4e92ab1",

    changed_files=[
        "model.py",
        "preprocessing.py"
    ],

    diff="...",

    feature="Image Classification",

    status="SUCCESS",

    tests={
        "passed": 143,
        "failed": 0
    },

    metrics={
        "accuracy": {
            "before": 89.2,
            "after": 93.4
        }
    }
)
```

Different adapters can contribute information to the event.

---

# 9. Adapter Architecture

External integrations should implement adapter interfaces.

Example:

```python
class EntireAdapter(Protocol):
    def is_available(self) -> bool:
        ...

    def is_enabled(self) -> bool:
        ...

    def get_current_checkpoint(self) -> CheckpointReference | None:
        ...

    def get_checkpoint(
        self,
        checkpoint_id: str
    ) -> CheckpointReference | None:
        ...
```

Git:

```python
class GitAdapter(Protocol):
    def current_commit(self) -> str:
        ...

    def parent_commit(self, commit: str) -> str | None:
        ...

    def get_diff(
        self,
        parent: str,
        commit: str
    ) -> str:
        ...

    def changed_files(
        self,
        parent: str,
        commit: str
    ) -> list[str]:
        ...
```

Tests:

```python
class TestAdapter(Protocol):
    def collect(self) -> TestResult:
        ...
```

Databricks:

```python
class DatabricksAdapter(Protocol):
    def publish_version(
        self,
        version: DevelopmentVersion
    ) -> None:
        ...
```

---

# 10. Entire Adapter

The Entire adapter is a critical component.

File:

```text
src/devmemory/adapters/entire.py
```

Responsibilities:

```text
- detect Entire installation
- detect whether Entire is enabled
- detect active agent integration
- find relevant checkpoint
- resolve checkpoint metadata
- expose checkpoint references
```

It should hide Entire-specific implementation details.

The rest of the application should only see:

```text
CheckpointReference
```

or equivalent normalized objects.

---

# 11. Entire Checkpoint Association

The preferred association mechanism is:

```text
Git commit
    ↓
Entire-Checkpoint trailer
    ↓
Entire checkpoint
```

The checkpoint association algorithm should be:

```text
1. Determine current Git commit.
2. Inspect commit metadata/trailers.
3. Look for Entire-Checkpoint.
4. If found, resolve the checkpoint.
5. Normalize the checkpoint.
6. Attach it to the Development Version.
```

Fallbacks can inspect Entire's repository state or supported CLI interfaces.

Timestamp-based association should only be used as a last-resort heuristic and should be clearly marked as inferred.

Never silently fabricate a checkpoint.

---

# 12. Git Adapter

File:

```text
src/devmemory/adapters/git.py
```

The Git adapter should encapsulate Git operations.

Responsibilities:

```text
- repository detection
- current branch
- current commit
- parent commit
- commit metadata
- commit trailers
- changed files
- diff
- line statistics
- restore operations
```

The adapter may use:

* subprocess + Git CLI
* GitPython
* another reliable Git library

Choose the simplest reliable option.

Do not introduce GitPython solely if subprocess-based Git integration is already sufficient.

---

# 13. Version Creation Pipeline

The main workflow is:

```text
devmemory checkpoint
        ↓
Checkpoint Collector
        ↓
Git Collector
        ↓
Test Collector
        ↓
Metrics Collector
        ↓
Feature Detection
        ↓
Status Calculation
        ↓
Analysis
        ↓
DevelopmentVersion
        ↓
SQLite
        ↓
Artifact
        ↓
Databricks
        ↓
Dashboard
```

Each stage should be independently testable.

---

# 14. Checkpoint Command

The primary CLI command is:

```bash
devmemory checkpoint
```

Expected behavior:

```text
1. Confirm repository.
2. Load DevMemory configuration.
3. Detect Git HEAD.
4. Detect parent commit.
5. Inspect Entire association.
6. Collect checkpoint context.
7. Collect Git diff.
8. Collect changed files.
9. Collect test information if configured.
10. Collect metrics if configured.
11. Infer feature.
12. Determine status.
13. Generate analysis.
14. Create Development Version.
15. Persist locally.
16. Optionally create snapshot.
17. Optionally publish to Databricks.
18. Report result.
```

Example output:

```text
Creating Development Version...

Git commit:
7fa91c

Entire checkpoint:
a3b2c4d5e6f7

Files changed:
2

Tests:
143 passed

Status:
SUCCESS

Created:
V7
```

---

# 15. Checkpoint Idempotency

Running:

```bash
devmemory checkpoint
```

twice against the same Git commit should not blindly create:

```text
V7
V8
```

for the same development state.

The system should detect whether the current Git commit has already been registered.

Possible behavior:

```text
Development Version already exists:

V7
Git commit: 7fa91c

Nothing to create.
```

A force option may be added later.

---

# 16. Version Numbering

Version numbers are DevMemory's own logical sequence.

They are NOT Git commit numbers.

Example:

```text
Git:
a91c2e

DevMemory:
V7
```

The database should maintain:

```text
project_id
version_number
```

with uniqueness enforced.

A project can therefore have:

```text
V1
V2
V3
...
V14
```

while Git commits have completely different identifiers.

---

# 17. Local Persistence

SQLite should be the default local database.

Project storage:

```text
.devmemory/
    config.json
    metadata.db
    artifacts/
    cache/
```

SQLite is appropriate because:

* no external database is required
* easy installation
* easy backup
* works locally
* supports relational queries
* sufficient for hackathon/demo workloads

The database should contain normalized metadata.

---

# 18. Artifact Storage

Artifacts should be stored outside the SQLite database.

Example:

```text
.devmemory/
    artifacts/
        V1.tar.gz
        V2.tar.gz
        V3.tar.gz
```

SQLite stores:

```text
artifact_id
version_id
path
hash
size
created_at
```

Do not store large binary archives directly inside SQLite.

---

# 19. Snapshot Strategy

For the initial implementation, snapshots can be generated from the Git state.

Preferred approach:

```text
Development Version
        ↓
Git commit
        ↓
archive source tree
        ↓
snapshot-V7.tar.gz
```

The snapshot should exclude unnecessary directories such as:

```text
.git/
.devmemory/
node_modules/
.venv/
__pycache__/
```

unless explicitly required.

A configurable exclusion list should be possible later.

Git remains the authoritative source for code history.

The snapshot is an artifact/reproducibility convenience.

---

# 20. Tests

DevMemory should not require users to adopt a specific testing framework.

The initial implementation can support configurable test commands.

Example configuration:

```json
{
  "test_command": "pytest"
}
```

Running a checkpoint may optionally execute:

```bash
pytest
```

and collect:

```text
passed
failed
skipped
duration
exit_code
```

For other projects:

```text
npm test
go test ./...
mvn test
cargo test
```

may be configured.

The adapter should treat the command as configurable.

---

# 21. Metrics

DevMemory should support arbitrary project metrics.

Do not assume:

```text
accuracy
```

is always available.

Metrics should be represented generically.

Example:

```json
{
  "accuracy": {
    "before": 89.2,
    "after": 93.4,
    "unit": "%"
  },

  "latency": {
    "before": 420,
    "after": 310,
    "unit": "ms"
  }
}
```

Metrics can come from:

* command output
* JSON files
* test reports
* user input
* project scripts
* future integrations

---

# 22. Status Calculation

Status should be derived from available evidence.

Possible statuses:

```text
IN_PROGRESS
SUCCESS
PARTIAL_SUCCESS
ERROR
REGRESSION
NEEDS_REVIEW
```

Basic rules:

```text
ERROR
→ command/process failed

REGRESSION
→ relevant metric worsened significantly
   or test/build status degraded

SUCCESS
→ tests/build succeeded
   and no detected regression

PARTIAL_SUCCESS
→ mixed results

NEEDS_REVIEW
→ insufficient evidence

IN_PROGRESS
→ work has started but has not produced a completed development state
```

The exact logic should be configurable and extensible.

Do not use arbitrary hard-coded thresholds everywhere.

---

# 23. Regression Detection

Regression detection should compare a Development Version against its previous relevant state.

Example:

```text
V7

Accuracy:
89.2 → 93.4
```

Result:

```text
IMPROVEMENT
```

Then:

```text
V8

Accuracy:
93.4 → 76.1
```

Result:

```text
REGRESSION
```

For tests:

```text
143 passed → 130 passed
```

may indicate regression.

For latency:

```text
420ms → 300ms
```

may indicate improvement.

The metric direction must be configurable.

Some metrics are:

```text
higher is better
```

Others:

```text
lower is better
```

---

# 24. Feature Detection

Feature identification should initially use simple mechanisms.

Possible sources:

1. explicit CLI argument

```bash
devmemory checkpoint --feature "Authentication"
```

2. configuration

3. commit message

4. Entire intent

5. AI analysis

The system should NOT attempt sophisticated code understanding in the first version.

Example:

```text
Intent:
"Fix JWT token expiration"

Feature:
Authentication
```

This can later be improved with LLM-based classification.

---

# 25. AI Analysis

AI analysis is an intelligence layer.

File:

```text
src/devmemory/intelligence/analyzer.py
```

Potential inputs:

```text
intent
Git diff
changed files
test results
metrics
previous version
feature
Entire context
```

Potential outputs:

```text
summary
reasoning
status explanation
recommendation
risk
regression explanation
```

Example:

```text
Analysis:

The preprocessing change increased classification
accuracy from 89.2% to 93.4% while maintaining all
existing tests.

Recommendation:

Keep this approach.
```

The analyzer should not fabricate metrics or test results.

All numerical claims must come from collected data.

---

# 26. Development Memory

Development memory is built from historical Development Versions.

Example:

```text
V8
learning_rate=0.0001

Accuracy:
93.4 → 76.1

Status:
REGRESSION
```

Later:

```text
Current proposal:
learning_rate=0.0001
```

Memory retrieval should return:

```text
Previous attempt detected.

V8:
learning_rate=0.0001

Result:
Accuracy decreased from 93.4% to 76.1%.

Recommendation:
Avoid repeating this configuration.
```

---

# 27. Previous Attempt Retrieval

The first implementation should use a combination of:

```text
exact metadata matching
+
keyword matching
+
feature matching
+
optional semantic similarity
```

Do not build a vector database unless it is genuinely necessary.

For the MVP, SQLite + text search may be sufficient.

Example:

```text
query:
"learning rate"

search:
- intent
- analysis
- recommendation
- changed files
- feature
- error
- metric names
```

Later, embeddings/vector search can be added.

---

# 28. AI Context Provider

File:

```text
src/devmemory/context/provider.py
```

Responsibilities:

```text
- assemble current project state
- retrieve relevant history
- retrieve previous failures
- retrieve incomplete features
- retrieve latest Entire checkpoint
- retrieve recent changes
- format context for an AI agent
```

Example:

```python
context = provider.get_project_context()
```

Returns:

```json
{
  "current_version": 14,

  "current_status": "IN_PROGRESS",

  "incomplete_features": [
    "notifications"
  ],

  "recent_changes": [
    "V14: Improve inference performance"
  ],

  "previous_failures": [
    {
      "version": 12,
      "change": "learning_rate=0.0001",
      "result": "Accuracy dropped to 76.3%"
    }
  ]
}
```

---

# 29. MCP

MCP should expose DevMemory context to compatible AI agents.

Initial tools:

```text
get_project_status
get_current_version
get_version_history
get_version
compare_versions
get_feature_status
get_previous_attempts
get_failed_changes
get_checkpoint_context
get_project_context
```

The MCP server should call DevMemory's internal services.

It should NOT directly query SQLite everywhere.

Architecture:

```text
AI Agent
   ↓
MCP
   ↓
Context Provider
   ↓
Domain Services
   ↓
Repositories
   ↓
SQLite
```

---

# 30. REST API

The web dashboard should use a REST API.

Example endpoints:

```text
GET /api/project

GET /api/versions

GET /api/versions/{version_id}

GET /api/versions/{version_id}/diff

GET /api/versions/{version_id}/checkpoint

GET /api/features

GET /api/features/{feature_id}

GET /api/search?q=...

GET /api/compare?from=V6&to=V7

GET /api/memory/previous-attempts

GET /api/status

POST /api/restore/{version_id}
```

The API should expose normalized DevMemory data.

---

# 31. Web Backend

FastAPI is recommended.

Reasons:

* Python-native
* simple
* fast to develop
* automatic OpenAPI documentation
* easy integration with Pydantic
* suitable for local server

Example:

```bash
devmemory serve
```

starts:

```text
FastAPI
    ↓
localhost:8000
```

---

# 32. Frontend

The dashboard should prioritize usability over frontend complexity.

Possible implementation:

```text
FastAPI
+
Jinja templates
+
HTML
+
CSS
+
vanilla JavaScript
```

or:

```text
FastAPI backend
+
React frontend
```

Use React only if it genuinely improves development speed.

The initial dashboard should not require a complex frontend build system unless necessary.

---

# 33. Dashboard

Main dashboard:

```text
PROJECT
VisionAI

Current Version
V14

Completion
82%

Features
8 / 10

Tests
143 / 148

Latest Metric
Accuracy: 93.4%
```

Version timeline:

```text
V14   SUCCESS
V13   SUCCESS
V12   REGRESSION
V11   SUCCESS
V10   PARTIAL
```

Clicking a version opens the Version Detail page.

---

# 34. Version Detail

Show:

```text
Version
V14

Intent
Improve inference performance

Agent
Claude Code

Entire Checkpoint
abc123

Git Commit
a72c91

Files
inference.py
model.py
config.yaml

Tests
143 passed
5 failed

Metrics
Accuracy: 93.4%
Latency: 280ms

Status
SUCCESS
```

Also show:

```text
Git diff
AI analysis
recommendation
feature
impact
artifact
```

---

# 35. Development Trace

The UI should visually connect:

```text
Intent
   ↓
AI Agent
   ↓
Entire Checkpoint
   ↓
Git Commit
   ↓
Files Changed
   ↓
Tests
   ↓
Metrics
   ↓
Development Version
```

This should be one of the most visually important parts of the demo.

---

# 36. Version Comparison

Endpoint:

```text
GET /api/compare?from=V6&to=V7
```

The comparison should provide:

```text
Files added
Files modified
Files deleted

Lines added
Lines removed

Metric changes

Test changes

Status changes

Feature changes
```

The Git diff remains the source of truth for code changes.

---

# 37. Restore

Restoration must be treated as a potentially destructive operation.

The UI should require confirmation.

Example:

```text
Restore V10?

This will restore the working tree to the state
represented by Git commit 3fa921.

Current state:
V14

A safety backup should be created before restoration.

[Cancel]
[Restore]
```

Preferred safe workflow:

```text
1. Ensure working tree state is understood.
2. Create backup/stash if appropriate.
3. Confirm target Git commit.
4. Perform restoration.
5. Verify resulting HEAD/worktree.
6. Report result.
```

Do not silently execute:

```bash
git reset --hard
```

without explicit confirmation.

A safer implementation may initially provide:

```text
restore preview
```

and leave destructive restoration to an explicit CLI command.

---

# 38. Databricks Architecture

Databricks is the analytics layer.

Local SQLite:

```text
operational project state
```

Databricks:

```text
cross-version analytics
development telemetry
trend analysis
aggregations
AI/agent observability
```

Flow:

```text
DevelopmentVersion
        ↓
DatabricksAdapter
        ↓
Databricks
        ↓
SQL / analytics
        ↓
Development intelligence
```

---

# 39. Databricks Data Model

Recommended logical tables:

```text
projects
development_versions
development_events
features
tests
metrics
agent_sessions
```

The exact physical implementation may use Delta tables.

For example:

```text
devmemory.projects
devmemory.development_versions
devmemory.development_events
devmemory.features
devmemory.tests
devmemory.metrics
devmemory.agent_sessions
```

---

# 40. Databricks Version Record

Example:

```json
{
  "project_id": "vision-ai",
  "version_id": "V14",
  "checkpoint_id": "abc123",
  "agent": "Claude Code",
  "intent": "Improve inference performance",
  "git_commit": "a72c91",
  "parent_commit": "7fa91c",
  "feature": "Inference",
  "status": "SUCCESS",
  "tests_passed": 143,
  "tests_failed": 5,
  "timestamp": "2026-09-06T01:30:00Z"
}
```

Metrics may be stored in a separate normalized table.

---

# 41. Databricks Analytics

The dashboard or demo should be able to answer questions such as:

```text
Which versions caused regressions?

Which features required the most attempts?

Which files change most frequently?

How many AI-assisted changes succeeded?

Which changes improved latency?

Which changes reduced test pass rate?

What is the project's development trend?
```

These should be demonstrated through actual queries where possible.

Do not merely send data to Databricks and claim "analytics."

---

# 42. Databricks Agent Observability

If suitable Databricks capabilities are available, represent development as a trace:

```text
Agent
  ↓
Prompt
  ↓
Tool activity
  ↓
Entire checkpoint
  ↓
Git commit
  ↓
Tests
  ↓
Result
```

For the hackathon, one meaningful trace or analytics workflow is better than many incomplete integrations.

Do not build an elaborate observability platform from scratch.

---

# 43. Configuration

Project configuration should live in:

```text
.devmemory/config.json
```

Example:

```json
{
  "project_id": "vision-ai",

  "entire": {
    "enabled": true
  },

  "tests": {
    "command": "pytest"
  },

  "metrics": {
    "source": null
  },

  "artifacts": {
    "enabled": true
  },

  "databricks": {
    "enabled": false
  }
}
```

Secrets should NOT be stored directly in project configuration.

Use environment variables.

Example:

```text
DATABRICKS_HOST
DATABRICKS_TOKEN
DATABRICKS_WAREHOUSE_ID
```

---

# 44. Environment Detection

DevMemory should inspect the project environment.

Potential information:

```text
OS
Python version
Git version
Entire version
agent
package manager
runtime
```

Environment metadata can be attached to Development Versions.

Example:

```json
{
  "python": "3.12",
  "os": "Windows",
  "git": "2.x",
  "entire": "0.10.x"
}
```

Do not collect unnecessary personal information.

---

# 45. CLI

Recommended commands:

```bash
devmemory init
devmemory status
devmemory checkpoint
devmemory history
devmemory show V7
devmemory diff V6 V7
devmemory compare V6 V7
devmemory search "authentication"
devmemory memory
devmemory context
devmemory restore V7
devmemory serve
devmemory databricks push
```

Commands should provide useful human-readable output.

Machine-readable JSON output can be added:

```bash
devmemory status --json
```

---

# 46. Initialization

Command:

```bash
devmemory init
```

Should:

```text
1. verify Git repository
2. create .devmemory/
3. create SQLite database
4. create config
5. detect Entire
6. detect agent integration
7. initialize schema
8. display setup summary
```

Example:

```text
DevMemory initialized.

Project:
vision-ai

Git:
✓ detected

Entire:
✓ detected

Agent:
✓ Claude Code

Database:
.devmemory/metadata.db

Run:
devmemory checkpoint
```

---

# 47. Project Status

Command:

```bash
devmemory status
```

Should show:

```text
Project:
VisionAI

Current version:
V14

Git:
a72c91

Entire:
abc123

Features:
8/10 complete

Latest status:
SUCCESS

Previous regression:
V12

Databricks:
Connected
```

---

# 48. Search Architecture

Search should initially operate over SQLite.

Searchable fields:

```text
version_id
intent
feature
status
agent
changed_files
analysis
recommendation
error messages
metric names
```

Later, full-text search or embeddings can be introduced.

Do not add Elasticsearch, OpenSearch, or another external search engine for the initial implementation.

---

# 49. Entire Graph Integration

Entire Graph should be implemented as an optional impact-analysis adapter.

Potential flow:

```text
Git changed files
       ↓
Entire Graph
       ↓
related components
       ↓
impact summary
       ↓
Development Version
```

Example:

```text
Changed:
auth.py

Potential impact:
middleware.py
UserService
OrdersAPI
PaymentAPI
```

If graph functionality cannot be reliably accessed in the current environment, the system should still work without it.

The core product must not depend on the graph.

---

# 50. Error Handling

External systems can fail.

Examples:

```text
Entire unavailable
Git unavailable
tests fail
Databricks unavailable
LLM unavailable
artifact creation fails
```

The system should distinguish:

```text
development failure
```

from:

```text
DevMemory integration failure
```

Example:

```text
Tests:
FAILED

DevMemory:
Version created successfully.

Status:
ERROR
```

versus:

```text
Databricks:
UPLOAD FAILED

Local version:
Successfully created.

Databricks sync:
PENDING
```

A cloud integration failure should not destroy local development history.

---

# 51. Offline-First Behavior

Local DevMemory should work without Databricks.

Expected:

```text
Git
+
Entire
+
SQLite
+
Dashboard
```

can operate locally.

Databricks is an enhancement/analytics layer.

If Databricks is unavailable:

```text
create local version
queue/surface failed sync
continue working
```

Do not make cloud connectivity a hard dependency for basic functionality.

---

# 52. Security

Do not store secrets in:

```text
SQLite
Git commits
Development Version metadata
Git trailers
dashboard HTML
```

Databricks credentials should come from environment variables or secure configuration.

The dashboard is initially local.

If later exposed remotely, authentication and authorization will be required.

---

# 53. Privacy

AI development sessions may contain sensitive project information.

DevMemory should minimize duplication.

Preferred:

```text
Entire checkpoint reference
```

rather than:

```text
entire raw AI transcript
```

Databricks should receive normalized telemetry rather than unrestricted source code or complete AI conversations unless explicitly configured.

---

# 54. Dependency Philosophy

Keep dependencies minimal.

Likely dependencies:

```text
pydantic
typer
fastapi
uvicorn
```

Potentially:

```text
httpx
sqlalchemy
```

For Databricks, use the appropriate official Databricks client/SDK only when needed.

For LLM analysis, use a provider abstraction rather than coupling the core system to one model provider.

Do not install large frameworks without a concrete requirement.

---

# 55. Testing Strategy

Testing should cover:

## Unit tests

```text
Git parsing
checkpoint parsing
status calculation
regression detection
feature detection
version numbering
database repositories
```

## Integration tests

```text
Git repository
Entire-enabled repository
checkpoint association
version creation
artifact generation
FastAPI endpoints
```

## End-to-end test

Simulate:

```text
Git commit
    ↓
Entire checkpoint reference
    ↓
devmemory checkpoint
    ↓
SQLite
    ↓
API
    ↓
dashboard
```

---

# 56. Demo Environment

Create a small sample project:

```text
examples/demo-project/
```

It should be intentionally simple.

Example:

```text
demo-project/
├── app.py
├── calculator.py
├── tests/
│   └── test_calculator.py
└── README.md
```

Use it to demonstrate:

```text
Version 1
Initial implementation

Version 2
Feature improvement

Version 3
Regression

Version 4
Fix
```

The demo should show development memory.

---

# 57. Recommended Demo Story

The strongest demonstration is:

### Step 1

Start with a project.

```text
V1
Authentication implemented
```

### Step 2

Ask Claude Code to improve authentication.

Entire captures the AI development session.

Git records the change.

### Step 3

Create a DevMemory version.

```text
V2
SUCCESS
```

### Step 4

Ask Claude Code to change token expiry.

The change causes tests to fail.

Create:

```text
V3
REGRESSION
```

### Step 5

Ask the AI:

```text
How should I modify token expiry?
```

DevMemory provides:

```text
Previous attempt:
V3

This approach caused test failures.

Recommendation:
Avoid repeating the same configuration.
```

### Step 6

Show the dashboard.

Show:

```text
timeline
Entire checkpoint
Git diff
tests
regression
previous attempts
```

### Step 7

Show Databricks analytics.

Example:

```text
3 development versions
1 regression
2 successful changes
Authentication:
3 attempts
```

### Step 8

Show AI context/MCP.

The AI can retrieve the same development memory.

This creates the complete story:

```text
AI session
   ↓
Entire
   ↓
Git
   ↓
DevMemory
   ↓
Databricks
   ↓
Dashboard
   ↓
Future AI
```

---

# 58. Implementation Order

Build in vertical slices.

## Slice 1

```text
CLI
+
Git
+
Entire
+
DevelopmentVersion
+
SQLite
```

Goal:

```bash
devmemory checkpoint
```

creates a real version.

---

## Slice 2

Add:

```text
FastAPI
+
dashboard
```

Goal:

```bash
devmemory serve
```

shows the version.

---

## Slice 3

Add:

```text
tests
+
metrics
+
status
+
regression
```

Goal:

```text
version
+
result
```

---

## Slice 4

Add:

```text
development memory
+
previous attempts
```

Goal:

```text
AI/developer can see failed approaches.
```

---

## Slice 5

Add:

```text
Databricks
```

Goal:

```text
real development data
→ Databricks
→ meaningful analytics
```

---

## Slice 6

Add:

```text
AI context
+
MCP
```

Goal:

```text
future AI agent
→ DevMemory
→ project history
```

---

## Slice 7

Add:

```text
Entire Graph
+
impact analysis
```

Only after the core system is stable.

---

# 59. Definition of Done

The first major milestone is reached when this works:

```text
Existing Git project
        ↓
Entire enabled
        ↓
Claude Code development
        ↓
Git commit
        ↓
devmemory checkpoint
        ↓
Development Version created
        ↓
Entire checkpoint linked
        ↓
Git diff captured
        ↓
SQLite persisted
        ↓
Dashboard displays version
```

The second milestone:

```text
Version
+
tests
+
metrics
+
status
+
regression
```

The third milestone:

```text
Version
→ Databricks
→ analytics
```

The fourth milestone:

```text
AI agent
→ MCP
→ development memory
```

---

# 60. Architectural North Star

The system should always preserve this relationship:

```text
                 USER INTENT
                      │
                      ↓
                 AI AGENT
                      │
                      ↓
              ENTIRE CHECKPOINT
                      │
                      ↓
                   GIT
                      │
             ┌────────┴────────┐
             ↓                 ↓
        CODE DIFF          COMMIT
             │                 │
             └────────┬────────┘
                      ↓
               DEVMEMORY VERSION
                      │
        ┌─────────────┼─────────────┐
        ↓             ↓             ↓
      TESTS        METRICS       FEATURE
        │             │             │
        └─────────────┼─────────────┘
                      ↓
                  ANALYSIS
                      ↓
              DEVELOPMENT MEMORY
                      │
             ┌────────┴────────┐
             ↓                 ↓
        HUMAN DASHBOARD     FUTURE AI
             │                 │
             ↓                 ↓
         UNDERSTANDING      CONTEXT
```

The architectural purpose of DevMemory is to make this relationship persistent, searchable, understandable, and reusable.

---

# 61. Critical Constraint

Do not allow the architecture to drift into:

```text
IDE
Git replacement
MLflow clone
custom VCS
custom agent
custom container platform
microservices platform
```

If an implementation decision makes DevMemory more complicated without improving the core development-memory workflow, prefer the simpler option.

The product's unique value is the connection:

```text
Entire
+
Git
+
Results
+
Development Memory
```

Everything else supports that relationship.
