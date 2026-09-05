# Entire Integration Specification

## 1. Purpose

Entire is a core component of DevMemory.

DevMemory must use Entire Checkpoints to preserve and connect the AI-assisted development context surrounding a code change.

The goal is NOT to recreate Entire.

The goal is to reference and consume the relevant Entire checkpoint associated with a development version.

The relationship is:

```text
Developer / AI Agent
        ↓
AI-assisted development session
        ↓
Entire Checkpoint
        ↓
Git commit
        ↓
DevMemory Development Version
```

Git provides the exact source-code changes.

Entire provides the surrounding AI-development context.

DevMemory connects both.

---

# 2. Core Principle

Never treat Entire as an optional metadata source.

A development version should preferably contain an Entire checkpoint reference.

Example:

```json
{
  "version_id": "v7",
  "git_commit": "7fa91c",
  "parent_commit": "91ac21",
  "entire_checkpoint_id": "checkpoint-abc123",
  "agent": "Claude Code",
  "intent": "Improve image classification accuracy"
}
```

DevMemory does NOT need to duplicate the complete Entire checkpoint.

Instead:

```text
DevMemory
    |
    └── checkpoint reference
             |
             ↓
         Entire Checkpoint
             |
             ├── AI session
             ├── original intent
             ├── agent activity
             ├── tool activity
             └── development context
```

---

# 3. Entire CLI

The implementation must first inspect the locally installed Entire CLI rather than assuming command names or output formats.

The system should detect whether Entire is installed:

```bash
entire --version
```

If unavailable:

```text
Entire CLI not found.

Install Entire and enable it in this repository before creating
AI-assisted development checkpoints.
```

DevMemory should not silently fabricate checkpoint information.

---

# 4. Repository Requirements

Entire must be enabled in the Git repository.

Typical setup:

```bash
git init
entire enable
```

Entire creates its project configuration/hooks.

These files should remain part of the repository where appropriate.

DevMemory should detect whether Entire appears to be configured.

---

# 5. Checkpoint Discovery

The most important technical problem is:

> Given a Git commit, which Entire checkpoint produced or corresponds to that development change?

DevMemory should solve this using the actual data exposed by the installed Entire CLI/repository.

Do NOT assume the checkpoint ID is embedded directly inside a Git commit unless verified.

The implementation should inspect:

```bash
entire --help
entire status
entire <relevant checkpoint/history command>
```

and inspect the repository's Entire metadata/configuration.

The adapter should encapsulate all Entire-specific behavior.

Example:

```python
class EntireAdapter:

    def is_available(self) -> bool:
        ...

    def is_enabled(self) -> bool:
        ...

    def list_checkpoints(self) -> list:
        ...

    def get_checkpoint(self, checkpoint_id: str):
        ...

    def find_checkpoint_for_commit(self, commit_sha: str):
        ...

    def get_checkpoint_context(self, checkpoint_id: str):
        ...
```

The rest of DevMemory must not depend directly on Entire CLI implementation details.

---

# 6. Entire Adapter

Create:

```text
devmemory/
    adapters/
        entire.py
```

The adapter should be responsible for:

1. Detecting Entire.
2. Detecting whether Entire is enabled.
3. Discovering checkpoints.
4. Extracting checkpoint identifiers.
5. Extracting checkpoint metadata available through supported interfaces.
6. Associating checkpoints with Git commits.
7. Providing a link/reference to the checkpoint where possible.
8. Returning normalized information to DevMemory.

Example normalized result:

```python
@dataclass
class EntireCheckpoint:
    checkpoint_id: str
    location: str | None
    agent: str | None
    intent: str | None
    timestamp: str | None
    git_commit: str | None
    metadata: dict
```

Do not make the core application depend on every possible Entire field.

---

# 7. Source of Truth

The system should maintain clear ownership.

## Entire owns

AI-assisted development context:

* AI session context
* checkpoint information
* agent interaction context
* development-session metadata
* checkpoint-specific information

## Git owns

Code history:

* commits
* branches
* parent commits
* diffs
* changed files
* renames
* additions
* deletions

## DevMemory owns

Development intelligence:

* development versions
* feature associations
* test results
* metrics
* status
* regression detection
* previous-attempt analysis
* project-level memory
* normalized development events
* dashboard presentation

## Databricks owns

Analytics and aggregated development telemetry.

---

# 8. Checkpoint Reference

A DevMemory version should store a lightweight checkpoint reference.

Example:

```json
{
  "checkpoint_id": "abc123",
  "location": "entire://checkpoint/abc123",
  "source": "entire"
}
```

If Entire provides a browser-accessible URL, store it.

If not, store the CLI/repository reference required to locate it.

Do not copy the entire checkpoint into SQLite unless necessary.

---

# 9. Checkpoint Context

When available, DevMemory should normalize useful context.

Example:

