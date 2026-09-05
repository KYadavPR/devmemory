"""Click CLI for DevMemory."""

import json
import os
import sys
import click

if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from devmemory import init as dm_init, DevMemoryProject
from devmemory.config import DevMemoryConfig


def _get_project(ctx) -> DevMemoryProject:
    """Helper to load DevMemoryProject from current directory."""
    project_path = os.getcwd()
    try:
        return DevMemoryProject(project_path)
    except Exception as e:
        click.secho(f"Error loading DevMemory project: {e}", fg="red")
        sys.exit(1)


@click.group()
@click.version_option(version="0.1.0", prog_name="devmemory")
def cli():
    """DevMemory — Development-Memory & Version-Intelligence Platform for AI-Assisted Software."""
    pass


@cli.command()
@click.option("--name", default="", help="Human-readable project name")
@click.option("--project-id", default="", help="Unique project identifier")
def init(name: str, project_id: str):
    """Initialize DevMemory tracking in the current project directory."""
    cwd = os.getcwd()
    proj = dm_init(cwd, name=name, project_id=project_id)
    click.secho(" DevMemory initialized successfully!", fg="green", bold=True)
    click.echo(f"   Project: {proj.config.project_name} ({proj.config.project_id})")
    click.echo(f"   Path:    {proj.project_path}")
    click.echo(f"   Storage: {proj.config.db_path}")
    click.echo("\nNext steps:")
    click.echo("   1. Work with your AI agent or commit your code.")
    click.echo("   2. Run `devmemory checkpoint --feature <name> --metrics acc=0.9`")
    click.echo("   3. Launch `devmemory serve` to view the web dashboard.")


@cli.command()
@click.option("--intent", default=None, help="Developer intent / AI prompt (auto-extracted from Entire if omitted)")
@click.option("--feature", default=None, help="Feature name (e.g., auth, classification, pipeline)")
@click.option("--status", default=None, help="Status override (SUCCESS, ERROR, REGRESSION, PARTIAL_SUCCESS)")
@click.option("--tests-passed", type=int, default=None, help="Count of passing tests")
@click.option("--tests-failed", type=int, default=None, help="Count of failing tests")
@click.option("--metrics", "-m", multiple=True, help="Key-value metrics, e.g. -m accuracy=92.5 -m latency=120")
@click.option("--errors", "-e", multiple=True, help="Error messages encountered")
@click.option("--agent", default=None, help="AI agent name (e.g. claude-code, codex)")
@click.option("--no-snapshot", is_flag=True, help="Skip creating artifact tar.gz snapshot")
def checkpoint(intent, feature, status, tests_passed, tests_failed, metrics, errors, agent, no_snapshot):
    """Record a development version combining Entire Checkpoint, Git changes, and test metrics."""
    proj = _get_project(None)

    # Parse metrics list into dictionary
    metrics_dict = {}
    for m in metrics:
        if "=" in m:
            k, v = m.split("=", 1)
            try:
                metrics_dict[k.strip()] = float(v.strip()) if "." in v else int(v.strip())
            except ValueError:
                metrics_dict[k.strip()] = v.strip()

    errors_list = list(errors) if errors else []

    record = proj.checkpoint(
        intent=intent,
        feature=feature,
        status=status,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        metrics=metrics_dict,
        errors=errors_list,
        agent=agent,
        create_snapshot=not no_snapshot,
    )

    vid = record["version_id"]
    rec_status = record["status"]
    is_reg = record.get("is_regression", False)

    status_color = "green"
    if is_reg or rec_status == "REGRESSION":
        status_color = "red"
    elif rec_status == "ERROR":
        status_color = "red"
    elif rec_status == "PARTIAL_SUCCESS":
        status_color = "yellow"

    click.secho(f"\n Development Version Recorded: v{vid} [{rec_status}]", fg=status_color, bold=True)
    click.echo(f"   Commit:     {record['git_commit'][:8]} (branch: {record.get('branch')})")
    if record.get("checkpoint_id"):
        click.echo(f"   Entire CP:  {record['checkpoint_id']}")
    click.echo(f"   Intent:     {record.get('intent')}")
    click.echo(f"   Agent:      {record.get('agent')}")
    if record.get("feature"):
        click.echo(f"   Feature:    {record.get('feature')}")
    click.echo(f"   Changes:    +{record.get('additions', 0)} / -{record.get('deletions', 0)} in {len(record.get('changed_files', []))} files")

    if metrics_dict:
        m_str = " ".join([f"{k}={v}" for k, v in metrics_dict.items()])
        click.echo(f"   Metrics:    {m_str}")

    if tests_passed is not None or tests_failed is not None:
        click.echo(f"   Tests:      {tests_passed or 0} passed, {tests_failed or 0} failed")

    if record.get("analysis"):
        click.echo(f"   Analysis:   {record['analysis']}")
    if record.get("recommendation"):
        click.secho(f"   Advice:     {record['recommendation']}", fg="cyan")


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as raw JSON")
def status(as_json: bool):
    """Show current project status, versions, and baseline metrics."""
    proj = _get_project(None)
    st = proj.status()

    if as_json:
        click.echo(json.dumps(st, indent=2))
        return

    click.secho(f"\n Project Status: {st.get('project_name', 'DevMemory')}", fg="cyan", bold=True)
    click.echo(f"   Current Version: v{st.get('current_version', 0)}")
    click.echo(f"   Total Versions:  {st.get('total_versions', 0)}")
    click.echo(f"   Latest Status:   {st.get('latest_status') or 'N/A'}")

    metrics = st.get("latest_metrics", {})
    if metrics:
        click.echo("   Active Metrics:")
        for k, v in metrics.items():
            click.echo(f"     - {k}: {v}")

    features = st.get("features", [])
    if features:
        click.echo("   Tracked Features:")
        for f in features:
            status_fg = "green" if f["status"] == "COMPLETE" else "yellow" if f["status"] == "IN_PROGRESS" else "red"
            click.echo(f"     - {f['name']}: ", nl=False)
            click.secho(f["status"], fg=status_fg)


