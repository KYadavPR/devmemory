# DevMemory — Project Specification

## 1. Project Overview

DevMemory is a development-memory and version-intelligence platform for AI-assisted software development.

The goal is to create a reusable Python package/platform that can be integrated into an existing software project and work alongside existing development tools.

DevMemory is NOT:

- an IDE
- a Git replacement
- an MLflow replacement
- an AI coding agent
- a code editor
- a custom version-control system

Developers should continue using their preferred development environment, including:

- VS Code
- Cursor
- Antigravity
- Codex
- Claude Code
- Gemini CLI
- Kiro
- terminal
- CI/CD
- other AI coding environments

DevMemory sits alongside these tools as a development-memory layer.

---

# 2. Core Concept

The central concept is:

```text
AI/developer intent
        ↓
AI agent activity
        ↓
Entire Checkpoint
        ↓
Git changes
        ↓
tests / metrics / results
        ↓
development version
        ↓
project history + analytics + artifacts
        ↓
future developer / AI agent can understand what happened
```

The system should allow a developer or future AI agent to understand the project from A-Z:

* What was requested?
* Why was the change made?
* Which AI agent worked on it?
* What did the AI agent do?
* Which files changed?
* Which exact lines changed?
* What code was added?
* What code was removed?
* Which components were affected?
* What tests were executed?
* What was the result?
* Did the feature succeed?
* Did it partially succeed?
* Did it cause an error?
* Did it improve or reduce performance/accuracy?
* What was the project status after the change?
* Which previous approaches were attempted?
* Which approaches failed?
* What should not be repeated?
* What is still incomplete?
* What changed between two versions?
* Can an earlier project state be restored?

---

# 3. Entire Integration

Entire must be an essential part of the project because the Build Entire hackathon specifically requires meaningful use of Entire Checkpoint context.

Entire must NOT be treated as an optional integration.

The system should use Entire Checkpoints as the development-context source for AI-assisted changes.

Git tells us exactly what code changed.

Entire provides the AI-assisted development session/context surrounding the change.

For example, an Entire checkpoint may allow us to associate a change with information such as:

* original developer prompt
* AI agent response
* development session
* files involved
* tool activity
* checkpoint ID
* checkpoint location/reference
* timestamps
* development context

DevMemory should NOT attempt to duplicate every piece of Entire's internal data.

Instead, DevMemory should store a reference to the Entire checkpoint and the normalized information required by DevMemory.

Example:

```json
{
  "checkpoint_id": "checkpoint-abc123",
  "checkpoint_location": "...",
  "agent": "Codex",
  "timestamp": "...",
  "intent": "Improve image classification accuracy"
}
```

The complete raw context remains associated with the Entire checkpoint.

The DevMemory version should therefore be able to represent:

```text
Version 7
    ↓
Entire Checkpoint #abc123
    ↓
Original AI interaction
    ↓
Files changed
    ↓
Git diff
    ↓
Test results
    ↓
Metrics
    ↓
Final development result
```

If a user needs complete details, they should be able to navigate from the DevMemory version record back to the corresponding Entire checkpoint.

---

# 4. Git Integration

Git provides the exact code-level history.

DevMemory must NOT implement its own version-control system.

Git should be used as the source for:

* commit
* parent commit
* changed files
* added files
* deleted files
* renamed files
* line-level changes
* diff
* repository history

Example:

```diff
V7

model.py

- learning_rate = 0.001
+ learning_rate = 0.0001

+ scheduler = ReduceLROnPlateau(...)
```

For every Development Version, store references such as:

```text
version_id
git_commit
parent_commit
```

Then:

```text
V6 → V7
```

can be reconstructed using:

```bash
git diff <V6 commit> <V7 commit>
```

This allows DevMemory to understand exactly what changed.

---

# 5. Development Version

A Development Version must NOT simply be a Git commit.

A Development Version is a complete development record.

Example:

```text
VERSION 7
--------------------------------

Project:
VisionAI

Intent:
"Improve image classification accuracy"

Agent:
Codex

Entire Checkpoint:
checkpoint-abc123

Git Commit:
7fa91c

Files Changed:
model.py
preprocessing.py
train.py

Code Changes:
+142 lines
-37 lines

Feature:
Image Classification

Tests:
143 passed
5 failed

Accuracy:
89.2% → 93.4%

Status:
SUCCESS

Project Completion:
82%

AI Analysis:
"The preprocessing modification improved classification accuracy."

Recommendation:
"Keep this approach."
```

Every meaningful development change should become a Development Version.

---

# 6. Version States

The system should support different outcomes.

Possible states:

```text
SUCCESS
PARTIAL_SUCCESS
ERROR
REGRESSION
IN_PROGRESS
NEEDS_REVIEW
```

For ML/AI projects, metrics can be used.

Example:

```text
Accuracy:

V1 = 84%
V2 = 89%
V3 = 73%
V4 = 93%
```

The system can identify:

```text
V2 = improvement
V3 = regression
V4 = improvement
```

For normal software projects, other signals can be used:

* tests passed
* tests failed
* build success
* lint errors
* API tests
* performance
* latency
* error count

DevMemory must NOT assume every project is an ML project.

---

# 7. Feature Tracking

DevMemory should maintain feature-level status.

Example:

```text
PROJECT FEATURES

Authentication       COMPLETE
Image Classification COMPLETE
GPU Inference        PARTIAL
Notifications        IN PROGRESS
Payment              FAILED
```

Each feature should have its own history.

Example:

```text
Image Classification

V3
Accuracy: 72%
Status: SUCCESS

V4
Accuracy: 81%
Status: SUCCESS

V5
Accuracy: 65%
Status: REGRESSION

V6
Accuracy: 89%
Status: SUCCESS

V7
Accuracy: 91.4%
Status: SUCCESS
```

This allows users to understand both:

1. overall project evolution
2. individual feature evolution

---

# 8. Development Memory

Development memory is one of the most important features.

The system should remember previous development attempts.

Example:

```text
V3

Change:
learning_rate = 0.0001

Result:
Accuracy dropped from 89% to 72%

Status:
REGRESSION

Conclusion:
This configuration caused a significant performance regression.
```

Later, an AI agent may suggest:

```text
"Let's use learning_rate=0.0001."
```

DevMemory should be able to provide context:

```text
WARNING

This approach was already attempted in V3.

Result:
Accuracy decreased from 89% to 72%.

Recommendation:
Avoid repeating this configuration.
```

The purpose is to help future developers and AI agents avoid repeating failed approaches.

---

# 9. AI Context API / MCP

DevMemory should expose project history and development memory to AI agents.

An AI agent should be able to ask:

```text
What is the current project status?

What features are incomplete?

What approaches have already been tried?

What changes caused regressions?

What was changed in the previous version?

Why was this file changed?

What did the previous AI agent attempt?

What is the latest Entire checkpoint?

What are the important project decisions?
```

Potential API/MCP tools:

```text
get_project_status()
get_current_version()
get_version_history()
get_version_diff(version_a, version_b)
get_feature_status()
get_previous_attempts()
get_failed_changes()
get_checkpoint_context()
get_project_context()
```

Example response:

```json
{
  "current_version": 14,
  "project_completion": 82,
  "completed_features": [
    "authentication",
    "image classification"
  ],
  "incomplete_features": [
    "notifications"
  ],
  "previous_failures": [
    {
      "version": 12,
      "change": "learning_rate=0.0001",
      "result": "accuracy dropped from 91.7% to 76.3%"
    }
  ]
}
```

This context can be provided to an AI coding agent before it makes another change.

---

# 10. Artifact Storage

DevMemory should store artifacts associated with Development Versions.

Example:

```text
V1
  └── snapshot-v1.tar.gz

V2
  └── snapshot-v2.tar.gz

V3
  └── snapshot-v3.tar.gz
```

An artifact may contain:

```text
project/
    model.py
    preprocessing.py
    train.py
    requirements.txt
    tests/
```

Do NOT create a full Docker container for every version in the initial implementation.

For the MVP, use:

* Git commits
* project archives/snapshots

Optionally store environment metadata:

```text
Python version
OS
dependency versions
package manager
requirements.txt/package.json/etc.
```

Docker/containerized reproducibility can be a future enhancement.

---

# 11. Restore / Revert

The user should be able to select an earlier Development Version.

Example:

```text
Current: V14

User selects:
Restore V10
```

DevMemory should use Git and/or the stored snapshot to restore the project.

The web UI should clearly explain:

```text
Restore Version 10

This will return the source code to the V10 state.
```

Do NOT build a custom version-control system.

Use Git checkout/reset or another safe restoration mechanism.

Restoration must be designed carefully to avoid accidental destructive operations.

---

# 12. Searchable Project History

The web application should allow users to search the development history.

Potential search terms:

```text
authentication
model.py
error
checkpoint
Codex
learning rate
failed
accuracy
payment
API
```

Example:

```text
Search:
"authentication"
```

Results:

```text
V3
Added JWT authentication

V7
Modified authentication middleware

V9
Fixed token expiration
```

Each result should link to the corresponding Development Version and, where applicable, the associated Entire checkpoint.

---

# 13. Version Comparison

The web UI should support:

```text
Compare V6 → V7
```

Example:

```text
FILES

+ preprocessing.py
~ model.py
~ train.py

CODE

+142 lines
-37 lines

METRICS

Accuracy:
89.2% → 93.4%

Latency:
420ms → 310ms

TESTS:

138 passed → 143 passed

RESULT:

SUCCESS
```

Version comparison should combine:

* Git diff
* files changed
* tests
* metrics
* status
* development context

---

# 14. A-Z Development Lineage

The platform should connect the complete development chain:

```text
USER INTENT
     ↓
AI AGENT
     ↓
ENTIRE CHECKPOINT
     ↓
GIT COMMIT
     ↓
GIT DIFF
     ↓
FILES / COMPONENTS AFFECTED
     ↓
TESTS
     ↓
METRICS / RESULTS
     ↓
DEVELOPMENT VERSION
     ↓
AI ANALYSIS
     ↓
PROJECT MEMORY
     ↓
FUTURE AI / DEVELOPER
```

The user should be able to trace backwards and forwards.

Example:

```text
Why was this line changed?

    ↓

Entire checkpoint

    ↓

AI's original task

    ↓

AI's response/actions

    ↓

Git diff

    ↓

Result

    ↓

Decision
```

This complete lineage is the core Development Intelligence concept.

---

# 15. Entire Graph

Where possible, integrate Entire Graph/codebase relationships.

The graph should not merely display raw graph output.

It should answer useful questions.

Example:

```text
V14

Changed:
auth.py

Graph impact:

auth.py
   ↓
middleware.py
   ↓
UserService
   ↓
OrdersAPI
   ↓
PaymentAPI
```

The dashboard could show:

```text
Impact:
5 modules
12 functions
3 API endpoints
```

The primary question is:

```text
"What else could this change affect?"
```

The MVP should prioritize the core checkpoint/version workflow before building an extremely sophisticated graph engine.

---

# 16. Databricks

Databricks should have a meaningful role.

Do NOT simply claim that Databricks stores data.

Use Databricks for development intelligence and analytics.

DevMemory should send normalized development records/events to Databricks.

Potential fields:

```text
project_id
version_id
checkpoint_id
agent
intent
feature
status
git_commit
files_changed
tests_passed
tests_failed
metrics
timestamp
duration
errors
regression
recommendation
```

Potential tables:

```text
projects
development_versions
development_events
features
tests
metrics
agent_sessions
```

Databricks should answer questions such as:

```text
Which versions caused regressions?

Which changes improved performance?

Which features required the most attempts?

How many AI-assisted changes were successful?

Which files/modules change most frequently?

Which agent sessions generated the most failed changes?

What is the project development trend?
```

---

# 17. Databricks AI / Agent Observability

Where practical, use Databricks capabilities for AI/agent observability and analysis.

Represent a trace such as:

```text
AI Agent
   ↓
Prompt
   ↓
Tool activity
   ↓
Files changed
   ↓
Entire checkpoint
   ↓
Git commit
   ↓
Tests
   ↓
Result
```