```python
{
    "checkpoint_id": "abc123",
    "agent": "Claude Code",
    "intent": "Improve authentication middleware",
    "timestamp": "2026-09-06T01:20:00Z",
    "git_commit": "7fa91c",
    "metadata": {
        "source": "entire"
    }
}
```

The raw Entire checkpoint remains outside DevMemory.

DevMemory stores only the information necessary for:

* displaying development history
* searching
* analytics
* AI context
* linking back to Entire

---

# 10. Checkpoint-to-Commit Association

This is critical.

The system should establish:

```text
Entire Checkpoint
        ↓
Development session
        ↓
Git commit
```

The association algorithm should be implemented inside `EntireAdapter`.

Possible evidence sources include:

1. Explicit checkpoint-to-commit relationship exposed by Entire.
2. Entire metadata.
3. Repository metadata.
4. Checkpoint timestamp + Git commit timestamp.
5. Checkpoint-associated branch/session information.

Timestamp matching should only be used as a fallback.

Never claim a checkpoint is associated with a commit solely because their timestamps are close if stronger evidence exists.

The association should have a confidence value.

Example:

```python
{
    "checkpoint_id": "abc123",
    "git_commit": "7fa91c",
    "confidence": 1.0,
    "method": "explicit"
}
```

Fallback:

```python
{
    "checkpoint_id": "abc123",
    "git_commit": "7fa91c",
    "confidence": 0.65,
    "method": "timestamp_proximity"
}
```

The UI should indicate uncertain associations.

---

# 11. Checkpoint Creation

DevMemory should NOT automatically recreate Entire's checkpoint mechanism.

If Entire already provides checkpoint creation through its workflow, DevMemory should use that.

The intended workflow is:

```text
AI coding session
        ↓
Entire captures checkpoint
        ↓
Developer commits changes
        ↓
devmemory checkpoint
        ↓
DevMemory discovers the Entire checkpoint
        ↓
DevMemory creates Development Version
```

If the installed Entire CLI provides a supported command for explicitly creating/finalizing a checkpoint, the DevMemory CLI may expose a wrapper.

Example:

```bash
devmemory checkpoint
```

could:

1. Inspect Git state.
2. Discover relevant Entire checkpoint.
3. Collect Git metadata.
4. Collect tests/metrics.
5. Create the DevMemory version.

Do not duplicate Entire's internal checkpoint logic.

---

# 12. Missing Checkpoint Behavior

Entire integration should be strict enough to preserve hackathon alignment.

If the user runs:

```bash
devmemory checkpoint
```

and no Entire checkpoint can be associated with the change, show:

```text
No Entire checkpoint could be associated with this development change.

DevMemory versions are checkpoint-aware.

Possible reasons:
- Entire is not enabled
- no AI-assisted checkpoint exists
- the checkpoint could not be associated with the current commit
- the repository state is incomplete
```

Do not invent:

```text
checkpoint_id = "unknown"
```

and pretend the integration succeeded.

However, support an explicit development mode if needed:

```bash
devmemory checkpoint --allow-no-entire
```

This may create a version without checkpoint context.

The dashboard should clearly mark it:

```text
Entire Context
NOT AVAILABLE
```

This is a fallback, not the primary workflow.

---

# 13. Multiple Checkpoints

A single development version may potentially correspond to more than one checkpoint.

The data model should therefore not assume that:

```text
version → exactly one checkpoint
```

is always true.

Prefer:

```text
version
   |
   └── checkpoint references
          ├── checkpoint A
          └── checkpoint B
```

For the MVP, the UI may display the primary checkpoint.

Internally, support a list:

```python
checkpoint_ids: list[str]
```

---

# 14. Checkpoint Metadata in the Dashboard

Version detail should contain an Entire section.

Example:

```text
ENTIRE CHECKPOINT

Checkpoint:
abc123

Agent:
Claude Code

Intent:
Improve image classification accuracy

Timestamp:
06 Sep 2026, 01:20

Git Commit:
7fa91c

Association:
Explicit

[View Entire Checkpoint]
```

If a direct link is unavailable:

```text
Checkpoint:
abc123

Reference:
Local Entire checkpoint

[Open checkpoint instructions]
```

Do not show fake links.

---

# 15. Development Trace

The dashboard should visualize the complete lineage:

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
TESTS
     ↓
METRICS
     ↓
DEVELOPMENT VERSION
     ↓
ANALYSIS
```

The Entire checkpoint should appear as a first-class node.

Example:

```text
V7

Intent
"Improve classification accuracy"
       ↓
Claude Code
       ↓
Entire Checkpoint abc123
       ↓
Git Commit 7fa91c
       ↓
+142 / -37 lines
       ↓
143 tests passed
       ↓
Accuracy +4.2%
       ↓
