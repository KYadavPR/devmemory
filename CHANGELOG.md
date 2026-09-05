# Changelog

All notable changes to DevMemory are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
