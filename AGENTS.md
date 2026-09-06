# Agent operating protocol — the state-aware coding loop

This repository runs a **closed feedback loop** around you (the AI coding agent).
DevMemory's State Engine aggregates evidence from Git, Entire, tests, and the
Entire graph into one normalized state and exposes it over MCP. You stay
responsible for understanding the repo and deciding the implementation — the
state only orients you.

## The MCP server

`devmemory` exposes these loop tools (plus the read-only memory tools):

| tool | use |
|---|---|
| `create_task(goal, test_command?)` | start a task — normalizes the goal into requirements, pins the base commit |
| `get_state(task_id)` | the current normalized state (requirements, git, checkpoint, tests, impact, unresolved, recommended focus, overall status) |
| `refresh_state(task_id)` | re-run every collector, re-evaluate requirements, recompute status, store a snapshot |
| `set_requirement_status(task_id, requirement_id, status, note)` | record your own verdict for a requirement after you implement + verify it |
| `report_issue(task_id, description, blocking?)` | record an unresolved item; `blocking=True` forces BLOCKED |
| `mark_complete(task_id)` | request a completion evaluation (never blindly READY) |
| `get_checkpoint(checkpoint_id)` | compact metadata for one Entire checkpoint |

Wire it up: `devmemory mcp --print-config` (a workspace `.mcp.json` is already
committed for this repo).

## The loop

1. Before starting or resuming meaningful work, call **`get_state(task_id)`**.
2. Read the state — `recommended_focus`, `unresolved`, failing `requirements`.
3. **Inspect the actual repository** with your normal tools. The state is
   evidence and guidance, not a code patch — do not blindly obey
   `recommended_focus` if the repo shows it is wrong.
4. Decide the implementation yourself. Make the code changes.
5. Run the relevant tests. Fix failures.
6. **Commit the source changes** to `main` before declaring anything done.
7. For each requirement you finished and verified, call
   `set_requirement_status(task_id, "R<n>", "COMPLETE", "<how you verified>")`.
8. Call **`refresh_state(task_id)`**, then read the returned `overall_status`:
   - **`NEEDS_WORK`** → keep going from step 3.
   - **`BLOCKED`** → stop and explain the blocker to the human.
   - **`READY`** → stop implementation and report completion.
9. Push only when the configured policy allows (default: commit locally, don't
   push while `NEEDS_WORK`).

## Status meanings (evidence-based, not certainty)

- **IN_PROGRESS** — actively being worked on; no completion evaluation yet.
- **NEEDS_WORK** — a requirement is incomplete, tests fail, or an issue is open.
- **READY** — requirements satisfied, relevant tests pass, no open issues,
  working tree clean.
- **BLOCKED** — you cannot safely continue; a human/external decision is needed,
  or git itself is unavailable.

## Rules

- Never force-push, never `reset --hard` without explicit recovery, never delete
  branches, never rewrite `main` history.
- Source code lives on `main`. Entire manages its own checkpoint storage
  (git-refs backend) — do not create competing checkpoint commits.
- The State Engine never modifies application code.
