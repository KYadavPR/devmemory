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

## Status

Early development. The repository is being built in vertical slices — see
[`docs/IMPLEMENTATION_STRATEGY.md`](docs/IMPLEMENTATION_STRATEGY.md) for the full plan and
[`docs/`](docs/) for the product and data specifications.

**Phase 0 (current):** package foundation — configuration, structured logging, the error
taxonomy, the SQLite migration runner, and CI.

## Development

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate    POSIX:  source .venv/bin/activate
pip install -e ".[dev]"

ruff check . && ruff format --check .
mypy
pytest
```

## License

[MIT](LICENSE)
