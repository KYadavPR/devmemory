# Entire Integration Reference

## Purpose of This Document

This document explains how DevMemory should understand and integrate with Entire.

This is a technical reference for implementation.

Do not invent Entire APIs, internal file formats, checkpoint locations, or behavior.

When implementation details are uncertain, inspect the installed Entire CLI, repository metadata, generated configuration, Git history, hooks, or official/current Entire source before making assumptions.

---

# 1. What Entire Does

Entire is a Git-integrated platform for capturing AI-assisted development sessions and connecting those sessions to code changes.

The important distinction for DevMemory is:

```text
Git
→ remembers the code history

Entire
→ remembers the AI-assisted development context
```

DevMemory connects the two.

Conceptually:

```text
Developer
    ↓
AI coding agent
    ↓
AI session
    ↓
Entire captures session context
    ↓
Developer/agent creates Git commit
    ↓
Entire associates checkpoint metadata with that commit
    ↓
DevMemory creates a Development Version
```

Entire is therefore not a replacement for Git.

It complements Git.

---

# 2. Entire + Git Architecture

Entire uses Git as part of its checkpoint architecture.

Normal project history remains on the project's active branch:

```text
main
  │
  ├── commit A
  ├── commit B
  ├── commit C
  └── commit D
```

Entire checkpoint/session metadata is stored separately.

The checkpoint metadata branch is:

```text
entire/checkpoints/v1
```

This keeps detailed session information separate from the normal code history.

Conceptually:

```text
NORMAL GIT HISTORY

main
  │
  ├── A
  ├── B
  ├── C
  └── D


ENTIRE CHECKPOINT HISTORY

entire/checkpoints/v1
  │
  ├── checkpoint metadata
  ├── checkpoint metadata
  └── checkpoint metadata
```

DevMemory should understand both histories.

---

# 3. Entire Must Be a Core Integration

Entire must NOT be treated as a generic optional plugin.

For DevMemory, Entire is one of the primary sources of development context.

The core relationship is:

```text
Entire Checkpoint
       │
       │ context
       ↓
Development Version
       ↑
       │ code
       │
Git Commit
```

The Development Version combines:

```text
Entire context
+
Git code history
+
tests
+
metrics
+
analysis
```

---

# 4. Entire Installation

Entire is installed separately from DevMemory.

DevMemory should NOT attempt to reinstall Entire automatically unless explicitly designed to do so later.

A developer may already have Entire installed.

Verify availability using:

```powershell
entire --version
```

The developer can inspect available commands using:

```powershell
entire --help
```

And repository-specific status using:

```powershell
entire status
```

---

# 5. Enabling Entire

Entire is enabled inside a Git repository.

Typical command:

```powershell
entire enable
```

Entire can also be enabled for a specific agent:

```powershell
entire enable --agent <agent>
```

The exact supported agent names should be discovered from the installed Entire version rather than hard-coded.

For example, Entire currently supports multiple coding agents, including Claude Code and others.

DevMemory should therefore detect the actual installed Entire configuration instead of assuming a particular agent.

---

# 6. Claude Code Integration

The target development environment for the initial implementation is Claude Code.

The important point is:

DevMemory does NOT replace Claude Code.

The developer continues using Claude Code normally.

The intended flow is:

```text
VS Code
   ↓
Claude Code
   ↓
Entire hooks
   ↓
Entire session/checkpoint
   ↓
Git
   ↓
DevMemory
```

Claude Code may be running inside:

* VS Code terminal
* Windows Terminal
* PowerShell
* another terminal environment

DevMemory should not care which UI is being used.

The package operates at the repository/Git/Entire layer.

---

# 7. Entire Hooks

Entire integrates with supported coding agents through agent-specific configuration/hooks.

For Claude Code, Entire uses Claude Code's project-level hook configuration.

The exact generated configuration should be inspected from the repository rather than recreated manually.

After running:

```powershell
entire enable
```

inspect the generated files.

For example:

```text
.entire/
.claude/
```

The exact contents depend on the installed Entire version.

DevMemory should treat these generated files as Entire-owned configuration.

