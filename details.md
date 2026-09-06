# DevMemory — Project Details

> **Development-memory and version-intelligence for AI-assisted software development.**
>
> Git remembers *what* changed. Entire remembers the AI-assisted development *context*.
> DevMemory connects those changes with results, metrics, feature status and previous
> attempts — so developers and future AI agents can understand the complete development
> history, and avoid repeating past mistakes.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Core Concept](#2-core-concept)
3. [Features](#3-features)
4. [Architecture](#4-architecture)
5. [System Components](#5-system-components)
6. [Repository Structure](#6-repository-structure)
7. [Technology Stack](#7-technology-stack)
8. [Workflow](#8-workflow)
9. [State-Aware Coding Loop](#9-state-aware-coding-loop)
10. [Integrations](#10-integrations)
11. [CLI Reference](#11-cli-reference)
12. [REST API](#12-rest-api)
13. [MCP Server](#13-mcp-server)
14. [Dashboard](#14-dashboard)
15. [Configuration](#15-configuration)
16. [Development & Build](#16-development--build)
17. [Build Phases](#17-build-phases)

---

## 1. Project Overview

DevMemory is a **development-memory and version-intelligence platform** for AI-assisted software development.

It is a reusable Python package that integrates into any existing software project and works alongside existing tools — VS Code, Cursor, Claude Code, Antigravity, Gemini CLI, Kiro, and any CI/CD pipeline.

### What it is NOT

- Not an IDE
- Not a Git replacement
- Not an MLflow replacement
- Not an AI coding agent
- Not a code editor
- Not a custom version-control system

### What it IS

A development-memory layer that:
- Joins each AI-assisted change with its **full context** (intent, agent, Entire checkpoint, diff, tests, metrics)
- Stores this context as a durable **Development Version**
- Exposes version history via a **visual dashboard** for humans
- Exposes version history via an **MCP server + REST API** for the next AI agent

---

## 2. Core Concept

The central concept:

```
AI/developer intent → AI agent activity → Entire Checkpoint → Git commit
→ tests/metrics/results → Development Version → project history + analytics
→ future developer/AI agent understands what happened
```

A Development Version answers: what was requested, why, by which agent, which files changed, what tests passed/failed, what metrics changed, which prior approaches failed, and more.

---

## 3. Features

### 3.1 Development Version Recording

Each meaningful AI-assisted commit becomes a durable record joining:
- The Entire checkpoint (prompt, agent, session)
- The Git commit (exact diff, files, lines added/deleted)
- Test results (pytest/go/generic/JUnit XML)
- Metrics (accuracy, latency, error rate)
- Regression detection
- Feature tracking
- AI analysis (kept strictly separate from facts)

### 3.2 Development Memory

Given a scope (files, feature, intent), ranks historical versions by changed-file overlap, feature match, intent-keyword overlap (FTS), and adverse status. Warns during `checkpoint` when the current change resembles a past regression.

### 3.3 Version Intelligence

- `devmemory history` — development timeline
- `devmemory show` — one version, end-to-end
- `devmemory compare` — metric/test deltas between versions
- `devmemory search` — full-text search
- `devmemory memory` — has this area failed before?
- `devmemory analytics` — regressions, feature attempts, file churn, agent effectiveness

### 3.4 Safe Restore

Preview restore without mutations. Always writes a safety tag at current HEAD before moving. Stash-creates if dirty. Records a restore event.

### 3.5 Change-Impact Analysis (Entire graph plugin)

Wraps `entire graph commit --json`. Detects entity-level changes (added/removed/renamed/signature-changed/body-changed). Ranks hotspots by dependent count.

### 3.6 AI Analysis Layer

Provider fallback chain: LLMProvider (Anthropic/OpenAI/Gemini) → RulesProvider (deterministic, offline). fact_guard prevents model from spoofing provider/model fields or overwriting facts.

### 3.7 Databricks Analytics

Publishes a fixed 24-field allowlist to a Delta star schema (fact_versions + dimension tables). Offline outbox queues versions if Databricks is unreachable. Source/diffs/transcripts/prompts/secrets never leave the machine.

### 3.8 State-Aware Coding Loop

A closed feedback loop around an AI coding agent exposing Task management, State Engine, and MCP tools. See Section 9.

### 3.9 Visual Dashboard

Vite + React + TypeScript SPA with: Overview, Version detail, Safe to change?, Timeline, Intelligence, Features, Memory, Search. Dark/light/system themes, command palette, mobile nav.

---

## 4. Architecture

### 4.1 Architectural Principles

1. **Do not replace existing tools** — wrap them behind adapters
2. **Git is the source of truth for code** — store references, not a copy
3. **Entire is the source of truth for AI context** — store checkpoint reference, not the session
4. **DevMemory owns the normalized development record** — the join of all adapters
5. **Adapters isolate external systems** — EntireAdapter, GitAdapter, TestAdapter, MetricsAdapter, DatabricksAdapter, GraphAdapter
6. **Analysis is strictly separated from facts** — separate table, can never overwrite a fact

### 4.2 High-Level Architecture

```
Developer / AI Agent
        |
Existing Dev Tools (Claude Code / VSCode / Cursor / Terminal)
        |
     Entire (AI session/checkpoint)
        |
  ------+------
  |            |
 Git      Test/Metrics adapters
  |            |
  +-----+------+
        |
   DevMemory Core
   (DevelopmentVersion, DevelopmentEvent, Feature, Analysis)
        |
  ------+-------+----------+
  |             |          |
SQLite      Artifacts   Databricks
  |             |          |
  +------+-------+---------+
         |
   FastAPI Web Server
         |
  -------+--------
  |               |
Dashboard     AI Context / MCP
(Vite+React)  (fastmcp)
```

### 4.3 Checkpoint Pipeline Stages

```
verify_repo → resolve_commit → check_working_tree → idempotency
→ resolve_entire_checkpoint → collect_changes → collect_environment
→ detect_feature → collect_tests → collect_metrics
→ check_previous_attempts → collect_graph_impact → generate_analysis
→ determine_status → build_event → persist → publish_databricks → create_artifact
```

Each stage is individually timed; cloud/optional stages never abort the run on failure.

### 4.4 Entire Checkpoint Association Ladder

1. `Entire-Checkpoint` git trailer (confidence 1.0)
2. `entire checkpoint explain --commit --json`
3. Direct read of `refs/entire/checkpoints/<shard>/<id>` (offline)
4. Time-proximity heuristic (confidence ≤ 0.5, marked uncertain)
5. None — no fabrication

---

## 5. System Components

| # | Component | Location | Description |
|---|---|---|---|
| 1 | CLI | `src/devmemory/cli/` | Typer CLI, all commands |
| 2 | Core domain | `src/devmemory/domain/` | Models, enums, errors |
| 3 | Adapters | `src/devmemory/adapters/` | Git, Entire, Test, Metrics, Databricks, Graph |
| 4 | Pipeline | `src/devmemory/pipeline/` | Ordered stages; checkpoint orchestration |
| 5 | Services | `src/devmemory/services/` | versions, features, memory, analytics, restore, agent_context, taskloop |
| 6 | Storage | `src/devmemory/storage/` | SQLite + migrations + repositories |
| 7 | Analysis | `src/devmemory/analysis/` | LLM + rules provider chain, fact_guard |
| 8 | REST API | `src/devmemory/api/` | FastAPI app and all endpoints |
| 9 | MCP Server | `src/devmemory/mcp/` | fastmcp-based, read-only + task-loop tools |
| 10 | Web | `src/devmemory/web/` | FastAPI static serving + Vite/React frontend |
| 11 | Config | `src/devmemory/config.py` | Layered config; secrets from env only |
| 12 | Paths | `src/devmemory/paths.py` | .devmemory/ layout, upward-walking discovery |
| 13 | Logging | `src/devmemory/logging.py` | structlog + secret redaction |
| 14 | Environment | `src/devmemory/environment.py` | Toolchain snapshot |

---

## 6. Repository Structure

```
devmemory/
├── pyproject.toml                  # build, deps, lint, test config
├── README.md
├── CHANGELOG.md
├── DEMO.md
├── AGENTS.md                       # agent operating protocol
├── LICENSE
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── PROJECT_SPEC.md
│   ├── IMPLEMENTATION_STRATEGY.md
│   ├── CONFIGURATION.md
│   ├── DATA_AND_API_SPEC.md
│   ├── ENTIRE_INTEGRATION.md
│   ├── ENTIRE_QUICKSTART.md
│   ├── MCP.md
│   └── STATE_LOOP.md
│
├── src/
│   └── devmemory/
│       ├── adapters/         # external system wrappers
│       ├── analysis/         # AI analysis provider chain
│       ├── api/              # FastAPI REST server
│       ├── cli/              # Typer CLI app
│       ├── domain/           # models, enums, errors
│       ├── mcp/              # MCP server (fastmcp)
│       ├── pipeline/         # checkpoint pipeline stages
│       ├── services/         # business logic
│       ├── storage/          # SQLite + migrations + repos
│       └── web/
│           ├── frontend/     # Vite + React + TypeScript SPA
│           └── static/       # built bundle (committed)
│
├── tests/
│   └── test_e2e.py           # end-to-end lifecycle test
│
└── examples/
    └── demo/
        └── seed.py           # seeded demo repo builder
```

---

## 7. Technology Stack

### Backend

| Layer | Technology |
|---|---|
| Language | Python >= 3.11 |
| CLI framework | Typer + Rich |
| Data validation | Pydantic v2 |
| Structured logging | structlog |
| REST API | FastAPI + uvicorn |
| Templating | Jinja2 |
| Local storage | SQLite (WAL, forward-only migrations) |
| MCP server | fastmcp |
| Env management | python-dotenv |

### Optional Integrations

| Integration | Package | Purpose |
|---|---|---|
| Databricks | databricks-sdk | Delta Lake analytics |
| Anthropic | anthropic | LLM analysis |
| OpenAI | openai | LLM analysis |
| Google Gemini | google-genai | LLM analysis |

### Frontend

| Layer | Technology |
|---|---|
| Framework | React 18 + TypeScript |
| Build tool | Vite |
| Charts | Hand-rolled SVG (no chart library) |
| Styling | Design-token CSS |
| Routing | Hash-based SPA routing |

### Developer Toolchain

| Tool | Purpose |
|---|---|
| ruff | Linting + formatting |
| mypy (strict) | Static type checking |
| pytest + pytest-xdist | Parallel test suite |
| pytest-cov | Coverage |
| hatchling | Build backend |

---

## 8. Workflow

### Quickstart

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev]"
cd your-repo
devmemory init --name "My Project"
devmemory checkpoint --intent "what you were trying to do"
devmemory serve
```

### Key Commands

```bash
devmemory history                 # the timeline
devmemory show v7                 # one version, end to end
devmemory compare 6 7             # what changed + metric/test deltas
devmemory memory --file auth.py   # has this area failed before?
devmemory analyze v7              # interpretation (rules or LLM)
devmemory analytics               # regressions, feature attempts, file churn
devmemory serve                   # the dashboard
devmemory mcp --print-config      # wire MCP into Claude Code / Cursor
devmemory doctor                  # check the setup
```

---

## 9. State-Aware Coding Loop

A closed feedback loop around an AI coding agent. The State Engine aggregates Git + Entire + tests + graph into one normalized state and evidence-based status.

```
human task -> normalize into requirements -> agent inspects repo -> edits code
-> tests -> commit -> Entire checkpoint -> refresh_state -> new state
-> agent continues (NEEDS_WORK) / stops (READY) / escalates (BLOCKED)
```

### Status Meanings

| Status | Meaning |
|---|---|
| IN_PROGRESS | Actively being worked on; no completion evaluation yet |
| NEEDS_WORK | A requirement is incomplete, tests fail, or an issue is open |
| READY | Requirements satisfied, tests pass, no open issues, tree clean |
| BLOCKED | Cannot safely continue; human/external decision needed |

### MCP Loop Tools

| Tool | Use |
|---|---|
| create_task(goal, test_command?) | Start a task, normalize requirements, pin base commit |
| get_state(task_id) | Current normalized state |
| refresh_state(task_id) | Re-run every collector, recompute status, store snapshot |
| set_requirement_status(task_id, req_id, status, note) | Record verdict for a requirement |
| report_issue(task_id, description, blocking?) | Record unresolved item |
| mark_complete(task_id) | Request completion evaluation |
| get_checkpoint(checkpoint_id) | Metadata for one Entire checkpoint |

### Agent Protocol (AGENTS.md)

1. Before starting: get_state(task_id)
2. Read recommended_focus, unresolved, failing requirements
3. Inspect the actual repository (state is evidence, not a patch)
4. Make code changes
5. Run tests, fix failures
6. Commit source changes to main
7. For each verified requirement: set_requirement_status(task_id, "R<n>", "COMPLETE", ...)
8. refresh_state(task_id) → read overall_status
9. NEEDS_WORK: continue | BLOCKED: explain | READY: stop

---

## 10. Integrations

### Entire (Required for full value)

Source of truth for *why* a change was made. DevMemory reads:
- Checkpoint ID and session metadata
- Original developer prompt
- AI agent used
- Token usage
- Association with the Git commit

### Git (Required)

Subprocess-based (no GitPython). Reads HEAD/branch/commit, diff stats, changed files, working tree state, Entire-Checkpoint trailer.

### Databricks (Optional)

Set DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_WAREHOUSE_ID. Publishes 24 sanitized fields to a Delta star schema. Offline outbox ensures local history never depends on connectivity.

### LLM Analysis (Optional)

Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY. Falls back to deterministic RulesProvider when no key is set or LLM call fails.

### Entire Graph Plugin (Optional)

Install with: entire plugin install graph
Enable in config: {"graph": {"enabled": true}}
Provides entity-level change analysis and hotspot detection.

---

## 11. CLI Reference

```
devmemory init --name NAME
devmemory status
devmemory doctor [--strict]

devmemory checkpoint --intent TEXT [--feature F] [--agent A] [--status S]
  [--tests-passed/--tests-failed] [-m name=before:after] [-e ERROR]
  [--allow-no-entire] [--force] [--no-snapshot] [--json]

devmemory history
devmemory show REF [--diff] [--json]
devmemory compare FROM TO [--diff] [--json]
devmemory diff FROM TO
devmemory search QUERY [--json]

devmemory memory [--file PATH] [--feature F] [--intent I] [--json]
devmemory analytics [--json]
devmemory analyze REF [--provider P] [--no-save] [--json]
devmemory impact REF [--json] [--stored-only]

devmemory restore REF [--yes] [--hard] [--allow-dirty] [--json]

devmemory databricks status
devmemory databricks push

devmemory task new GOAL [--test COMMAND]
devmemory task state [TASK_ID]
devmemory task refresh [TASK_ID]
devmemory task complete [TASK_ID]
devmemory task requirement REQ_ID -s STATUS -m NOTE
devmemory task issue DESCRIPTION [--blocking]
devmemory task resolve ISSUE_ID
devmemory task list
devmemory task history [TASK_ID]

devmemory serve [--host H] [--port P] [--open/--no-open] [--enable-restore]
devmemory mcp [--print-config]
```

---

## 12. REST API

| Method | Endpoint | Description |
|---|---|---|
| GET | /api/project | Project metadata + status |
| GET | /api/versions | All versions (timeline) |
| GET | /api/versions/{ref} | One version |
| GET | /api/versions/{ref}/diff | Raw git diff |
| GET | /api/versions/{ref}/checkpoint | Entire checkpoint |
| GET | /api/versions/{ref}/trace | Development trace |
| GET | /api/versions/{ref}/impact | Change-impact analysis |
| GET | /api/versions/{ref}/attempts | Previous attempts |
| GET | /api/versions/{ref}/restore/preview | Preview restore |
| POST | /api/versions/{ref}/restore | Execute restore |
| POST | /api/versions/{ref}/analysis | Re-run analysis |
| GET | /api/compare | Compare two versions |
| GET | /api/features | All features |
| GET | /api/features/{ref} | One feature |
| GET | /api/search | Full-text search |
| GET | /api/analytics | Analytics summary |
| GET | /api/attempts | All previous-attempt queries |
| GET | /api/agent/context | Project brief for AI agents |
| GET | /api/agent/history | Recent history for agents |
| POST | /api/agent/check | Pre-flight risk check |
| GET | /api/health | Health check |
| GET | /api/docs | OpenAPI docs |

---

## 13. MCP Server

Wire into Claude Code / Cursor:

```bash
devmemory mcp --print-config
```

### Read-Only Tools

| Tool | Description |
|---|---|
| get_project_context | Project orientation brief |
| get_version_history | Recent version timeline |
| get_version | One version by ref |
| get_development_trace | Development trace for a version |
| get_previous_attempts | Prior attempts for a file/feature scope |
| check_before_change | Pre-flight risk verdict |
| search_versions | Full-text search |
| get_analytics | Analytics summary |
| get_change_impact | Graph-based change-impact |

### Task-Loop Tools

| Tool | Description |
|---|---|
| create_task | Create task, normalize requirements, pin base commit |
| get_state | Current normalized state |
| refresh_state | Re-collect evidence, recompute status, store snapshot |
| set_requirement_status | Record verdict for a requirement |
| report_issue | Record an unresolved item |
| mark_complete | Request completion evaluation |
| get_checkpoint | Metadata for one Entire checkpoint |

---

## 14. Dashboard

A Vite + React + TypeScript SPA served from the committed built bundle (no Node.js at runtime).

### Pages

| Page | Description |
|---|---|
| Overview | Health headline, repeated-failure callout, version-health strip |
| Version | Full detail: intent, agent, checkpoint, diff, tests, metrics, analysis, trace |
| Safe to change? | Human wrapper for POST /api/agent/check |
| Timeline | All versions with status/feature filters |
| Intelligence | Regression leaderboard, feature attempts, file churn, SVG charts |
| Features | All features with roll-up status |
| Memory | Previous failed approaches |
| Search | Full-text search across all versions |

### Design

- Design tokens with system/light/dark themes
- Command palette (Cmd+K)
- Skeleton loading, error boundaries, real empty states
- Mobile navigation

### Rebuilding

```bash
cd src/devmemory/web/frontend
npm install && npm run build
```

The built bundle is committed to `src/devmemory/web/static/`.

---

## 15. Configuration

Config is layered (lowest to highest priority):
1. Built-in defaults
2. `.devmemory/config.json` (project config)
3. `.devmemory/config.local.json` (personal, gitignored)
4. Environment variables

### Key Settings

```json
{
  "tests": { "command": "pytest -q", "timeout": 300 },
  "metrics": { "file": "metrics.json" },
  "analysis": { "enabled": true, "include_diff": false },
  "artifacts": { "enabled": true },
  "graph": { "enabled": false },
  "databricks": { "catalog": "my_catalog", "schema": "devmemory" },
  "regression": { "threshold_pct": 5.0 }
}
```

### Secrets (Environment Only)

```
ANTHROPIC_API_KEY       LLM analysis
OPENAI_API_KEY          LLM analysis
GEMINI_API_KEY          LLM analysis
DATABRICKS_HOST         Workspace URL
DATABRICKS_TOKEN        Personal access token
DATABRICKS_WAREHOUSE_ID SQL warehouse ID
```

Copy `.env.example` to `.env` and fill in what you need.

---

## 16. Development & Build

```bash
# Lint + format check
ruff check . && ruff format --check .

# Type check (strict)
mypy

# Tests (parallel)
pytest -n auto

# Tests with coverage
pytest --cov=devmemory --cov-report=term-missing

# Demo
python examples/demo/seed.py /tmp/devmemory-demo && cd /tmp/devmemory-demo
devmemory serve

# Health check
devmemory doctor
```

---

## 17. Build Phases

| Phase | What was built |
|---|---|
| Phase 0 | Repository & package foundation: entry points, config, logging, SQLite migration runner, CI |
| Phase 1 | devmemory init + GitAdapter, EntireAdapter probe |
| Phase 2 | Entire checkpoint resolution (4-level association ladder) |
| Phase 3 | Normalized event + version registry + full SQLite schema (16 tables + FTS5) |
| Phase 4 | devmemory checkpoint end-to-end pipeline (ordered stages, RunLog, idempotency) |
| Phase 5 | FastAPI REST API + initial dashboard (dependency-free SPA) |
| Phase 6 | Test + metric collection, regression detection |
| Phase 7 | Development memory / previous attempts (FTS + overlap ranking) |
| Phase 8 | Version comparison + search CLI |
| Phase 9 | Project snapshots + safe restore (git archive, safety tags) |
| Phase 10 | Development intelligence + Databricks analytics (Delta star schema, outbox) |
| Phase 11 | AI context API + MCP server (read-only tools, agent risk check) |
| Phase 12 | Change-impact analysis (Entire graph plugin, entity-level hotspots) |
| Phase 13 | AI analysis layer (LLM chain, RulesProvider, fact_guard) |
| Phase 14 | Demo, doctor, docs, end-to-end test |
| Dashboard redesign | Vite + React + TypeScript SPA (design tokens, SVG charts, mobile nav) |
| State-aware loop | Task layer, State Engine, MCP loop tools, AGENTS.md protocol |

---

*DevMemory — MIT License — https://github.com/KYadavPR/devmemory*
