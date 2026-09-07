# The state-aware coding loop

A closed feedback loop around an AI coding agent, built on DevMemory's existing
evidence collectors. The agent implements; the **State Engine** aggregates Git +
Entire + tests + (optional) graph into one normalized state and an evidence-based
status. See [`AGENTS.md`](../AGENTS.md) for the agent protocol.

```
human task → normalize into requirements → agent inspects repo → edits code
   → tests → commit → Entire checkpoint → refresh_state → new state
   → agent continues (NEEDS_WORK) / stops (READY) / escalates (BLOCKED)
```

## Try it

Any DevMemory project works. From a repo you have run `devmemory init` in:

```bash
devmemory task new "Add a currency helper and a test for it" \
    --test "python -m pytest -q"
devmemory task state                 # the dashboard: NEEDS_WORK, requirements 0/2

# ... agent inspects the repo, implements the helper + a test, commits ...

devmemory task requirement R1 -s complete -m "added the currency helper"
devmemory task refresh               # re-collects evidence; R2 (tests) verified
devmemory task state                 # READY
devmemory task history               # snapshot #1 NEEDS_WORK → #2 READY
```

Over MCP the same flow is `create_task` → `get_state` → *(implement)* →
`set_requirement_status` → `refresh_state` → read `overall_status`.

## The normalized state

`get_state` / `refresh_state` return a compact object — **not** the repository.
It carries: the task + its requirements (each `COMPLETE`/`PARTIAL`/`INCOMPLETE`/
`UNKNOWN` with a reason), the current/last checkpoint id and session id, the Git
branch/SHA/diffstat/tree-clean flag, the test command + pass/fail + status, a
change-impact count (`available: false` when the graph plugin is absent),
unresolved items, findings, `recommended_focus`, and `overall_status`.

## Status

| status | meaning |
|---|---|
| `IN_PROGRESS` | actively worked on; no completion evaluation yet |
| `NEEDS_WORK` | a requirement is incomplete, tests fail, or an issue is open |
| `READY` | requirements satisfied, tests pass, no open issues, tree clean |
| `BLOCKED` | can't safely continue — human/external decision needed, or git unavailable |

`READY` is evidence-based, not a proof. `mark_complete` runs a full refresh and
returns the state; it never blindly marks `READY`.

## What it does not do

No custom checkpoint store (Entire owns that, git-refs backend), no second git
branch, no autonomous background process (the loop is driven by the agent's MCP
calls), no repository dump into the state, no fabricated metrics or checkpoint
ids. The engine never edits application code.