Do not modify them unnecessarily.

---

# 8. Sessions

An Entire session represents an AI-assisted development interaction.

A session can contain:

* prompts
* AI responses
* files modified
* timestamps
* session metadata
* development context

The session is different from a Git commit.

A single AI session may involve many edits before the developer commits.

Conceptually:

```text
Entire Session
│
├── Prompt
├── AI response
├── File edit
├── File edit
├── Tool activity
├── More edits
└── Git commit
        ↓
   Checkpoint association
```

DevMemory should not assume:

```text
one prompt = one Git commit
```

or:

```text
one session = one Development Version
```

Instead, DevMemory should build a relationship between sessions/checkpoints and the Git commit that represents the resulting development state.

---

# 9. Checkpoints

An Entire checkpoint is a saved development state associated with AI-assisted work.

The checkpoint is the key Entire object for DevMemory.

Conceptually:

```text
Checkpoint
│
├── session
├── agent
├── prompts/context
├── files/session information
├── timestamp
└── association with Git state
```

DevMemory should store the checkpoint identity/reference.

It should NOT unnecessarily copy the complete Entire session data into its own database.

---

# 10. Checkpoint IDs

Entire checkpoints have checkpoint identifiers.

Example:

```text
a3b2c4d5e6f7
```

The exact identifier should always come from Entire.

DevMemory must never invent checkpoint IDs.

A Development Version should store something similar to:

```text
entire_checkpoint_id
```

Example:

```json
{
  "entire_checkpoint_id": "a3b2c4d5e6f7"
}
```

---

# 11. Git Commit Association

This is one of the most important integration points.

Entire associates checkpoint metadata with Git development.

Current Entire behavior includes an `Entire-Checkpoint` Git commit trailer.

Conceptually:

```text
Git commit

abc1234

Entire-Checkpoint: a3b2c4d5e6f7
```

This provides a direct relationship:

```text
Git Commit
     │
     │ Entire-Checkpoint trailer
     ↓
Entire Checkpoint
```

DevMemory should prefer this explicit relationship whenever available.

Do NOT try to associate checkpoints using only timestamps if a direct Git association exists.

---

# 12. Recommended Checkpoint Association Strategy

When creating a Development Version, DevMemory should attempt to associate the current Git state with an Entire checkpoint.

Preferred order:

```text
1. Inspect current Git commit metadata/trailers
        ↓
2. Find Entire-Checkpoint reference
        ↓
3. Resolve the corresponding Entire checkpoint
        ↓
4. Store checkpoint ID/reference
```

If a direct commit trailer is unavailable:

```text
5. Inspect Entire's repository metadata
6. Inspect Entire checkpoint branch
7. Inspect session/checkpoint metadata
8. Use commit/session relationships where supported
```

Timestamp matching should be considered a fallback only.

Do not make timestamp matching the primary mechanism.

---

# 13. Do Not Assume a Fixed Entire Internal Layout

Do NOT write code such as:

```python
open(".entire/some-hardcoded-file.json")
```

unless the installed Entire version has been verified to use that file.

Entire's internal implementation can change.

Instead:

```text
DevMemory
    ↓
Entire CLI / documented interface
    ↓
verified checkpoint information
```

When necessary, inspect:

```powershell
entire --help
entire status
entire <relevant-command> --help
```

and the repository's generated Entire configuration.

If a reliable machine-readable CLI command exists, prefer it over parsing undocumented internal files.

---

# 14. Entire Checkpoint Branch

Entire stores checkpoint metadata on:

```text
entire/checkpoints/v1
```

This is separate from the active project branch.

Conceptually:

```text
main
│
├── code commit
├── code commit
└── code commit


entire/checkpoints/v1
│
├── checkpoint
├── checkpoint
└── checkpoint
```

This is important because DevMemory should not try to recreate Entire's checkpoint storage system.

Entire already owns that responsibility.

DevMemory should reference it.

---

# 15. What DevMemory Should Store

A Development Version should store normalized information such as:

