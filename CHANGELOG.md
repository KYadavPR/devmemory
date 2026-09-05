# Changelog

All notable changes to DevMemory are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
