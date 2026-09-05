"""DevMemory Model Context Protocol (MCP) Server.

Exposes project status, version history, previous attempt warnings, and diffs as MCP tools
for AI coding agents (Claude Code, Cursor, Antigravity, etc.).
Supports FastMCP if `mcp` is installed, with an integrated stdio JSON-RPC 2.0 server fallback.
"""

import sys
import json
import os
from typing import Dict, Any, List

from devmemory import DevMemoryProject


def get_project(project_path: str = ".") -> DevMemoryProject:
    return DevMemoryProject(project_path)


def run_mcp_server(project_path: str = "."):
    """Launch the MCP server for the given project path."""
    project_path = os.path.abspath(project_path)

    # Attempt FastMCP first
    try:
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("DevMemory", dependencies=["devmemory"])
        proj = get_project(project_path)

        @mcp.tool()
        def get_project_status() -> Dict[str, Any]:
            """Get current project status, active version, test health, and baseline metrics."""
            return proj.status()

        @mcp.tool()
        def get_version_history(limit: int = 10) -> List[Dict[str, Any]]:
            """Get recent development version iterations with status, intent, and metrics."""
            return proj.history(limit=limit)

        @mcp.tool()
        def get_previous_attempts(feature: str = "", intent: str = "") -> Dict[str, Any]:
            """Check project memory for prior failed attempts or regressions before implementing changes."""
            return proj.context(feature=feature, intent=intent)

        @mcp.tool()
        def get_version_diff(version_a: int, version_b: int) -> Dict[str, Any]:
            """Compare two development versions (metrics delta, test changes, git diff)."""
            return proj.diff(version_a, version_b)

        @mcp.tool()
        def get_feature_status() -> List[Dict[str, Any]]:
            """Get status, metrics, and evolution history for all tracked features."""
            return proj.features()

        @mcp.tool()
        def get_project_context(feature: str = "", intent: str = "") -> str:
            """Get complete markdown prompt snippet formatted for AI agent decision-making."""
            ctx = proj.context(feature=feature, intent=intent)
            return ctx.get("prompt_snippet", "")

        mcp.run()
        return
    except ImportError:
        pass

    # Fallback to standard stdio JSON-RPC 2.0 MCP protocol
    _run_stdio_jsonrpc_mcp(project_path)


def _run_stdio_jsonrpc_mcp(project_path: str):
    """Integrated stdio JSON-RPC 2.0 server supporting core MCP tools."""
    proj = get_project(project_path)

    TOOLS = [
        {
            "name": "get_project_status",
            "description": "Get current project status, active version, test health, and baseline metrics.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_version_history",
            "description": "Get recent development version iterations with status, intent, and metrics.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max versions to return", "default": 10}
                },
            },
        },
        {
            "name": "get_previous_attempts",
            "description": "Check development memory for past regressions or mistakes before modifying code.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "feature": {"type": "string", "description": "Feature name to inspect"},
                    "intent": {"type": "string", "description": "Proposed intent or description"},
                },
            },
        },
        {
            "name": "get_version_diff",
            "description": "Compare two development versions across code, tests, and metric changes.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "version_a": {"type": "integer", "description": "Base version ID"},
                    "version_b": {"type": "integer", "description": "Target version ID"},
                },
                "required": ["version_a", "version_b"],
            },
        },
        {
            "name": "get_feature_status",
            "description": "Get status, metrics, and evolution history for all tracked features.",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "get_project_context",
            "description": "Get formatted markdown prompt snippet for AI coding agent decision making.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "feature": {"type": "string", "description": "Active feature name"},
                    "intent": {"type": "string", "description": "Proposed intent"},
                },
            },
        },
    ]

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "devmemory-mcp", "version": "0.1.0"},
                },
            }
        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": TOOLS},
            }
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            try:
                if tool_name == "get_project_status":
                    res = proj.status()
                elif tool_name == "get_version_history":
                    limit = int(arguments.get("limit", 10))
                    res = proj.history(limit=limit)
                elif tool_name == "get_previous_attempts":
                    res = proj.context(
                        feature=arguments.get("feature", ""),
                        intent=arguments.get("intent", ""),
                    )
                elif tool_name == "get_version_diff":
                    res = proj.diff(
                        version_a=int(arguments["version_a"]),
                        version_b=int(arguments["version_b"]),
                    )
                elif tool_name == "get_feature_status":
                    res = proj.features()
                elif tool_name == "get_project_context":
                    ctx = proj.context(
                        feature=arguments.get("feature", ""),
                        intent=arguments.get("intent", ""),
                    )
                    res = ctx.get("prompt_snippet", "")
                else:
                    res = {"error": f"Unknown tool '{tool_name}'"}

                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res, indent=2) if isinstance(res, (dict, list)) else str(res)}]
                    },
                }
            except Exception as e:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32000, "message": str(e)},
                }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Method '{method}' not found"},
            }

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    run_mcp_server(os.getcwd())
