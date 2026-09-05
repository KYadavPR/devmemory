# DevMemory — Implementation Strategy

> Engineering audit, locked decisions, and the phased build plan.
> Companion to `PROJECT_SPEC.md`, `ARCHITECTURE.md`, `ENTIRE_INTEGRATION.md`,
> `ENTIRE_QUICKSTART.md`, and `DATA_AND_API_SPEC.md`, which remain the product and
> data specification. Where this document and those conflict, the conflict is
> called out here and resolved in favour of what the installed tooling actually
> supports.

Last updated: 2026-09-06 (Phase 0).

---

## 1. What we are building

A reusable, `pip`-installable Python platform (`devmemory` / `dm`) that sits *beside*
a developer's existing tools and turns each meaningful AI-assisted change into a
**Development Version** — one durable record that joins five otherwise-disconnected
facts:

| Layer | Source of truth | DevMemory's job |
|---|---|---|
| *What* changed — commit, diff, files, renames, line counts | **Git** | reference + cache |
| *Why / who / how* — prompt, agent, model, transcript, tokens | **Entire checkpoint** | reference + normalize |
| *What resulted* — tests, metrics, regressions, status | **DevMemory** | own it |
| *What it means* — analysis, recommendation, previous-attempt warnings | **DevMemory intelligence (LLM)** | own it, kept separate from facts |
| *What the trend is* — cross-version / agent / feature / file analytics | **Databricks** | analytics layer |

Consumed two ways: a **visual dashboard** for humans, and an **MCP server + REST
context API** for the next AI agent.

The defensible core is the *join*, and the join is only credible if the Entire
checkpoint is a real, first-class participant — never fabricated.

**DevMemory is not** an IDE, a VCS, an AI agent, an experiment tracker, or a generic
observability dashboard. It does not create commits to make versions; a version
normally corresponds to an existing meaningful commit.

---

## 2. Environment (verified 2026-09-06)

