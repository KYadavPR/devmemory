# Changelog

All notable changes to DevMemory are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed — Dashboard redesign (Vite + React)

- The dashboard is now a Vite + React + TypeScript app (`src/devmemory/web/frontend/`),
  built to `src/devmemory/web/static/` — committed, so `devmemory serve` still
  needs no Node. The old vanilla `src/devmemory/api/static/` bundle is removed.
- New information architecture: **Overview** reads as a narrative (health
  headline, a repeated-failure callout, a version-health strip), a redesigned
  **Version** page with sticky in-page nav and a file-tree diff viewer, a new
  **Safe to change?** page wrapping `POST /api/agent/check` for humans,
  **Timeline** with status/feature filters, and a report-grade **Intelligence**
  page with hand-rolled SVG charts (no chart library).
- New visual system: design tokens with system/light/dark themes (`?theme=`
  override), a ⌘K command palette, skeleton loading, error boundaries, real
  empty states, and a mobile nav.
- `test_dashboard_index_served` updated for the built bundle.

### Added — Phase 14: demo, doctor, docs, end-to-end test

- `devmemory doctor` — checks the toolchain (Python, git, `entire`, the `graph`
  plugin), the project (root, config, schema version), the outbox depth, and
  which integration credentials are *present* (never their values). `--strict`
  exits non-zero on any warning.
- `examples/demo/seed.py` — builds a self-contained demo repo: a small `pricing`
  package with six Development Versions across three features, two regressions,
  and a repeated failed approach, so every view and command has real data.
- `DEMO.md` — a five-minute runbook. `docs/CONFIGURATION.md` — every setting,
  the secrets-from-env table, and the fact/analysis separation.
- `README.md` — a real quickstart replacing the Phase 0 placeholder.
- `tests/test_e2e.py` — one test driving the whole lifecycle through the real
  CLI and dashboard API: init → success/regression/fix checkpoints → history,
  show, compare, analyze, memory → `/api/project`, `/api/analytics`,
  `/api/agent/check`, `doctor`.

### Added — Phase 13: AI analysis layer

- `devmemory.analysis`: a provider fallback chain that turns one version's
  normalized facts into an `Analysis` (summary / reasoning / recommendation /
  warnings / risk). `AnalysisInput` is the only thing a provider sees — Git
  stats, test/metric deltas, regressions, prior attempts, graph hotspots — never
  raw source (a truncated diff only if `analysis.include_diff` is set) and never
  a transcript.
- `RulesProvider` — deterministic, offline, never fails; always the tail of the
  chain. `LLMProvider` — Anthropic / OpenAI / Gemini, one class, lazy SDK import,
  key from the environment; any failure falls through.
