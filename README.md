# DevMemory ⚡

**Development-Memory & Version-Intelligence Platform for AI-Assisted Software Engineering**

> *Git remembers what changed. Entire remembers the AI-assisted development context. DevMemory connects those changes with test results, metric baselines, feature status, and previous attempts so that developers and future AI agents never repeat past mistakes.*

---

## 🌟 Overview

As software development shifts to AI coding agents (Claude Code, Cursor, Codex, Antigravity), codebases evolve through rapid, iterative prompts. Standard version control systems (like Git) track code diffs, but fail to record:
- **Why** the change was made (developer intent / prompt)
- **Which AI agent** generated the code
- **What test results & metrics** resulted from the change (e.g., accuracy 89.2% -> 72.1%)
- **Whether the step caused a regression**
- **Lessons learned from failed attempts** to guide future prompt turns

**DevMemory** bridges **Entire Checkpoints**, **Git**, **Databricks Analytics**, and **AI Coding Agents** into a single, cohesive development memory layer.

---

## 🏗️ Architecture & How It Works

```
┌───────────────────────────┐      ┌───────────────────────────┐
│       Entire CLI          │      │         Git Repo          │
│ (Checkpoints & Transcripts)│      │   (Commits, Diffs, Stats) │
└─────────────┬─────────────┘      └─────────────┬─────────────┘
              │ Entire-Checkpoint: <id>          │
              └──────────────┬───────────────────┘
                             ▼
               ┌───────────────────────────┐
               │    DevMemory Engine       │
               │ (Regression Detection,    │
               │  Feature Health, FTS)     │
               └─────────────┬─────────────┘
                             │
     ┌───────────────────────┼───────────────────────┐
     ▼                       ▼                       ▼
┌───────────────┐   ┌─────────────────┐   ┌────────────────────┐
│ Web Dashboard │   │  MCP AI Server  │   │ Databricks Analytics│
│  (Port 8765)  │   │  (Claude/Cursor)│   │   (Delta Tables)   │
└───────────────┘   └─────────────────┘   └────────────────────┘
```

1. **Entire Checkpoint Linking**: Every Git commit generated during AI sessions includes an `Entire-Checkpoint: <ulid>` trailer. DevMemory inspects this trailer to automatically fetch full transcript context, developer prompts, and AI model names.
2. **Regression Detection**: Compares incoming metrics (e.g. accuracy, latency, test pass rates) against prior baselines. Automatically flags regressions (>5% degradation or increased test failures).
3. **Development Memory**: Indexes all past iterations with SQLite FTS5. Before an AI agent attempts a new task, DevMemory provides targeted warnings about previous failed attempts.
4. **Databricks Delta Lake Sync**: Streams version records to Databricks for cross-project agent effectiveness evaluation and regression pattern discovery.

---

## 🚀 Quick Start

### 1. Installation

```bash
# Clone or navigate to your project
cd /path/to/your/project

# Install DevMemory package
pip install -e .

# Or install optional extras for Databricks and MCP
pip install -e ".[all]"
```

### 2. Initialize Tracking

```bash
devmemory init --name "VisionAI" --project-id "visionai"
```

### 3. Run Pre-Seeded Demo Data (Hackathon Showcase)

Populate realistic development history (VisionAI model iterations, regressions, dynamic TensorRT exports, and API auth errors):

```bash
devmemory seed-demo
```

### 4. Explore via CLI

```bash
# View current status & baseline metrics
devmemory status

# View chronological history
devmemory history

# Compare version 2 and regression version 3
devmemory diff 2 3

# Check AI context & regression warnings
devmemory context --feature "image-classification"

# Full-text search across past attempts
devmemory search "learning rate"

# List tracked features
devmemory features
```

### 5. Launch Interactive Web Dashboard

```bash
devmemory serve
# Open http://127.0.0.1:8765 in your browser
```

---

## 💻 CLI Command Reference

| Command | Description |
|:--------|:------------|
| `devmemory init` | Initialize DevMemory tracking in current directory |
| `devmemory checkpoint` | Record a new version connecting Entire Checkpoint, Git HEAD, and metrics |
| `devmemory status` | View current version, completion %, and active baseline metrics |
| `devmemory history` | List version log with status badges and metrics chips |
| `devmemory diff <A> <B>` | Compare two versions: line diffs, metric deltas (+/- %), test pass/fail deltas |
| `devmemory restore <ID>` | Safely checkout target version code to a `devmemory/restore-v<ID>` recovery branch |
| `devmemory search <q>` | Full-text search across intents, agents, features, and analysis |
| `devmemory context` | Output markdown prompt snippet formatted for AI agent prompt injection |
| `devmemory features` | View feature health, version count, and evolution timeline |
| `devmemory serve` | Launch the FastAPI + Single Page Web Dashboard |
| `devmemory mcp` | Start Model Context Protocol (MCP) server for Claude Code / Cursor |
| `devmemory seed-demo` | Populate sample 8-iteration VisionAI project data |