This can be stored/analyzed as development telemetry.

If Databricks provides suitable tracing/evaluation capabilities, use them meaningfully rather than adding a superficial API call.

For the initial implementation, prioritize one working Databricks flow over attempting to integrate every Databricks feature.

---

# 18. Normalized Event Model

The architecture should use adapters.

Different sources produce different formats.

Create a normalized internal model.

Example:

```json
{
  "project_id": "...",
  "timestamp": "...",
  "source": "entire",
  "checkpoint_id": "...",
  "agent": "Codex",
  "intent": "...",
  "git_commit": "...",
  "parent_commit": "...",
  "changed_files": [],
  "diff": "...",
  "feature": "...",
  "status": "...",
  "tests": {},
  "metrics": {},
  "errors": [],
  "artifact": "...",
  "analysis": {}
}
```

Potential adapters:

```text
EntireAdapter
GitAdapter
DatabricksAdapter
TestAdapter
FilesystemAdapter
AgentAdapter
```

The purpose is to allow future integrations without changing the core platform.

---

# 19. Python Package

The project should behave as a reusable Python package.

Possible package names:

```text
devmemory
devtrace
projectmemory
```

The exact name can be decided during implementation.

Conceptual package structure:

```text
devmemory/
│
├── pyproject.toml
│
├── devmemory/
│   ├── __init__.py
│   ├── config.py
│   ├── project.py
│   ├── version.py
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── entire.py
│   │   ├── git.py
│   │   └── databricks.py
│   │
│   ├── collector/
│   │   ├── __init__.py
│   │   └── events.py
│   │
│   ├── intelligence/
│   │   ├── analyzer.py
│   │   ├── regression.py
│   │   └── features.py
│   │
│   ├── storage/
│   │   ├── metadata.py
│   │   └── artifacts.py
│   │
│   ├── context/
│   │   └── ai_context.py
│   │
│   ├── mcp/
│   │   └── server.py
│   │
│   └── web/
│       └── app.py
│
└── cli.py
```

This structure may be simplified where appropriate.

---

# 20. Package API

The package should be simple to use.

Example:

```python
import devmemory

project = devmemory.init()

project.checkpoint()

project.status()

project.history()

project.diff("v3", "v4")

project.restore("v3")

project.context()
```

Potential CLI:

```bash
devmemory init

devmemory checkpoint

devmemory status

devmemory history

devmemory diff V3 V4

devmemory restore V3

devmemory context

devmemory serve
```

The exact API can be improved, but simplicity is important.

---

# 21. Local Project Storage

DevMemory should create a hidden project directory:

```text
.devmemory/
```

Possible contents:

```text
.devmemory/
│
├── config.json
├── metadata.db
├── versions/
│   ├── V1.json
│   ├── V2.json
│   └── V3.json
│
├── artifacts/
│   ├── V1.tar.gz
│   └── V2.tar.gz
│
└── cache/
```

The exact structure may be changed if a better implementation is identified.

SQLite can be used for local metadata.

Databricks can serve as the cloud analytics layer.

Git remains the source of truth for source-code history.

Entire remains the source of truth/reference for AI checkpoint context.

---

# 22. Web Application

The package should include or launch a local web server.

Example:

```bash
devmemory serve
```

Then:

```text
http://localhost:8000
```

The dashboard should resemble an experiment/version tracking platform.

Main sections:

```text
Project Overview
Version Timeline
Version Details
Version Comparison
Feature Status
Development Trace
Search
Previous Attempts
Project Graph
Restore
```

Example overview:

```text
PROJECT: VisionAI

Current Version: V14

Completion: 82%

Features: 8/10

Tests: 143/148

Accuracy: 93.4%

Recent Versions:

V14  SUCCESS       93.4%
V13  SUCCESS       91.7%
V12  REGRESSION    84.2%
V11  SUCCESS       89.3%
```

---

# 23. Version Detail Page

When the user opens a Development Version, show:

```text
VERSION 14

Intent:
"Improve inference performance"

Agent:
Codex

Entire Checkpoint:
checkpoint-abc123

Git Commit:
a72c91

Files Changed:
inference.py
model.py
config.yaml

Diff:
exact Git diff

Tests:
143 passed
5 failed

Metrics:
Accuracy: 93.4%
Latency: 280ms

Feature:
Inference

Status:
SUCCESS

AI Analysis:
"Inference latency improved by 30% while accuracy increased."

Impact:
4 modules affected

Recommendation:
"Keep this change."
```

---

# 24. Previous Attempt View

This should be one of the strongest product features.

Example:

```text
PREVIOUS ATTEMPT DETECTED

Version:
V12

Change:
learning_rate = 0.0001

Result:
Accuracy 91.7% → 76.3%

Status:
REGRESSION

Recommendation:
Avoid repeating this configuration.
```

The system can identify similar previous attempts using stored metadata and AI analysis.

---

# 25. Documentation

A future feature can be "Living Documentation."

For the initial implementation, do not build a complex automatic documentation engine.

Instead, detect potentially affected documentation.

Example:

```text
Code changed:
auth.py

Potentially affected documentation:

README.md
API.md
ARCHITECTURE.md

Status:
NEEDS REVIEW
```

A future version can automatically propose documentation updates.

---

# 26. What NOT to Build

Do NOT build:

* a complete IDE
* a Git replacement
* a custom version-control engine
* a custom container engine
* a full MLflow replacement
* a new LLM
* a full code parser
* a full Docker orchestration platform
* support for every AI agent during the initial implementation
* a huge microservices architecture

Use existing tools wherever possible.

Preferred approach:

```text
Git
→ source-code history and diffs

Entire
→ AI development checkpoints/context

Databricks
→ analytics, development intelligence,
  telemetry/observability where useful

SQLite
→ local metadata

Filesystem/archive
→ project artifacts

LLM
→ semantic analysis of intent/results/history

MCP/API
→ AI-agent access

FastAPI/Flask
→ backend

React or simple HTML/JS
→ dashboard
```

---

# 27. Hackathon Alignment

The strongest alignment is E1:

"Build a Checkpoint-Native Developer Experience."

DevMemory uses actual Entire Checkpoint context as an essential input.

The checkpoint is connected to:

```text
intent
AI interaction
Git changes
results
version
project state
future AI context
```

The project also has E2 potential through Entire Graph:

```text
changed component
    ↓
dependency graph
    ↓
affected components
    ↓
impact analysis
```

The project also has E3 potential because it can expose development memory/context to external AI agents through an API/MCP interface.

However, do not weaken the E1 alignment by treating Entire as just another optional connector.

Entire Checkpoints should be one of the central pillars of the architecture.

---

# 28. Product Positioning

Do NOT describe DevMemory as:

> "MLflow for code."

Do NOT describe it as:

> "another Git."

Do NOT describe it as:

> "an AI IDE."

Instead describe it as:

> "A development-memory and version-intelligence layer for AI-assisted software development."

Core statement:

```text
Git remembers what changed.

Entire remembers the AI-assisted development context.

DevMemory connects those changes with results,
metrics, feature status, project state and previous
attempts so that developers and future AI agents
can understand the complete development history.
```

Short pitch:

> "Understand your entire AI-assisted development journey: what changed, why it changed, what it affected, what happened as a result, and what should not be repeated."

---

# 29. Example End-to-End Flow

Start with:

```text
VisionAI/
```

Developer initializes:

```bash
devmemory init
```

Developer uses an AI coding agent.

Prompt:

```text
"Improve image classification accuracy."
```

The AI modifies:

```text
model.py
preprocessing.py
```

Entire captures the development checkpoint.

Git records the code changes.

The developer runs tests/project evaluation.

Result:

```text
Accuracy:
89.2% → 93.4%

Tests:
143 passed
```

Developer runs:

```bash
devmemory checkpoint
```

The package:

1. finds the relevant Entire checkpoint
2. records checkpoint ID/location
3. gets Git commit
4. gets parent commit
5. calculates Git diff
6. detects changed files
7. collects tests/metrics
8. identifies feature
9. determines status
10. analyzes the result
11. creates Version 7
12. stores metadata
13. stores/references artifacts
14. sends development data to Databricks
15. updates the web dashboard