@cli.command()
@click.option("--limit", type=int, default=20, help="Number of records to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def history(limit: int, as_json: bool):
    """Show chronological development version history."""
    proj = _get_project(None)
    hist = proj.history(limit=limit)

    if as_json:
        click.echo(json.dumps(hist, indent=2))
        return

    if not hist:
        click.echo("No development versions recorded yet.")
        return

    click.secho(f"\n Development History ({len(hist)} versions):\n", bold=True)
    header = f"{'VERSION':<8} {'STATUS':<16} {'AGENT':<16} {'FEATURE':<18} {'METRICS':<24} {'INTENT'}"
    click.secho(header, fg="cyan", underline=True)

    for h in hist:
        vid = f"v{h['version_id']}"
        st = h["status"]
        agent = (h["agent"] or "")[:15]
        feat = (h["feature"] or "-")[:17]
        m_str = " ".join([f"{k}:{v}" for k, v in (h.get("metrics") or {}).items()])[:23]
        intent = (h.get("intent") or "")[:40]

        color = "green" if st == "SUCCESS" else "red" if (st == "REGRESSION" or h.get("is_regression")) else "yellow"
        row = f"{vid:<8} {st:<16} {agent:<16} {feat:<18} {m_str:<24} {intent}"
        click.secho(row, fg=color)


@cli.command()
@click.argument("version_a", type=int)
@click.argument("version_b", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output comparison as JSON")
def diff(version_a: int, version_b: int, as_json: bool):
    """Compare two development versions (code diff, metric deltas, tests)."""
    proj = _get_project(None)
    res = proj.diff(version_a, version_b)

    if as_json:
        click.echo(json.dumps(res, indent=2))
        return

    if "error" in res:
        click.secho(res["error"], fg="red")
        return

    click.secho(f"\n Comparing Version v{version_a}  v{version_b}", fg="cyan", bold=True)
    click.echo(f"   Files changed: {len(res.get('files', []))} (+{res.get('additions', 0)} / -{res.get('deletions', 0)})")

    mc = res.get("metric_changes", {})
    if mc:
        click.echo("\n   Metric Deltas:")
        for k, info in mc.items():
            dir_str = info.get("direction", "")
            color = "green" if dir_str == "improved" else "red" if dir_str == "regressed" else "white"
            chg = info.get("change")
            click.echo(f"     - {k}: {info['before']} -> {info['after']} (delta: ", nl=False)
            click.secho(f"{chg:+} [{dir_str}]", fg=color)

    tc = res.get("test_changes", {})
    if tc:
        click.echo(f"   Test Deltas: passed {tc.get('passed', 0):+}, failed {tc.get('failed', 0):+}")

    diff_text = res.get("diff_text", "")
    if diff_text:
        click.echo("\n--- Git Diff ---")
        for line in diff_text.split("\n")[:40]:
            if line.startswith("+"):
                click.secho(line, fg="green")
            elif line.startswith("-"):
                click.secho(line, fg="red")
            elif line.startswith("@@"):
                click.secho(line, fg="cyan")
            else:
                click.echo(line)
        if len(diff_text.split("\n")) > 40:
            click.echo(f"... [diff truncated, total lines: {len(diff_text.splitlines())}]")


@cli.command()
@click.argument("version_id", type=int)
def restore(version_id: int):
    """Restore project code to a previous development version safely."""
    proj = _get_project(None)
    res = proj.restore(version_id)
    if "error" in res:
        click.secho(res["error"], fg="red")
    else:
        click.secho(f" {res['message']}", fg="green", bold=True)
        click.echo(f"   Branch created: {res['branch']}")
        click.echo(f"   Target commit:  {res['commit']}")


@cli.command()
@click.argument("query")
@click.option("--json", "as_json", is_flag=True, help="Output as raw JSON")
def search(query: str, as_json: bool):
    """Search development memory across intents, agents, features, and analysis."""
    proj = _get_project(None)
    results = proj.search(query)

    if as_json:
        click.echo(json.dumps(results, indent=2))
        return

    click.secho(f"\n Search Results for '{query}' ({len(results)} matches):\n", bold=True)
    for r in results:
        vid = f"v{r['version_id']}"
        st = r["status"]
        color = "green" if st == "SUCCESS" else "red" if st == "REGRESSION" else "yellow"
        click.secho(f"[{vid}] {st} - Feature: {r.get('feature') or 'N/A'}", fg=color, bold=True)
        click.echo(f"  Intent:  {r.get('intent')}")
        click.echo(f"  Agent:   {r.get('agent')}")
        if r.get("analysis"):
            click.echo(f"  Analysis: {r.get('analysis')}")
        click.echo()


@cli.command()
@click.option("--feature", default="", help="Filter warnings by feature")
@click.option("--intent", default="", help="Filter warnings by intent query")
@click.option("--json", "as_json", is_flag=True, help="Output as raw JSON")
def context(feature: str, intent: str, as_json: bool):
    """Output development memory & AI agent context to prevent known regressions."""
    proj = _get_project(None)
    ctx_data = proj.context(feature=feature, intent=intent)

    if as_json:
        click.echo(json.dumps(ctx_data, indent=2))
        return

    click.echo(ctx_data["prompt_snippet"])


@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Output as raw JSON")
def features(as_json: bool):
    """List all tracked features and their evolution."""
    proj = _get_project(None)
    feats = proj.features()

    if as_json:
        click.echo(json.dumps(feats, indent=2))
        return

    click.secho("\n Tracked Features:\n", bold=True)
    for f in feats:
        color = "green" if f["status"] == "COMPLETE" else "yellow" if f["status"] == "IN_PROGRESS" else "red"
        click.secho(f"• {f['name']} [{f['status']}]", fg=color, bold=True)
        click.echo(f"   Versions touched: {f['version_count']}")
        if f.get("latest_metrics"):
            click.echo(f"   Metrics: {f['latest_metrics']}")


@cli.command()
@click.option("--host", default=None, help="Host to bind server to")
@click.option("--port", type=int, default=None, help="Port to bind server to")
def serve(host: str, port: int):
    """Launch the interactive DevMemory web dashboard."""
    import socket
    import uvicorn
    from devmemory.web.app import create_app

    proj = _get_project(None)
    server_host = host or proj.config.web_host
    desired_port = port or proj.config.web_port

    server_port = desired_port
    for p in range(desired_port, desired_port + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((server_host, p))
                server_port = p
                break
            except OSError:
                continue

    app = create_app(proj.project_path)
    click.secho(f"\n DevMemory Web Dashboard running at: http://{server_host}:{server_port}", fg="green", bold=True)
    uvicorn.run(app, host=server_host, port=server_port, log_level="info")


@cli.command()
def mcp():
    """Start the DevMemory Model Context Protocol (MCP) server for AI coding agents."""
    from devmemory.mcp_server import run_mcp_server
    run_mcp_server(os.getcwd())


@cli.command("seed-demo")
def seed_demo():
    """Seed realistic development memory demo data (VisionAI with 8 iterations and regressions)."""
    from devmemory.seed_demo import seed_demo_data
    seed_demo_data(os.getcwd())
    click.secho(" Demo data populated successfully! Run `devmemory serve` to explore.", fg="green", bold=True)


if __name__ == "__main__":
    cli()
