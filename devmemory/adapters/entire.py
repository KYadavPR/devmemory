"""Entire CLI adapter for DevMemory.

Wraps the Entire CLI (Go binary) to inspect checkpoints, transcripts,
developer intents, agents, and graph impact.
"""

import json
import os
import shutil
import subprocess
from typing import Optional, List, Dict, Any


class EntireAdapter:
    """Wraps the Entire CLI to extract checkpoint data and session context."""

    def __init__(self, repo_path: str):
        self.repo_path = os.path.abspath(repo_path)
        self._entire_bin = shutil.which("entire") or "entire"

    def is_available(self) -> bool:
        """Check if Entire CLI is installed and responsive."""
        try:
            result = subprocess.run(
                [self._entire_bin, "status", "--json"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.SubprocessError, PermissionError):
            return False

    def get_version(self) -> Optional[str]:
        """Get Entire CLI version string if installed."""
        try:
            result = subprocess.run(
                [self._entire_bin, "version"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_checkpoint_id_from_commit(self, commit_message: str) -> Optional[str]:
        """Extract Entire-Checkpoint trailer from a git commit message."""
        if not commit_message:
            return None
        for line in commit_message.strip().split("\n"):
            line = line.strip()
            if line.lower().startswith("entire-checkpoint:"):
                parts = line.split(":", 1)
                if len(parts) > 1:
                    val = parts[1].strip()
                    if val:
                        return val
        return None

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List all checkpoints via `entire checkpoint list --json`."""
        try:
            result = subprocess.run(
                [self._entire_bin, "checkpoint", "list", "--json"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception:
            pass
        return []

    def explain_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Get full checkpoint context via `entire checkpoint explain <id> --json`."""
        if not checkpoint_id:
            return None
        try:
            result = subprocess.run(
                [self._entire_bin, "checkpoint", "explain", checkpoint_id, "--json"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception:
            pass
        return None

    def extract_intent(self, checkpoint_data: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract the developer's intent from checkpoint transcript or summary.

        The intent is typically the first user prompt in the session transcript.
        """
        if not checkpoint_data:
            return None

        # Check transcript user messages
        transcript = checkpoint_data.get("transcript") or []
        if isinstance(transcript, list):
            for turn in transcript:
                if isinstance(turn, dict) and turn.get("role") in ("user", "human"):
                    content = turn.get("content") or turn.get("text") or ""
                    if content:
                        return str(content).strip()[:500]

        # Check prompts field
        prompts = checkpoint_data.get("prompts") or []
        if isinstance(prompts, list) and prompts:
            first = prompts[0]
            if isinstance(first, dict):
                return (first.get("content") or first.get("prompt") or "")[:500]
            elif isinstance(first, str):
                return first[:500]

        # Fallback to summary or title
        for key in ("summary", "intent", "title", "description"):
            val = checkpoint_data.get(key)
            if val and isinstance(val, str):
                return val.strip()[:500]

        return None

    def extract_agent(self, checkpoint_data: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract which AI agent created this checkpoint."""
        if not checkpoint_data:
            return None
        for key in ("agent", "agent_name", "model", "assistant", "author"):
            val = checkpoint_data.get(key)
            if val and isinstance(val, str):
                return val.strip()
        metadata = checkpoint_data.get("metadata")
        if isinstance(metadata, dict):
            for key in ("agent", "agent_name", "model"):
                val = metadata.get(key)
                if val and isinstance(val, str):
                    return val.strip()
        return None

    def search_checkpoints(self, query: str) -> List[Dict[str, Any]]:
        """Search checkpoints via `entire checkpoint search <query> --json`."""
        if not query:
            return []
        try:
            result = subprocess.run(
                [self._entire_bin, "checkpoint", "search", query, "--json"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception:
            pass
        return []

    def get_impact_analysis(self, changed_files: List[str]) -> Optional[Dict[str, Any]]:
        """Use Entire Graph plugin to find affected modules if available."""
        if not changed_files:
            return None
        try:
            cmd = [self._entire_bin, "graph", "impact", "--files"] + list(changed_files) + ["--json"]
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0 and result.stdout.strip():
                return json.loads(result.stdout)
        except Exception:
            pass
        return None