Dashboard:

```text
V7

Intent:
Improve image classification accuracy

Entire:
checkpoint-abc123

Changes:
model.py
preprocessing.py

Diff:
+142 / -37

Accuracy:
89.2% → 93.4%

Tests:
143 passed

Status:
SUCCESS
```

Later, the AI tries:

```text
learning_rate = 0.0001
```

Version 8:

```text
Accuracy:
93.4% → 76.1%
```

Status:

```text
REGRESSION
```

The system stores:

```text
V8
failed approach
result
analysis
```

Later, an AI agent asks:

```text
"How can I improve the model?"
```

DevMemory returns:

```text
Previous attempts:

V8:
learning_rate=0.0001

Result:
Accuracy dropped from 93.4% to 76.1%

Recommendation:
Avoid repeating this configuration.
```

This demonstrates that DevMemory is not merely storing versions.

It is creating reusable development memory.

---

# 30. Final Technical Goal

Build a working platform with this complete flow:

```text
Existing Project
      ↓
AI Agent / IDE
      ↓
Entire Checkpoint
      ↓
DevMemory Python Package
      ↓
Git + Entire + tests + metrics
      ↓
Normalized Development Event
      ↓
Version Registry
      ↓
Databricks analytics
      ↓
Web Dashboard
      ↓
AI Context / MCP
      ↓
Future Developer / AI Agent
```

The most important end-to-end demonstration must work.

A single development change should be able to travel through:

```text
Entire
  ↓
Git
  ↓
Development Version
  ↓
Databricks
  ↓
Dashboard
  ↓
AI Context
```

---

# 31. Implementation Philosophy

We have more than six hours available.

Therefore, do NOT artificially cripple the architecture.

However, development must remain incremental.

The priority order is:

```text
PRIORITY 1
Core data model

PRIORITY 2
Entire checkpoint integration

PRIORITY 3
Git integration

PRIORITY 4
Development Version creation

PRIORITY 5
Local persistence

PRIORITY 6
Dashboard

PRIORITY 7
Tests/results

PRIORITY 8
Feature tracking

PRIORITY 9
Previous-attempt memory

PRIORITY 10
Artifact snapshots

PRIORITY 11
Version comparison

PRIORITY 12
Databricks analytics

PRIORITY 13
AI context API

PRIORITY 14
MCP

PRIORITY 15
Entire Graph / impact analysis

PRIORITY 16
Search

PRIORITY 17
Restore

PRIORITY 18
Living documentation

PRIORITY 19
Additional agent integrations
```

Do not build everything simultaneously.

Always maintain a working end-to-end path.

The architecture should be modular enough to expand after the first vertical slice is working.

---

# 32. Architectural Principle

The core system should be built around this relationship:

```text
                DEVELOPMENT VERSION
                         │
        ┌────────────────┼────────────────┐
        ↓                ↓                ↓
   ENTIRE CONTEXT      GIT              RESULTS
        │                │                │
        ↓                ↓                ↓
 AI intent/session    code diff      tests/metrics
        │                │                │
        └────────────────┼────────────────┘
                         ↓
                 DEVELOPMENT MEMORY
                         ↓
              ┌──────────┴──────────┐
              ↓                     ↓
          HUMAN UI              AI CONTEXT
              ↓                     ↓
       developer understands    future agent
       project history          understands history
```

DevMemory's value comes from connecting these sources rather than replacing them.

---

# 33. Success Criteria

The project should be considered successful when a fresh developer can install DevMemory into a project, initialize it, perform an AI-assisted development task using their normal environment, and then use DevMemory to understand:

1. What was requested.
2. Which AI agent performed the work.
3. Which Entire checkpoint contains the development context.
4. Which Git commit represents the resulting change.
5. Which files changed.
6. What the exact diff was.
7. What tests/results occurred.
8. Whether the change succeeded or regressed.
9. Which project/feature state resulted.
10. What previous attempts are relevant.
11. What the next AI agent should know.

The system should feel like **memory for the development process**, not another place where development happens.
