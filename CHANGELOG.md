# Changelog

All notable changes to DevMemory are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
