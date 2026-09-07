<h1 align="center">DevMemory</h1>

<p align="center">
  <em>Development-memory and version-intelligence for AI-assisted software development.</em>
</p>

<p align="center">
  <strong>Git remembers <em>what</em> changed. Entire remembers the AI-assisted development <em>context</em>.
  DevMemory connects those changes with results, metrics, feature status and previous
  attempts — so developers and future AI agents can understand the complete development
  history, and avoid repeating past mistakes.</strong>
</p>

---

DevMemory turns each meaningful AI-assisted change into a **Development Version**: one
durable record that joins the Entire checkpoint (the prompt, agent, and session), the Git
commit (the exact diff), the results (tests, metrics, regressions), an analysis layer
(kept strictly separate from the facts), and cross-version analytics.

It is consumed two ways — a **visual dashboard** for humans, and an **MCP server + REST
context API** for the next AI agent.

DevMemory sits *beside* your existing tools. It is **not** an IDE, a version-control
system, or an experiment tracker. You keep using VS Code, Cursor, Claude Code, the
terminal, and CI exactly as before.

```text
        developer / AI intent
                 │
          AI coding agent            ← you keep your editor & agent
                 │
          Entire checkpoint          ← why / who / how  (github.com/entireio/cli)
                 │
            Git commit               ← what changed, exactly
                 │
       tests · metrics · results     ← the outcome
                 │
       Development Version  ← DevMemory: the join
                 │
     ┌───────────┴───────────┐
 dashboard                 MCP / API
 (a human understands)     (the next agent understands)
```

## Quickstart

```bash
pip install devmemory-cli

cd your-repo
devmemory init --name "My Project"
devmemory serve
```

Nothing else to configure: `init` creates `.devmemory/` in your repo, and the
dashboard reads that project and nothing else. There is no sample data — what you
see is your own history.

`init` backfills a lightweight Development Version for each of the last 100 commits,
so an existing project has a populated timeline from the start (`--no-backfill` to
skip it; `devmemory backfill --limit N --since <date>` to import more later).

Then, after each meaningful AI-assisted commit:

```bash
devmemory checkpoint --intent "what you were trying to do"
```

DevMemory finds the Entire checkpoint for the commit (or records without one),
runs your configured tests and metrics, detects regressions against the previous
version, checks whether this area has failed before, generates an analysis
(kept separate from the facts), and stores one **Development Version**.

```bash
devmemory history                 # the timeline
devmemory show v7                 # one version, end to end
devmemory compare 6 7             # what changed + metric/test deltas
devmemory memory --file auth.py   # "has this area failed before?"
devmemory analyze v7              # interpretation (rules, an on-device model, or a cloud LLM)
devmemory analytics               # regressions, feature attempts, file churn
devmemory serve                   # the dashboard + "Ask" chat (works with no API key)
devmemory model pull              # an on-device LLM for Ask + analyze (no key, offline)
devmemory mcp --print-config      # wire the MCP server into Claude Code / Cursor
devmemory doctor                  # check the setup
```

See [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md) for every setting. `devmemory
checkpoint` collects tests and metrics only once you point it at them — set
`tests.command` and `metrics.file` in `.devmemory/config.json`.

Credentials (LLM keys, Databricks) are read from the environment — `cp
.env.example .env` and fill in what you need; the CLI loads it automatically.

**The Ask chat and `analyze` need no key.** A built-in engine answers common
questions from your local data out of the box. For open-ended questions, run
`pip install "devmemory-cli[local-llm]"` then `devmemory model pull` — that fetches
a ~1 GB on-device model (Qwen2.5-Coder-1.5B) once and runs it locally, offline,
with nothing leaving the machine. A cloud key or a Databricks Genie space is used
instead when configured.

## What it is not

DevMemory sits *beside* your tools. It is not an IDE, a version-control system,
or an experiment tracker. It never sends source or transcripts anywhere unless
you configure it to, and an AI summary can never overwrite a Git, test, or metric
fact.

## Status

Built in vertical slices — see
[`CHANGELOG.md`](CHANGELOG.md) for what each phase added and
[`docs/IMPLEMENTATION_STRATEGY.md`](docs/IMPLEMENTATION_STRATEGY.md) for the
engineering audit and plan.

## Development

```bash
ruff check . && ruff format --check .
mypy
pytest -n auto
```

The dashboard is a Vite + React app in
[`src/devmemory/web/frontend/`](src/devmemory/web/frontend/); its built bundle is
committed to `src/devmemory/web/static/`, so `devmemory serve` never needs Node.
Rebuild it with `npm run build` in that directory (see its `README.md`).

## License

[MIT](LICENSE)