```json
{
  "version_id": "V7",
  "git_commit": "7fa91c",
  "parent_commit": "4e92ab1",
  "entire_checkpoint_id": "a3b2c4d5e6f7",
  "agent": "Claude Code",
  "timestamp": "2026-09-06T01:30:00Z"
}
```

Additional DevMemory fields can include:

```text
intent
feature
status
changed_files
tests
metrics
analysis
recommendation
artifact
```

The important distinction is:

```text
Entire owns:
AI-session context

Git owns:
code history

DevMemory owns:
normalized development intelligence
```

---

# 16. Do Not Duplicate Entire

Avoid storing:

```text
full Entire transcript
full tool history
full raw session data
full checkpoint internals
```

inside every DevMemory version.

Instead store:

```text
checkpoint_id
checkpoint reference/location
agent
session information
important normalized metadata
```

When deeper information is required, DevMemory should navigate back to Entire's checkpoint/session data where possible.

---

# 17. Development Version Relationship

A DevMemory Development Version should look conceptually like:

```text
VERSION 7
│
├── Intent
│
├── Entire Checkpoint
│     ├── checkpoint ID
│     ├── session
│     ├── agent
│     └── AI context
│
├── Git
│     ├── commit
│     ├── parent commit
│     ├── changed files
│     └── diff
│
├── Tests
│
├── Metrics
│
├── Analysis
│
└── Result
```

This is the central data relationship in DevMemory.

---

# 18. Example

Suppose the developer asks Claude Code:

```text
Improve image classification accuracy.
```

Claude Code modifies:

```text
model.py
preprocessing.py
```

Entire captures the AI development context.

The developer then commits:

```text
7fa91c
```

The commit contains an Entire checkpoint association:

```text
Entire-Checkpoint: a3b2c4d5e6f7
```

DevMemory creates:

```text
VERSION 7

Intent:
Improve image classification accuracy

Agent:
Claude Code

Entire:
a3b2c4d5e6f7

Git:
7fa91c

Files:
model.py
preprocessing.py

Tests:
143 passed

Accuracy:
89.2% → 93.4%

Status:
SUCCESS
```

The important chain is:

```text
Prompt
   ↓
Claude Code session
   ↓
Entire checkpoint
   ↓
Git commit
   ↓
DevMemory Version
```

---

# 19. Detecting the Current Checkpoint

When:

```bash
devmemory checkpoint
```

is executed, DevMemory should attempt to answer:

```text
What is the current Git commit?

What is its parent?

Does it contain an Entire checkpoint reference?

What checkpoint does that reference identify?

What Entire session/context belongs to it?
```

The first implementation should use the most reliable information available from the installed Entire version.

Do not assume that the answer can always be obtained from one hardcoded file.

---

# 20. Git Inspection

DevMemory can use Git commands for code history.

Useful commands include:

Current commit:

```powershell
git rev-parse HEAD
```

Parent commit:

```powershell
git rev-parse HEAD^
```

Commit metadata:

```powershell
git show --format=fuller --no-patch HEAD
```

Commit message:

```powershell
git log -1 --pretty=%B
```

Changed files:

```powershell
git diff-tree --no-commit-id --name-status -r HEAD
```

Diff:

```powershell
git diff HEAD^ HEAD
```

Trailers:

```powershell
git show --format='%(trailers:key=Entire-Checkpoint,valueonly)' --no-patch HEAD
```

The exact Git invocation can be changed during implementation.

Prefer robust Git library/subprocess abstractions rather than scattering commands throughout the codebase.

---

# 21. Entire Status

During development/debugging, inspect:

```powershell
entire status
```

This should be useful for determining:

* whether Entire is enabled
* which agent integration is active
* current strategy
* relevant configuration
* checkpoint state

DevMemory should use this information during integration development.

Do not make assumptions based only on whether `.entire/` exists.

---

# 22. Entire Configuration

Entire generates/uses project configuration.

For example:

```text
.entire/
```

may contain project-specific configuration.

The exact configuration should be discovered from the installed version.

DevMemory should NOT overwrite Entire configuration.