---

## 📊 Databricks Analytics Integration

DevMemory streams development metadata to Databricks Delta Lake tables:
- `devmemory_analytics.development_intelligence.development_versions`
- `devmemory_analytics.development_intelligence.development_events`

### Databricks SQL Queries

**Agent Effectiveness Comparison**:
```sql
SELECT 
    agent, 
    COUNT(*) as total_versions,
    SUM(CASE WHEN is_regression THEN 1 ELSE 0 END) as regression_count,
    ROUND((SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) * 100.0 / COUNT(*)), 1) as success_rate_pct
FROM devmemory_analytics.development_intelligence.development_versions
WHERE agent IS NOT NULL
GROUP BY agent
ORDER BY success_rate_pct DESC;
```

**Files Most Frequently Involved in Regressions**:
```sql
SELECT 
    explode(changed_files) as file_path, 
    COUNT(*) as failure_count
FROM devmemory_analytics.development_intelligence.development_versions
WHERE is_regression = TRUE OR status IN ('ERROR', 'REGRESSION')
GROUP BY file_path
ORDER BY failure_count DESC
LIMIT 10;
```

---

## 🤖 Model Context Protocol (MCP) Integration

DevMemory acts as an MCP Server for AI Coding Agents.

Add DevMemory to your `claude_desktop_config.json` or Cursor MCP settings:

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "devmemory",
      "args": ["mcp"]
    }
  }
}
```

### Exposed MCP Tools:
- `get_project_status()`: Baseline metrics, current version, test health.
- `get_version_history(limit)`: Chronological iterations.
- `get_previous_attempts(feature, intent)`: Warnings about past failed approaches.
- `get_version_diff(version_a, version_b)`: Code diffs & metric changes.
- `get_feature_status()`: Feature health & evolution.
- `get_project_context(feature, intent)`: Markdown prompt snippet for AI agents.

---

## 🎨 Web Dashboard Preview

The web dashboard is built using vanilla HTML/CSS/JS with zero heavy framework overhead, featuring a dark glassmorphic design system:
- **Overview**: Active baseline metrics, recent iterations, test health stats.
- **Timeline**: Interactive timeline with status badges and Entire Checkpoint links.
- **Version Detail**: Full session intent, heuristic analysis, actionable advice, tests breakdown, and colorized Git diff viewer.
- **Compare**: Side-by-side metric deltas with green/red indicator pills and full code diffs.
- **Features**: Evolution timeline per feature area.
- **AI Memory**: Warning callouts for regressions and prompt injection snippet generator.
- **Databricks**: Agent performance comparison table and Delta Lake schema browser.

---

## 🛠️ Project Structure

```
.
├── pyproject.toml               # Package configuration
├── setup.py                     # Setuptools compatibility shim
├── README.md                    # Project documentation
└── devmemory/
    ├── __init__.py              # Package API & DevMemoryProject class
    ├── cli.py                   # Click CLI implementation
    ├── config.py                # Configuration management (.devmemory/config.json)
    ├── database.py              # SQLite storage & FTS5 search layer
    ├── models.py                # Pydantic data models
    ├── mcp_server.py            # FastMCP & stdio JSON-RPC 2.0 server
    ├── seed_demo.py             # Realistic 8-iteration demo seeder
    ├── adapters/
    │   ├── entire.py            # Entire CLI wrapper & transcript parser
    │   ├── git_adapter.py       # GitPython integration
    │   └── databricks.py        # Databricks SQL connector & Delta Lake sync
    ├── intelligence/
    │   ├── analyzer.py          # Status inference & regression detection
    │   └── memory.py            # Previous attempt matching & AI context generator
    └── web/
        ├── app.py               # FastAPI application factory
        ├── api.py               # REST API endpoints
        └── static/
            ├── index.html       # SPA Dashboard HTML
            ├── style.css        # Glassmorphic dark styling
            └── app.js           # Interactive frontend logic
```

---

## 📜 License

MIT License. Designed for the Entire Open Source Challenge Hackathon.
