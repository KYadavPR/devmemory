# Configuration

DevMemory reads configuration in layers, later layers overriding earlier ones:

1. built-in defaults
2. `.devmemory/config.json` — committed, shared with the team
3. `.devmemory/config.local.json` — git-ignored, per-developer overrides
4. environment variables — **secrets only** (never written to any file)

`devmemory init` writes a minimal `config.json`. Unknown keys are rejected, so a
typo fails loudly.

## Secrets (environment only)

DevMemory never stores a credential in a file, a log, the database, a commit, or
an API response. These are read from the environment at the moment they're used:

| Variable | Used for |
| --- | --- |
| `ANTHROPIC_API_KEY` | `anthropic` analysis provider |
| `OPENAI_API_KEY` | `openai` analysis provider |
| `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) | `gemini` analysis provider |
| `DATABRICKS_HOST` / `DATABRICKS_TOKEN` / `DATABRICKS_WAREHOUSE_ID` | Databricks analytics sync (all three required) |
| `DEVMEMORY_LOG_LEVEL` | override log level (`DEBUG` / `INFO` / `WARNING`) |

`devmemory doctor` reports which of these are **present** — never their values.

## `config.json` reference

```jsonc
{
  "project_id": "pricing",          // stable slug, set at init
  "project_name": "Pricing",

  "entire": {
    "enabled": true,
    "binary": null,                 // absolute path to `entire`; null = PATH lookup
    "repo": null                    // "owner/name" if Entire can't auto-detect
  },

  "tests": {
    "command": null,                // e.g. "pytest -q", "npm test", "go test ./..."
    "parser": "auto",               // auto | pytest | junitxml | generic
    "junit_xml": null,              // parse this report instead of stdout
    "timeout_seconds": 900
  },

  "metrics": {
    "file": null,                   // JSON file read after tests; keys become metrics
    "command": null,                // or a command whose JSON stdout provides metrics
    "directions": {}                // {"latency_ms": "lower_is_better", ...}
  },

  "artifacts": {
    "enabled": true,                // a .tar.gz snapshot per version
    "exclude": [".git", ".devmemory", ".venv", "node_modules", "__pycache__", "..."]
  },

  "regression": {
    "metric_pct": 2.0,              // a metric must move > this % to count
    "metric_abs_floor": 1e-9,       // ignore moves smaller than this absolute value
    "high_pct": 15.0,               // >= this % worse  -> HIGH severity
    "medium_pct": 6.0               // >= this % worse  -> MEDIUM severity
  },

  "databricks": {
    "enabled": false,               // off = queue to .devmemory/outbox/ only
    "catalog": "devmemory",
    "schema": "analytics"
  },

  "analysis": {
    "enabled": true,                // false = skip the generate_analysis stage
    "providers": ["rules"],         // fallback chain; "rules" is always the tail
    "model": null,                  // model id for the active LLM provider
    "include_diff": false,          // send a truncated diff to the LLM (off = facts only)
    "max_diff_bytes": 4000
  },

  "graph": {
    "enabled": false,               // change-impact via `entire plugin install graph`
    "binary": null,
    "timeout_seconds": 90,
    "max_seconds": 120              // analysis budget passed to the plugin
  },

  "web": {
    "host": "127.0.0.1",
    "port": 8760,
    "enable_restore": false         // allow the POST restore endpoint on `serve`
  }
}
```

### Turning on the LLM analysis provider

```jsonc
// .devmemory/config.json
"analysis": { "providers": ["anthropic", "rules"] }
```

```bash
export ANTHROPIC_API_KEY=sk-ant-...
devmemory analyze v7        # uses Anthropic; falls back to rules on any failure
```

The `fact_guard` runs on every provider's output: it clamps `risk`, forces it to
at least `medium` when the version's recorded status is adverse, and strips any
secret value that appears in the text. Analysis is stored in its own table and
can never overwrite a Git / test / metric fact.

### Turning on Databricks

```jsonc
"databricks": { "enabled": true, "catalog": "main", "schema": "devmemory" }
```

```bash
export DATABRICKS_HOST=https://dbc-....cloud.databricks.com
export DATABRICKS_TOKEN=dapi...
export DATABRICKS_WAREHOUSE_ID=...
devmemory databricks push
```

Only a fixed 24-field allowlist of normalized telemetry is published — never
source, diffs, transcripts, or secrets. Until it's configured, every version is
still queued locally to `.devmemory/outbox/` and analytics run against SQLite.