SUCCESS
```

---

# 16. AI Context Integration

When an AI agent asks DevMemory for project context, Entire information should be included when available.

Example:

```json
{
    "current_version": "v14",

    "latest_development": {
        "version": "v14",
        "intent": "Improve inference performance",
        "agent": "Claude Code",
        "entire_checkpoint": "abc123",
        "git_commit": "a72c91"
    },

    "previous_failures": [],
    "incomplete_features": [
        "notifications"
    ]
}
```

The AI should be able to understand:

```text
What happened?
Why did it happen?
Which AI session performed it?
What code changed?
What happened afterwards?
```

---

# 17. MCP

If DevMemory exposes MCP tools, Entire checkpoint information should be available through those tools.

Example:

```text
get_checkpoint_context(version_id)
```

Response:

```json
{
    "version": "v14",
    "checkpoint_id": "abc123",
    "agent": "Claude Code",
    "intent": "Improve inference performance",
    "git_commit": "a72c91"
}
```

Another useful tool:

```text
get_development_trace(version_id)
```

Response:

```json
{
    "intent": "...",
    "agent": "...",
    "entire_checkpoint": "...",
    "git_commit": "...",
    "changed_files": [],
    "tests": {},
    "metrics": {},
    "status": "SUCCESS"
}
```

---

# 18. Entire Graph

Entire Graph is a secondary feature.

Do not make the core version system depend on the graph.

The preferred architecture is:

```text
Core:

Entire Checkpoint
        +
Git
        ↓
Development Version
```

Optional:

```text
Development Version
        ↓
Entire Graph
        ↓
Impact Analysis
```

If Entire exposes useful graph/codebase relationship information, DevMemory may use it to calculate:

```text
Files affected
Modules affected
Functions affected
Potential downstream impact
```

Example:

```text
Changed:
auth.py

Potential impact:

auth.py
   ↓
middleware.py
   ↓
UserService
   ↓
OrdersAPI
   ↓
PaymentAPI

Impact:
5 modules
12 functions
3 endpoints
```

Do not build a custom graph engine for the MVP.

---

# 19. Testing the Integration

Before implementing the full application, create a small integration test.

The test repository should contain:

```text
sample-project/
    app.py
    tests/
```

Workflow:

```bash
git init
entire enable
```

Run an AI coding session through Claude Code.

Create a change.

Commit it.

Then run:

```bash
devmemory checkpoint
```

Expected:

```text
Git commit detected
Entire checkpoint detected
Checkpoint associated
Development version created
```

Verify:

```text
Version
    ↓
Git commit
    ↓
Entire checkpoint
```

---

# 20. Integration Failure Modes

Handle these explicitly.

### Entire not installed

```text
ERROR: Entire CLI not installed.
```

### Entire not enabled

```text
ERROR: Entire is not enabled for this repository.
```

### No checkpoint found

```text
WARNING: No Entire checkpoint found for this development change.
```

### Multiple possible checkpoints

```text
WARNING: Multiple Entire checkpoints may correspond to this commit.
```

Store the candidates and mark the association uncertain.

### Git repository missing

```text
ERROR: DevMemory requires a Git repository.
```

### Dirty working tree

Before creating a version, warn if important changes are uncommitted.

Example:

```text
WARNING

You have uncommitted changes.

Commit the current development change before creating
a DevMemory version.
```

Do not silently snapshot arbitrary uncommitted changes as a version unless explicitly requested.

---

# 21. Implementation Rules

1. Do not hardcode assumptions about Entire's internal storage.
2. Inspect the installed Entire CLI and documentation before implementing the adapter.
3. Keep Entire-specific logic inside `EntireAdapter`.
4. Never duplicate the complete Entire checkpoint.
5. Store references and normalized metadata.
6. Git remains the source of truth for code changes.
7. Entire remains the source of truth for AI-development context.
8. DevMemory connects the two.
9. Missing Entire context must be visible to the user.
10. Do not fabricate checkpoint IDs, URLs, sessions, prompts, or agent activity.
11. Prefer verified associations over timestamp heuristics.
12. Keep the adapter replaceable so Entire CLI changes do not affect the rest of DevMemory.

---

# 22. Definition of Done

The Entire integration is considered successful when this works:

```text
Claude Code
     ↓
Entire Checkpoint
     ↓
Git Commit
     ↓
devmemory checkpoint
     ↓
EntireAdapter discovers checkpoint
     ↓
GitAdapter discovers commit/diff
     ↓
DevelopmentVersion created
     ↓
Dashboard displays:

Intent
Agent
Entire Checkpoint
Git Commit
Files Changed
Diff
Tests
Metrics
Status
```

The user must be able to follow:

```text
Version 7
    ↓
Entire Checkpoint abc123
    ↓
AI development context
    ↓
Git Commit 7fa91c
    ↓
Exact code diff
    ↓
Development result
```

This connection is the primary reason Entire is part of DevMemory.
