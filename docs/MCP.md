# DevMemory MCP server

`devmemory mcp` runs a [Model Context Protocol](https://modelcontextprotocol.io)
server over stdio that exposes this project's development memory to an AI coding
agent. It is **read-only**: every tool returns collected facts (Git, Entire,
tests, metrics) or a rule-based risk read over them — never an LLM
interpretation.

The point: before an agent edits a file, it can ask *"has this area failed
here before?"* and get the specific prior versions to read first.

## Wiring it into a client

Print a ready-to-paste fragment for the current repo:

```bash
devmemory mcp --print-config
```

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "devmemory",
      "args": ["mcp", "--repo", "/abs/path/to/your/repo"]
    }
  }
}
```

- **Claude Code** — drop the fragment into `.mcp.json` at the repo root (or
  `claude mcp add`).
- **Cursor** — add it to `.cursor/mcp.json`.
- Any other MCP client — point it at `devmemory mcp` with a stdio transport.

The `mcp` extra must be installed: `pip install 'devmemory[mcp]'` (or
`devmemory[all]`).

## Tools

| Tool | Returns |
| --- | --- |
| `get_project_context` | Branch/HEAD, whether HEAD is checkpointed, version count and success rate, open features, the latest version, recent adverse versions, and cautions. |
| `get_version_history` | Recent development versions, newest first (`limit`, `feature`). |
| `get_version` | One version: the flattened brief, its intent→result trace, and its parent commit. |
| `get_development_trace` | The ordered chain for one version — intent → agent → checkpoint → commit → files → tests → metrics → status → analysis. |
| `get_previous_attempts` | Past versions touching the same files / feature / intent, ranked, each with why it matched and what to do. Adverse only unless `include_successes`. |
| `check_before_change` | **Pre-flight.** Given the files you're about to edit (+ optional intent / feature): a verdict `proceed` \| `caution` \| `high-risk` with the specific prior failures to read first. |
| `search_versions` | Full-text search over intents, features, and changed files. |
| `get_analytics` | Regression leaderboard, feature attempts, file churn, agent effectiveness, trend, repeatedly-failed approaches. |

## REST equivalent

The same three orientation calls are also plain HTTP on the dashboard server
(`devmemory serve`), for clients that aren't MCP-aware:

- `GET /api/agent/context`
- `GET /api/agent/history?limit=&feature=`
- `POST /api/agent/check` — body `{ "files": [...], "intent": "...", "feature": "..." }`