- `fact_guard`: runs on every provider's output — clamps `risk` to
  low/medium/high, forces it to at least `medium` when the recorded status is
  adverse, sets `provider`/`model` itself (the model can't spoof them), and
  secret-scrubs + length-caps all free text. Analysis is stored in its own table
  and structurally cannot carry a fact field.
- Pipeline stage `generate_analysis` (after `collect_graph_impact`) — skipped
  when `analysis.enabled = false`, degraded (never fatal) on failure; the version
  and its facts are already persisted.
- CLI `devmemory analyze <ref>` (`--provider`, `--no-save`, `--json`).
- API `POST /api/versions/{ref}/analysis` re-runs the chain. `redact_secrets`
  helper added to `logging`.

### Added — Phase 12: change-impact analysis (Entire `graph` plugin)

- `GraphAdapter`: wraps `entire graph commit --json` (the official, no-egress
  local code graph). Discovers the `entire-graph` binary in the managed plugin
  dirs; degrades to `None` when missing or slow — never blocks a checkpoint.
  Parses the entity-level change list (added / removed / renamed /
  signature-changed / body-changed) with per-entity dependent counts; `hotspots`
  ranks the risky ones.
- Opt-in: needs `entire plugin install graph` and `graph.enabled = true`. New
  `GraphSettings` config section (binary, timeouts).
- Migration `0003_graph.sql` + `GraphImpactRepository` — one row per version,
  full JSON payload plus denormalized summary columns. Local-only; never
  published to Databricks.
- Pipeline stage `collect_graph_impact` (after `refresh_feature`) — skipped when
  disabled/uninstalled, degraded on analysis failure.
- `services.impact.version_impact`: stored result, or computed once on demand.
- CLI `devmemory impact <ref>` (`--json`, `--stored-only`): the entity change
  list, a hotspots table, and a "review before keeping" callout for
  signature/removal changes with dependents.
- API `GET /api/versions/{ref}/impact`. Dashboard: a "Change impact" panel on the
  version page. MCP tool `get_change_impact`.

### Added — Phase 11: AI context API + MCP server

- `services.agent_context`: agent-facing, JSON-first shapes shared by the MCP
  server and the REST `/api/agent/*` endpoints. `project_brief` (orientation:
  HEAD/branch, checkpoint coverage, success rate, open features, recent adverse
  versions, cautions), `recent_history`, `version_report` (brief + trace),
  and `change_guidance` — a pre-flight risk read that returns a verdict
  (`proceed` / `caution` / `high-risk`) with the specific prior failures to read.
  Facts and rule-based reads only; no LLM interpretation.
- `devmemory mcp`: a read-only [MCP](https://modelcontextprotocol.io) server over
  stdio (`fastmcp`). Tools: `get_project_context`, `get_version_history`,
  `get_version`, `get_development_trace`, `get_previous_attempts`,
  `check_before_change`, `search_versions`, `get_analytics`. `--print-config`
  emits a ready `.mcp.json` fragment for the current repo. Requires the `mcp`
  extra; a clear error otherwise.
- API: `GET /api/agent/context`, `GET /api/agent/history`, `POST /api/agent/check`.
- `docs/MCP.md`: wiring for Claude Code / Cursor, the tool table, the REST
  equivalent.

### Added — Phase 10: development intelligence + Databricks analytics

- `services.analytics.analytics_summary`: one report — regression leaderboard,
  feature attempt/success/regression counts, file churn (with an adverse-change
  ratio), agent effectiveness (success rate, tokens per success), a per-version
  trend, and repeatedly-failed approaches (adverse versions clustered by their
  exact changed-file signature, ≥2 occurrences). Carries a `source` field:
  `local` (SQLite, always available — the demo path) or `databricks`.
- `adapters.databricks.DatabricksAdapter`: REST-only publishing and querying via
  the SQL Statement Execution API against a serverless SQL warehouse — no Spark,
  no cluster. `bootstrap()` creates a Delta star schema (`fact_versions` +
  `fact_changed_files` / `fact_metrics` / `fact_tests` / `fact_regressions`);
  `publish_version()` is an idempotent `MERGE`. Every value travels as a bound
  named `:param`; table names come only from trusted `catalog`/`schema` config.
- Only a fixed 24-field allowlist (`_VERSION_FIELDS`) ever leaves the machine —
  never source, diffs, transcripts, prompts, or secrets. The intent string is
  truncated to 2000 chars. Credentials come from `DATABRICKS_HOST` /
  `DATABRICKS_TOKEN` / `DATABRICKS_WAREHOUSE_ID` only.
- `services.databricks_sync`: an offline outbox. Every published version is
  written to `.devmemory/outbox/<version>.json` first; if Databricks is
  configured and reachable the pipeline pushes immediately and removes the file,
  otherwise it stays queued. Local history never depends on any of this — a push
  failure degrades the run, it does not abort it.
- Pipeline stage `publish_databricks` (before `create_artifact`): `skipped` when
  not configured (queued to the outbox), `degraded` on a push failure.
- CLI: `devmemory analytics` (`--json`) and `devmemory databricks status` /
  `devmemory databricks push`.
- API: `GET /api/analytics`.
- Dashboard: an **Intelligence** tab — the regression leaderboard, feature
  attempts, file churn, agent effectiveness, an SVG trend sparkline, and the
  repeatedly-failed-approaches callout, badged by `source`.

### Added — Phase 9: project snapshots + safe restore

- `ArtifactStore`: a `.tar.gz` snapshot per version, built from `git archive`
  (the committed tree, no working-tree noise), repacked through `tarfile` to
  apply exclusions and record a deterministic sha256. Pipeline stage
  `create_artifact` (skippable with `--no-snapshot` or `artifacts.enabled`).
- `GitAdapter` gains its only mutating operations: `archive_tar`, `create_tag`,
  `stash_create` (a pure safety reference), `checkout_detached`, `reset_hard`.
- `services.restore`: `restore_preview` (reports the target commit, current HEAD,
  dirty files, and the safety-tag name — touches nothing) and `restore_version`
  — refuses a dirty tree unless `allow_dirty`, always writes a `devmemory/safety/<ts>`
  tag at the current HEAD (plus a `git stash create` ref if dirty) *before*
  moving HEAD, detached checkout by default, `--hard` only on explicit request,
  records a `restore` event, and returns the exact recovery command.
- CLI: `devmemory restore <ref>` (`--yes`, `--hard`, `--allow-dirty`, `--json`) —
  previews and prompts by default.
- API: `GET /api/versions/{ref}/restore/preview` and `POST .../restore`
  (403 unless the server was started with `--enable-restore`).
- `devmemory show` now lists the version's snapshot.

### Added — Phase 8: version comparison + search CLI

- CLI: `devmemory diff FROM TO` (raw git diff), `devmemory compare FROM TO`
  (`--diff`, `--json`) — files by change type, line totals, metric deltas, test
  deltas, status transition — and `devmemory search QUERY` (`--json`).
- `VersionDiff` / `/api/compare` now also report the version numbers, feature
  transition, and the checkpoint on each side.
- Dev: `pytest-xdist`; CI runs the suite with `-n auto` (~4x faster).

### Added — Phase 7: development memory / previous attempts

- `services.memory.previous_attempts`: given a scope (files being changed,
  feature, intent), rank historical versions by changed-file overlap + feature
  match + intent-keyword overlap (FTS) + adverse status. Returns each with a
  "why this matched", a one-line result summary, and a recommendation. Failed and
  regressed attempts only, unless successes are requested.
- Pipeline stage `check_previous_attempts`: warns during `devmemory checkpoint`
  when the current change resembles a past regression ("similar prior attempt
  V2 [REGRESSION] — …").
- CLI: `devmemory memory` (`--file`, `--feature`, `--intent`,
  `--include-successes`, `--json`).
- API: `GET /api/attempts` and `GET /api/versions/{ref}/attempts`.
- Dashboard: the Memory tab now scores real previous attempts; the Version
  detail page shows a "⚠ Previous attempts touching this area" panel.

### Added — Phase 6: test + metric collection, regression detection

- `TestAdapter`: runs the configured `tests.command` and normalizes the result —
  pytest / go / generic stdout parsers, a JUnit XML reader, timeout handling. A
  non-zero exit with no parsed failures still counts as failed. Collection
  failures degrade the run (the version is still recorded), they don't abort it.
- `MetricsAdapter`: reads metrics from a JSON file or a command's JSON stdout;
  scalar (`{"accuracy": 93.4}`) and object (`{"latency": {"before", "after",
  "unit"}}`) shapes; direction from config, then a name heuristic.
- `pipeline.regression.detect_regressions`: direction-aware metric comparison
  against the previous relevant version (configurable percent threshold +
  severity bands) and test comparison (newly-failing / dropped-passing). The
  version's `before` is backfilled from the previous version's `after`.
- `status_rules.derive_status` now returns `REGRESSION` when regressions are
  present.
- Pipeline stages added: `collect_metrics`, `detect_regression`,
  `refresh_feature` (recomputes the feature's roll-up status from its versions).
- `services.features`: `refresh_feature_status`, feature roll-up
  (`COMPLETE`/`PARTIAL`/`FAILED`/`IN_PROGRESS` from the latest version).
- CLI: `devmemory checkpoint` gains `--run-tests/--no-run-tests` and
  `--metrics-file`. Config gains a `regression` section (thresholds).

### Added — Phase 5: REST API + dashboard

- FastAPI app (`devmemory.api`): `/api/project` (+ `/api/status`), `/api/versions`,
  `/api/versions/{ref}` (resolves `v7` / `7` / sha-prefix), `.../diff`,
  `.../checkpoint`, `.../trace`, `/api/compare?from&to`, `/api/features`,
  `/api/features/{ref}`, `/api/search`, `/api/health`, OpenAPI at `/api/docs`.
  Per-request `ProjectContext` (own SQLite connection); domain errors map to
  404/400.
- `services.trace.build_trace`: the development trace — intent → agent → Entire
  checkpoint → commit → files → tests → metrics → status → analysis — as an
  ordered node list the UI draws as a connected chain.
- `services.features`: feature roll-up status and per-feature version history.
- Dashboard: a dependency-free, hash-routed single-page app served from the wheel
  (`devmemory serve`) — Overview, Timeline, Version detail (record + trace +
  metrics + files + syntax-coloured diff), Compare, Features, Memory (failed
  approaches), Search. Light/dark theme with a toggle; design-token CSS.
- `devmemory serve` (`--host`, `--port`, `--open/--no-open`, `--enable-restore`):
  picks a free port, opens the browser, runs uvicorn.

### Added — Phase 4: `devmemory checkpoint` end-to-end

- The checkpoint pipeline (`devmemory.pipeline`): an ordered, individually-timed
  set of stages — verify repo, resolve commit, check working tree, idempotency,
  resolve Entire checkpoint, collect changes, environment, detect feature,
  collect tests, determine status, build event, persist — each recorded in a
  `RunLog` written to `.devmemory/runs/<run_id>.json`. Cloud/optional steps never
  fail the run.
- Missing-checkpoint policy: `checkpoint` refuses without an Entire checkpoint
  unless `--allow-no-entire`; uncertain (heuristic) associations are surfaced as
  warnings. Dirty working tree is warned, not blocked.
- `feature_detect`: explicit flag → conventional-commit scope → intent keywords.
- `status_rules.derive_status`: explicit override → errors → regressions → test
  outcome → needs-review.
- CLI: `devmemory checkpoint` (`--intent`, `--feature`, `--agent`, `--status`,
  `--tests-passed/-failed`, `-m name=before:after`, `-e error`,
  `--allow-no-entire`, `--force`, `--json`), `devmemory history` (timeline
  table), `devmemory show <v7|7|sha> [--diff] [--json]` (full record with metric
  direction, file marks, analysis panel, syntax-highlighted diff).
- `devmemory status` now reports version count, latest version/status/metrics,
  in-progress features, last regression, and whether HEAD is recorded.
- Global `-v/--verbose`; CLI logs default to WARNING. Windows console output is
  forced to UTF-8. structlog uses a lazy stderr factory (survives pytest capture).

### Added — Phase 3: normalized event + version registry + persistence

- Migration `0002_versions`: the full schema — `versions` (with version number,
  association method/confidence, environment + source-event JSON, run id, distinct
  recorded/committed times), `changed_files`, `entire_checkpoints`,
  `version_checkpoints` (many-to-many), `features`, `tests`, `metrics`,
  `regressions`, `analysis` (1:1, kept separate from facts), `artifacts`,
  `doc_flags`, `events`, plus an FTS5 `version_search` table and indexes.
- Domain: `DevelopmentEvent` (the normalized bridge adapters fill), `Metric`
  (direction-aware, with delta / percent-change / improvement helpers),
  `TestOutcome`, `Regression`, `Analysis`, `Artifact`, `DocFlag`, `Feature`, and
  the persisted `DevelopmentVersion` record joining all of it.
- `VersionRepository`: numbering, idempotent lookup by commit, `create` /
  `replace` (for `--force`) writing every child table in one transaction, full
  hydration, `previous_relevant` (for regression detection), and FTS-backed
  `search_ids` with a `LIKE` fallback.
- `CheckpointRepository` (upsert + version linking), `FeatureRepository`.
- Services (`devmemory.services.versions`): `create_version_from_event`
  (idempotent; `--force` re-records in place), `get_version` (resolves
  `v7`/`7`/sha-prefix), `list_versions`, `version_diff` (real git diff + metric
  and test deltas), `search_versions`. Every create writes an audit `events` row.

### Added — Phase 2: Entire checkpoint resolution

- `EntireAdapter.resolve_for_commit()` implements the association ladder:
  `Entire-Checkpoint` git trailer (confidence 1.0) → `entire checkpoint explain
  --commit --json` for session metadata → direct read of the
  `refs/entire/checkpoints/<shard>/<id>` git object tree (offline; supplies the
  intent from `<idx>/prompt.txt`, which the CLI envelope never includes) →
  time-proximity heuristic against `entire checkpoint list --json` (confidence
  ≤ 0.5, marked uncertain) → `None`. Checkpoint data is never fabricated.
- `EntireAdapter.get_checkpoint()`, `list_checkpoints()`, `transcript()`.
- Normalized `CheckpointReference` carries the association method + confidence,
  the resolving git ref, per-session metadata, and merged token usage.
- `ProjectContext` now wires the Entire adapter (with the git adapter injected).
- Integration tests run against the real installed Entire CLI when present, as an
  early-warning signal for `--json` shape drift.

### Added — Phase 1: `devmemory init` + Git adapter

- `GitAdapter` (`devmemory.adapters.git`): subprocess-based, no GitPython. Repo
  detection, HEAD/branch/commit metadata with parsed trailers, `Entire-Checkpoint`
  trailer extraction, NUL-delimited name-status + numstat diff parsing (adds,
  deletes, renames, binary), root-commit handling, working-tree state, ref-blob
  reads for Entire checkpoint refs later.
- `EntireAdapter.probe()` (`devmemory.adapters.entire`): detects whether the
  Entire CLI is installed and enabled, its version and configured agents.
  Degrades gracefully; never fabricates.
- Domain models (`devmemory.domain.models`): `CommitInfo`, `ChangedFile`,
  `DiffStat`, `WorkingTreeState`, `CheckpointReference` (+ sessions, token usage,
  association method/confidence), `EntireStatus`, `Project`, `EnvironmentInfo`.
- `devmemory.environment`: best-effort toolchain snapshot (Python, platform,
  git, Entire, package manager).
- Storage: `ProjectRepository` — the single place `projects` SQL lives.
- Services: `ProjectContext` (the wired bundle every entry point works through)
  and `devmemory.services.projects` (`init_project`, `project_status`).
- CLI: `devmemory init` (`--name`, `--project-id`, `--force`, `--json`) and
  `devmemory status` (`--json`), with shared Rich rendering and a `handle_errors`
  decorator that maps the error taxonomy to exit codes under the CLI runner.
- `init` writes `.devmemory/config.json`, creates and migrates the database,
  registers the project, and appends local-only paths to the repo `.gitignore`.

### Added — Phase 0: repository & package foundation

- `devmemory` / `dm` console entry points with `--version` and a `version` command
  that reports the detected toolchain (Python, git, Entire).
- Layered project configuration (`devmemory.config`): built-in defaults →
  `.devmemory/config.json` → `.devmemory/config.local.json` → environment. Secrets
  (Databricks token, LLM API keys) are resolved from the environment only and are
  never loaded into the config object or written to disk.
- Project filesystem layout (`devmemory.paths`): a single `.devmemory/` directory,
  with upward-walking project-root discovery.
- Structured logging (`devmemory.logging`) built on structlog, with a redaction
  processor that scrubs sensitive keys and any live environment-secret value.
- Typed error taxonomy (`devmemory.domain.errors`) — every deliberate failure carries
  a message, an optional next-step hint, and a CLI exit code.
- Domain enumerations (`devmemory.domain.enums`): version/feature status, change type,
  metric direction, checkpoint association method.
- SQLite layer (`devmemory.storage`): connection management (WAL, foreign keys) and a
  forward-only, transactional schema migration runner.
- Continuous integration: ruff, ruff-format, mypy (strict), and pytest on Linux and
  Windows across Python 3.11–3.13.
- `docs/IMPLEMENTATION_STRATEGY.md` — the engineering audit and phased build plan.