| Tool | Version | Notes |
|---|---|---|
| OS | Windows 11 | PowerShell 5.1 + Git Bash |
| Python | 3.14.6 (python.org) | one global env (the user's Django env) — **DevMemory uses its own venv** |
| pip | 26.1.2 | no `uv`, no `pipx` |
| Git | 2.47.1 | `core.autocrlf` unset → LF/CRLF handled via `.gitattributes` |
| Node | 22.12 / npm 10.9 | for the Vite build step only |
| Go | 1.27 | used once to inspect Entire |
| SQLite (via Python) | 3.50.4 | FTS5 + JSON1 available |
| Entire CLI | 0.10.5 | installed to `~/.local/bin/entire.exe` (official installer) |

All target dependencies resolve on Python 3.14 (`fastapi 0.141`, `uvicorn 0.52`,
`typer 0.27`, `databricks-sdk 0.135`, `fastmcp 4.0.3`, `pytest 9.1`, `structlog 26.1`,
`rich 15`). Python 3.14 is not a risk; the package targets 3.11+.

No `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DATABRICKS_*` are set in the environment.
They will be added later; every integration degrades gracefully without them.

---

## 3. Entire integration (verified against installed CLI 0.10.5)

`ENTIRE_INTEGRATION.md` §35 is emphatic: *inspect the installed CLI, do not guess.*
The following was verified by installing Entire and exercising it against a scratch
repository.

### 3.1 Capture model

- Fully **local, no login** for capture, checkpoint reads, `why`, `blame`, `explain`.
  Login is only needed for hosted dashboard sync, semantic `entire search`, and
  `recap` / `activity`.
- `entire enable --agent claude-code --yes --no-github` writes:
  - `.entire/settings.json` (committed) — `{enabled, telemetry, checkpoints.primary.type: "git-refs"}`
  - `.entire/.gitignore`
  - `.claude/settings.json` (committed) — eight hooks calling `entire hooks claude-code <phase>`
  - Git hooks: `prepare-commit-msg` (injects the trailer), `commit-msg` (strips it if
    the commit has no real content), `post-commit` (condenses session data),
    `post-rewrite` (remaps after amend/rebase/squash), `pre-push` (pushes session logs).
- Linking is **automatic and non-interactive** by default.

### 3.2 Checkpoint storage (read directly from Git objects)

Backend `git-refs` (default): one ref per checkpoint at
`refs/entire/checkpoints/<shard>/<id>`, `<shard>` = last two characters of the id.
Each ref points to a commit whose tree is:

```
metadata.json              top-level envelope
<idx>/metadata.json        per-session metadata
<idx>/prompt.txt           the user's prompt  ==  INTENT
<idx>/full.jsonl           full transcript
<idx>/transcript.jsonl     compact transcript
<idx>/content_hash.txt
```

Top-level `metadata.json` (verified): `cli_version`, `checkpoint_id`, `strategy`,
`commit_sha`, `checkpoints_count`, `files_touched`, `sessions[]` (path pointers),
`token_usage`, `imported`. Per-session adds `session_id`, `agent`, `model`,
`created_at`, `kind`.

Checkpoint IDs: 26-char ULID for hook-captured checkpoints, 12-char hex for
imported / logs-only.

### 3.3 Commit ↔ checkpoint association — the ladder

DevMemory resolves the checkpoint for a commit in this order, recording
`association_method` and `association_confidence`:

1. **Git trailer** (`method = trailer`, confidence 1.0) — no Entire dependency:
   `git show -s --format='%(trailers:key=Entire-Checkpoint,valueonly)' <sha>`.
   The trailer is stored, not derived, so it survives rebase/amend/squash/cherry-pick.
2. **Entire CLI** (`method = entire_cli`, confidence 1.0):
   `entire checkpoint explain --commit <sha> --json` → metadata envelope
   (no transcript bytes, no prompt text).
3. **Direct Git-object read** (`method = git_ref`, confidence 1.0) — offline fallback:
   `git cat-file -p refs/entire/checkpoints/<shard>/<id>:metadata.json` and
   `:<idx>/prompt.txt`. Works with zero Entire involvement; this is the resilience story.
4. **Time/branch heuristic** (`method = heuristic_time`, confidence ≤ 0.5) — UI-flagged.
5. **None** — `entire_status: "unavailable"`, never fabricated.

Per-file / per-line AI attribution: `entire why <file>[:line] --json` and
`entire blame <file> --json` return per-line `authorship` (`human`/`ai`/`mixed`),
`commit_sha`, `author`, `author_time`, plus a summary with `ai_percentage`.

### 3.4 Getting real checkpoints for the demo

1. **Live** — run Claude Code in an `entire enable`d repo; hooks capture the session,
   the commit gets a ULID checkpoint + trailer automatically. (We dogfood DevMemory's
   own development this way — Entire is enabled on this repo from Phase 0.)
2. **`entire session attach <session-id> --force`** (verified) — builds a checkpoint
   from an existing transcript and amends `HEAD` with the trailer. The deterministic
   recovery path when hooks did not fire.
3. **`entire import claude-code [--path DIR]`** (verified) — bulk-imports past
   transcripts as read-only, non-commit-linked checkpoints. For back-filling history.

### 3.5 `entire-graph`

Official plugin (`entire plugin install graph`). `graph impact <symbol>` returns a
blast radius (callers / callees / co-change files); JSON output; local and
deterministic; needs an index; Git ≥ 2.36 (have 2.47). Optional `GraphAdapter`,
never a hard dependency.

### 3.6 Gotchas

- Repo auto-detection needs an `origin` remote (or `--repo owner/name`); detached
  HEAD breaks it. The adapter passes `--repo` when configured.
- `entire agent-help [command]` is the machine-readable CLI contract — the adapter
  treats it plus `--json` as the interface and never hard-codes flags.
- Entire's secret redaction is best-effort; DevMemory stores only references and a
  short prompt excerpt, never full transcripts.

---

## 4. Git integration

Pure `subprocess` against the `git` CLI — no GitPython (identical behaviour
cross-platform, one fewer heavy dependency). Rules: explicit `cwd`; env with
`GIT_OPTIONAL_LOCKS=0`, `GIT_TERMINAL_PROMPT=0`; `--no-pager`; `-z` NUL-delimited
parsing where available; `-c core.autocrlf=false` for internal calls; `pathlib` only;
stored paths always POSIX. Diffs are generated on demand from the commit pair (the
source of truth) and only *cached* in SQLite.

---

## 5. Databricks integration

REST-only, no Spark, no cluster:

- `databricks-sdk` → **SQL Statement Execution API** against a **serverless SQL
  warehouse**. Works on Free Edition. Credentials from env only: `DATABRICKS_HOST`,
  `DATABRICKS_TOKEN`, `DATABRICKS_WAREHOUSE_ID` (+ optional catalog/schema).
- First `databricks push` bootstraps a star-ish schema
  (`dim_projects`, `fact_versions`, `fact_changed_files`, `fact_tests`,
  `fact_metrics`, `fact_regressions`, `dim_features`, `dim_checkpoints`,
  `dim_agent_sessions`).
- `publish_version(v)` → idempotent `MERGE` keyed on `(project_id, version_id)`;
  child rows delete-then-insert per version. Only normalized fields + short intent —
  never transcripts or source.
- **Offline-first**: unreachable → append to `.devmemory/outbox/`; `devmemory
  databricks push` drains it. Local history never depends on the cloud.
- "Meaningful", not "integration complete": a set of canned analytical queries wired
  to a dashboard **Intelligence** tab and to MCP — regression leaderboard, feature
  attempt-count / success-rate, file churn vs regression incidence, agent success
  rate & token cost per successful change, rolling test-pass-rate and metric trends,
  repeatedly-failed approaches.
- The identical query semantics are also implemented locally over SQLite, so the demo
  works with or without a workspace (source badged in the UI).
- *Stretch:* one MLflow trace per version for agent observability.

---

## 6. MCP

`fastmcp` stdio server (`devmemory mcp`). Every tool calls the same domain services
the REST API calls — no SQL in the MCP layer. Tools (from `DATA_AND_API_SPEC.md` §35):
`get_project_status`, `get_current_version`, `get_version_history`, `get_version`,
`get_version_diff`, `compare_versions`, `get_feature_status`, `get_feature_history`,
`get_previous_attempts`, `get_failed_changes`, `get_checkpoint_context`,
`get_development_trace`, `get_project_context`, plus one composite:
`check_before_change(files=[...], intent="...")`. Responses are curated context with
every fact tagged `source: git|entire|tests|metrics|analysis`. Ships a `.mcp.json`
fragment and `devmemory mcp install`.

---

## 7. Architecture decisions (deltas from the docs)

1. `src/` layout, **hatchling**, single package `devmemory`.
2. **No SQLAlchemy** — stdlib `sqlite3` + a hand-written repository layer + a
   numbered-migration runner. SQLite 3.50 here has FTS5 + JSON1.
3. **Domain services are the single waist.** CLI, REST, and MCP are thin adapters
   over `devmemory.services.*`. Only `services` and `storage` touch SQLite.
4. Adapters return normalized Pydantic models only: `GitAdapter`, `EntireAdapter`,
   `TestAdapter`, `MetricsAdapter`, `DatabricksAdapter`, `GraphAdapter`,
   `AnalysisProvider`.
5. **Frontend: Vite + React + TypeScript + Tailwind, pre-built into the wheel.**
   `devmemory serve` serves the built bundle — no Node at runtime.
6. **Facts vs analysis is structural**: a separate `analysis` table, never written by
   collectors; API responses tag every field's source.
7. `run_id` + a structured run log per `devmemory checkpoint` (`.devmemory/runs/`) so
   "what failed, which integration, was project state changed, what next" is always
   answerable.
8. Config precedence: `.devmemory/config.json` → `.devmemory/config.local.json` →
   env (secrets only) → CLI flags — mirroring Entire's own `settings.json` /
   `settings.local.json` split.

### Data-model deltas (applied when the persistence layer lands)

- `versions`: add `version_number`, `entire_association_method` / `_confidence`,
  `environment_json`, `run_id`, `source_event_json`, distinct `created_at` /
  `committed_at`.
- Checkpoints are **many-to-many** with versions (`version_checkpoints`).
- New tables: `regressions`, `analysis` (1:1), `doc_flags`, plus per-file
  `changed_files` and a real `tests` table.
- `features.derived_from` records how the feature was attributed.
- FTS5 `search_index` rebuilt on version write.

---

## 8. Technology stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+ (dev on 3.14) |
| Packaging | `pyproject.toml` + hatchling, `src/` layout |
| CLI | Typer + Rich |
| Models | Pydantic v2 (one set for REST + MCP + serialization) |
| Persistence | stdlib `sqlite3` + repositories + numbered migrations; FTS5 search |
| Git | subprocess plumbing |
| Entire | subprocess `--json` + direct Git-object reads |
| Web backend | FastAPI + uvicorn |
| Frontend | Vite + React + TS + Tailwind, prebuilt into the wheel |
| Analytics | `databricks-sdk` Statement Execution → Delta tables; MLflow trace (stretch) |
| MCP | `fastmcp` stdio |
| LLM | provider abstraction: Anthropic / OpenAI / Gemini / rules (fallback chain) |
| Logging | structlog (JSON + console), with secret redaction |
| Tests | pytest + pytest-cov |
| Lint / types | ruff + ruff-format + mypy (strict on domain/services) |
| CI | GitHub Actions: lint → mypy → pytest (Windows + Linux, 3.11–3.13) → build wheel |

---

## 9. Locked decisions (confirmed with the project owner)

1. **Databricks** — build the full adapter, star schema, and offline outbox now; the
   demo runs on the local-SQLite analytics parity path until `DATABRICKS_*` is added
   to the environment, then syncs.
2. **LLM analysis** — an `AnalysisProvider` abstraction supporting **all three**
   (Anthropic, OpenAI, Gemini) plus rule-based, as a configurable fallback chain.
   Rule-based is the effective default until an API key is present.
3. **Frontend** — Vite + React + TypeScript + Tailwind, prebuilt into the wheel.
4. **Demo** — a non-ML app (task API + auth, real pytest suite) is the headline; an
   ML example ships as a second `examples/` project.
5. **Name** — `devmemory` (CLI `devmemory` + alias `dm`).
6. **Entire** — installed via the official installer to `~/.local/bin/entire.exe`.

---

## 10. Build phases

Each phase ends with a working vertical slice, tests, and a demo-able command.

| Phase | Deliverable | Milestone |
|---|---|---|
| **0** | Repo + package foundation: `pyproject`, config, logging, error taxonomy, migration runner, CI, this doc, `entire enable` on our repo | skeleton installs, CI green |
| **1** | `devmemory init` + `GitAdapter` | `.devmemory/` scaffolded from a real repo |
| **2** | `EntireAdapter` (the resolution ladder) + normalized `CheckpointReference` | commit → checkpoint, with confidence |
| **3** | `DevelopmentEvent` normalization + `DevelopmentVersion` registry + SQLite persistence (the full schema) | the join is stored |
| **4** | `devmemory checkpoint` end-to-end (19-step pipeline, run log) + `status` / `history` / `show` | **M1**: real commit + real checkpoint → Version |
| **5** | REST API + dashboard shell (Overview, Timeline, Version Detail, **Development Trace**) + `devmemory serve` | **M2**: the trace, with real diff + real checkpoint |
| **6** | Test + metric collection, status rules, regression detection, feature history | **M3**: SUCCESS/REGRESSION from real evidence |
| **7** | Development memory + previous-attempts retrieval (FTS5) + inline warnings | **M4**: a failed approach is remembered |
| **8** | Version comparison + global search | |
| **9** | Artifacts (`git archive`) + safe restore (dirty-tree refusal, safety tag, preview default) | |
| **10** | Databricks adapter + schema + outbox + Intelligence tab | **M5**: real analytical queries |
| **11** | AI context API + MCP server + `check_before_change` | **M6**: a fresh agent gets the same memory |
| **12** | Entire Graph / impact panel | |
| **13** | AI analysis layer (provider abstraction, fact-guarded) | |
| **14** | `examples/demo-project` + seed script, `devmemory doctor`, e2e test, theming, `DEMO.md` | rehearsed end-to-end demo |

---

## 11. Test strategy

- **Unit**: git parsing (renames, root commit, binary files, CRLF), Entire
  trailer/JSON/git-ref parsing (recorded fixtures), status rules (table-driven),
  regression direction logic, feature detection, version numbering + idempotency, FTS
  ranking, repositories, config precedence, secret redaction, Databricks SQL builders
  (assert the field allowlist), artifact exclusion.
- **Integration**: real temp-git fixture; an `entire enable`d bare fixture repo with an
  attached checkpoint checked into `tests/fixtures/`; the full `checkpoint` pipeline;
  FastAPI routes via `TestClient`; MCP tools via an in-process client; restore safety.
- **E2E**: `init → commit → checkpoint → serve(API) → context/MCP`, asserting the trace
  is consistent across all three surfaces; runs on Windows + Linux CI.
- **Contract**: an opt-in job that runs the *live* Entire CLI and diffs its `--json`
  shapes against the recorded fixtures — early warning on CLI drift.
- Coverage target: 85%+ on `domain/`, `services/`, `pipeline/`, `adapters/git.py`,
  `adapters/entire*.py`.

---

## 12. Demo (the strongest end-to-end story)

`examples/demo-project` — a small task API + auth + calculator (~150 lines, real
pytest suite). Metrics: test pass-rate + endpoint latency + error count. Deliberately
not ML.

Pre-seeded history (real commits; `entire session attach` on genuine transcripts —
never fabricated):

- V1 SUCCESS — auth + task API
- V2 SUCCESS — task filtering (latency 210 → 180 ms)
- V3 **REGRESSION** — "shorten JWT expiry to 30 s" → 6 tests fail
- V4 SUCCESS — fix with a refresh window

Live: ask Claude Code to make token expiry configurable → commit → `devmemory
checkpoint` (V5) → dashboard **Development Trace** → **Compare V4→V5** → open the V3
regression → in a new Claude Code chat, `check_before_change(files=["auth.py"])`
surfaces the V3 mistake and the agent avoids it **on camera** → **Intelligence** tab
(regression leaderboard, "Authentication: 4 attempts, 75% success", `auth.py` churn
hotspot) → restore *preview* of V2.

One sentence: *"Git remembered what changed; Entire remembered why; DevMemory
connected them to the result — and just stopped the next agent from repeating a bug
we shipped last week."*

---

## 13. Risk register

| Risk | Sev | Mitigation |
|---|---|---|
| Demo has no genuine Entire checkpoints | HIGH | enable early; dogfood; `session attach` backfill; rehearse |
| Entire needs `origin` for repo detection | MED | adapter passes `--repo`; demo repo gets an origin |
| Entire CLI output/flags shift (pre-1.0) | MED | `--json` only; `agent-help` as contract; direct git-object fallback |
| Databricks not provisioned in time | MED | local-SQLite analytics parity + outbox |
| No LLM key | MED | rule-based analysis, labelled "heuristic" |
| Restore corrupts uncommitted work | MED | dirty-tree refusal; safety tag + stash ref; preview default |
| CRLF changes hashes/diffs on Windows | LOW | `.gitattributes` + `-c core.autocrlf=false`; hash normalized bytes |
| Double `checkpoint` on one commit | LOW | unique `(project, commit)`; report existing; `--force` |
| Frontend build friction | LOW | commit built assets; wheel ships them |

---

## 14. Documentation still to write

`DEMO.md` (rehearsed runbook), `CONFIGURATION.md` (every key + precedence + which are
secret), concrete Databricks setup steps, the default status/regression thresholds,
"which restore do I want?" (DevMemory restore vs `entire rewind`), and the
`examples/demo-project` spec.
