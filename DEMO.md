# DevMemory — demo runbook

A five-minute walk-through. Everything is local; no accounts, no keys.

## 0. Setup (once)

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate     POSIX:  source .venv/bin/activate
pip install -e ".[dev]"

python examples/demo/seed.py /tmp/devmemory-demo
cd /tmp/devmemory-demo
```

The seed builds a small `pricing` package and records **six Development
Versions** across three features — Tax, Discounts, Rounding — including two
regressions and one repeated failed approach.

## 1. The history

```bash
devmemory history
```

Six versions, each joining intent → feature → Δ lines → metrics → status. V2 and
V3 are `REGRESSION`.

```bash
devmemory show v2          # the full record for one version
devmemory compare 1 2      # what changed, and the metric/test deltas
```

## 2. The memory — "has this failed before?"

V3 tried to paper over V2's regression by touching the same files. DevMemory
knows:

```bash
devmemory memory --file pricing/core.py
```

> **V2 [REGRESSION]** — quote_latency_ms 42 → 47 · *matched on: pricing/core.py*
> recommendation: this approach regressed here — avoid repeating it.

## 3. The analysis (facts vs. interpretation)

```bash
devmemory analyze v3
```

The **facts** (Git, metrics, tests) are never touched. The `rules` provider adds
*interpretation* — risk `high`, a summary, a recommendation — and cites V2 as the
prior failure. Set `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` and
add the provider to `analysis.providers` in `.devmemory/config.json` to use an
LLM instead; `rules` stays the guaranteed fallback.

## 4. Cross-version intelligence

```bash
devmemory analytics
```

Regression leaderboard, feature attempt/success rates, file churn, and the
**repeatedly-failed approach** (V2 + V3, same file signature). With
`DATABRICKS_HOST` / `DATABRICKS_TOKEN` / `DATABRICKS_WAREHOUSE_ID` set and
`databricks.enabled = true`, `devmemory databricks push` publishes the same
normalized rows to Delta tables — never source, never transcripts.

## 5. The dashboard

```bash
devmemory serve
```

- **Overview / Timeline** — the six versions
- **Version → V2** — the development trace, the diff, and the ⚠ previous-attempts
  panel
- **Features → Discounts** — 4 attempts, 50% success, 2 regressions
- **Intelligence** — the analytics above, with a trend sparkline
- **Memory** — search previous attempts by file / intent

## 6. For the next AI agent

```bash
devmemory mcp --print-config      # an .mcp.json fragment for Claude Code / Cursor
```

Wire it in, then the agent can call `check_before_change` **before** editing:

```text
check_before_change(files=["pricing/core.py"], intent="change the discount logic")
→ verdict: high-risk
  "2 earlier attempts in this exact area failed — and more than once."
  read V2, V3 first.
```

Same three calls are plain HTTP on the running dashboard: `GET /api/agent/context`,
`GET /api/agent/history`, `POST /api/agent/check`.

## 7. Optional: change-impact

```bash
entire plugin install graph        # one-time
devmemory impact v2
```

> `signature_changed apply_discount` (pricing/core.py, **2 dependents**) — review
> before keeping.

## 8. Health check

```bash
devmemory doctor
```