If DevMemory needs to know configuration values, it should read them safely or use Entire's supported interfaces.

---

# 23. Manual Commit Strategy

Entire's current architecture can use a manual-commit strategy.

The important principle is:

```text
Developer controls Git commits.
```

Entire records checkpoint metadata without taking over normal source-code version control.

This is exactly the model DevMemory wants.

DevMemory should therefore NOT automatically create arbitrary Git commits merely to create Development Versions.

A Development Version should normally correspond to an existing meaningful Git commit.

---

# 24. Entire and Git Are Complementary

Do not implement this:

```text
Entire replaces Git
```

or:

```text
DevMemory replaces Git
```

Instead:

```text
Git
=
permanent source-code history

Entire
=
AI-assisted development context

DevMemory
=
development intelligence connecting both
```

---

# 25. Claude Code vs Entire Checkpoints

Claude Code has its own session/checkpoint/recovery concepts.

Do not confuse those with Entire Checkpoints.

For DevMemory's hackathon integration, the important source is:

```text
Entire Checkpoint
```

because Entire is the required platform being demonstrated.

Claude Code's internal rewind/checkpoint mechanisms are not the primary DevMemory storage mechanism.

DevMemory should use Entire's checkpoint relationship as the canonical AI-development-context reference.

---

# 26. Entire Rewind

Entire provides checkpoint-based rewind functionality.

Conceptually:

```text
entire rewind
```

allows developers to return to an earlier checkpoint state.

DevMemory should NOT reimplement Entire's rewind system.

If DevMemory provides a "Restore Version" feature, it should distinguish between:

```text
DevMemory restore
```

and:

```text
Entire rewind
```

Potential model:

```text
DevMemory Version
       ↓
Git commit
       ↓
Git restoration
```

while:

```text
Entire checkpoint
       ↓
Entire rewind
       ↓
AI/session state restoration
```

The two systems solve related but different problems.

---

# 27. Entire Graph

Entire Graph is a separate capability that can provide semantic/codebase relationship information.

For example:

```text
auth.py
   ↓
middleware.py
   ↓
UserService
   ↓
OrdersAPI
```

DevMemory can eventually use this to answer:

```text
What might this change affect?
```

However:

Entire Graph is NOT required for the first vertical slice.

Priority should be:

```text
Entire Checkpoint
        ↓
Git
        ↓
Development Version
```

before:

```text
Entire Graph
```

---

# 28. Entire Graph Integration Strategy

If Entire Graph is available in the environment:

1. Detect whether it is installed.
2. Inspect its supported commands.
3. Query graph information only for relevant files/symbols.
4. Normalize the result into an impact model.
5. Display useful impact information.

Do NOT build a custom dependency graph engine just to satisfy the feature.

The MVP can display:

```text
Potential Impact

5 modules
12 functions
3 API endpoints
```

if reliable graph information is available.

---

# 29. Agent Detection

DevMemory should not hard-code:

```python
agent = "Claude Code"
```

everywhere.

Instead the system should have an agent abstraction.

Example:

```python
class AgentInfo:
    name: str
    session_id: str | None
    source: str
```

For the initial implementation:

```text
Claude Code
```

is the primary supported agent.

But the architecture should allow:

```text
Claude Code
Codex
Gemini CLI
Cursor
OpenCode
Copilot CLI
```

or other Entire-supported agents later.

---

# 30. Recommended Adapter

Create an adapter:

```text
devmemory/adapters/entire.py
```

Conceptually:

```python
class EntireAdapter:
    def is_available(self) -> bool:
        ...

    def status(self):
        ...

    def get_current_checkpoint(self):
        ...

    def get_checkpoint(self, checkpoint_id):
        ...

    def get_checkpoint_context(self, checkpoint_id):
        ...

    def get_agent(self):
        ...
```

The exact methods can change after inspecting the actual Entire CLI.

The adapter should hide Entire-specific implementation details from the rest of DevMemory.

---

# 31. Normalized Checkpoint Model

DevMemory should normalize Entire information into its own internal representation.

Example:

```python
class CheckpointReference:
    checkpoint_id: str
    session_id: str | None
    agent: str | None
    timestamp: datetime | None
    location: str | None
    source: str = "entire"
```

Do not put raw Entire-specific structures throughout the application.

Only the Entire adapter should know how to retrieve them.

---

# 32. Failure Handling

Entire may be:

* unavailable
* disabled
* misconfigured
* missing checkpoint metadata
* missing remote data
* running with an unsupported agent
* temporarily inaccessible

DevMemory should handle these situations gracefully.

Example:

```text
Entire checkpoint:
NOT FOUND

Git commit:
FOUND

Development Version:
CREATED

Warning:
No Entire checkpoint could be associated with this commit.
```

However, for the hackathon's main demo, the expected path should have Entire enabled and a valid checkpoint association.

Do not silently fabricate checkpoint information.

---

# 33. Never Fabricate Entire Data

This is critical.

Never generate:

```text
checkpoint-abc123
```

just because a checkpoint is expected.

Never infer:

```text
agent = Claude Code
```

unless the available data supports it.

Never invent:

```text
Entire session
```

or:

```text
checkpoint location
```

If the information cannot be obtained, represent it as unavailable.

Example:

```json
{
  "entire_checkpoint_id": null,
  "entire_status": "unavailable"
}
```

---

# 34. Recommended Debugging Workflow

When developing the Entire adapter:

### Step 1

Verify Git:

```powershell
git status
```

### Step 2

Verify Entire:

```powershell
entire --version
```

### Step 3

Inspect Entire:

```powershell
entire --help
```

### Step 4

Inspect repository state:

```powershell
entire status
```

### Step 5

Inspect generated configuration:

```text
.entire/
.claude/
```

### Step 6

Perform a tiny Claude Code task.

### Step 7

Inspect Git:

```powershell
git log --oneline --decorate -5
```

### Step 8

Inspect the resulting commit metadata/trailers.

### Step 9

Identify the Entire checkpoint associated with the commit.

### Step 10

Only then implement the DevMemory adapter.

---

# 35. Do Not Build Against Guesses

Before writing the Entire integration, Claude Code should inspect the actual environment.

The implementation agent should run commands such as:

```powershell
entire --version
entire --help
entire status
git status
git log --oneline --decorate -10
```

and inspect the generated repository files.

If necessary, inspect the installed Entire CLI/source documentation.

The implementation should be based on the actual installed Entire version.

---

# 36. Core Integration Contract

For DevMemory, the Entire integration ultimately needs to answer:

```text
Is Entire available?

Is Entire enabled in this repository?

Which agent is being captured?

What is the relevant session?

What is the relevant checkpoint?

What is the checkpoint ID?

Which Git commit does the checkpoint correspond to?

Where/how can the detailed checkpoint context be accessed?
```

The rest of DevMemory should not need to know how Entire answers these questions.

---

# 37. Final Mental Model

The entire system should be understood like this:

```text
                    DEVELOPER
                        │
                        ↓
                  CLAUDE CODE
                        │
                        ↓
               ┌────────────────┐
               │ Entire Capture │
               └────────────────┘
                        │
                        ↓
               ENTIRE CHECKPOINT
                        │
                        │
                        ↓
Git ───────────────→ DEVELOPMENT VERSION
│                         │
│                         ├── Intent
│                         ├── Agent
│                         ├── Checkpoint
│                         ├── Diff
│                         ├── Tests
│                         ├── Metrics
│                         ├── Status
│                         └── Analysis
│
↓
Code History
```

The most important relationship is:

```text
ENTIRE CHECKPOINT
       +
GIT COMMIT
       +
RESULTS
       ↓
DEVMEMORY DEVELOPMENT VERSION
```

That relationship is the foundation of the project.

---

# 38. Implementation Rule

Before implementing the Entire adapter:

> Inspect the actual installed Entire CLI and repository state.

Do not rely on assumptions from this document when the installed CLI can provide the real answer.

This document explains the architectural role of Entire.

The installed Entire CLI and current source/documentation are authoritative for exact commands, output formats, file locations, and internal implementation details.
