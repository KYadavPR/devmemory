"""
DevMemory — Development-memory and version-intelligence for AI-assisted software development.

Git remembers what changed.
Entire remembers the AI-assisted development context.
DevMemory connects those changes with results, metrics, feature status, project state,
and previous attempts so that developers and future AI agents can understand the
complete development history.
"""

__version__ = "0.1.0"

import os
import tarfile
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

from devmemory.config import DevMemoryConfig
from devmemory.database import DevMemoryDB
from devmemory.models import (
    DevelopmentVersion,
    Feature,
    ProjectState,
    VersionStatus,
    FeatureStatus,
)
from devmemory.adapters.entire import EntireAdapter
from devmemory.adapters.git_adapter import GitAdapter
from devmemory.adapters.databricks import DatabricksAdapter
from devmemory.intelligence.analyzer import (
    detect_regression,
    infer_status,
    generate_analysis_and_recommendation,
)
from devmemory.intelligence.memory import (
    find_similar_attempts,
    format_agent_context,
)


class DevMemoryProject:
    """Main entry point for the DevMemory Python API."""

    def __init__(self, project_path: str = "."):
        self.project_path = os.path.abspath(project_path)
        self.config = DevMemoryConfig.load(self.project_path)
        self.db = DevMemoryDB(self.project_path)
        self.git = GitAdapter(self.project_path)
        self.entire = EntireAdapter(self.project_path)
        self.databricks = DatabricksAdapter(self.config)

    def status(self) -> Dict[str, Any]:
        """Get current project status and latest baseline metrics."""
        project = self.db.get_project()
        if not project:
            return {"error": "Project not initialized. Run `devmemory init` first."}

        versions = self.db.get_all_versions()
        features = self.db.get_all_features()
        latest = versions[-1] if versions else None

        return {
            "project_id": project["project_id"],
            "project_name": project["project_name"],
            "current_version": project["current_version"],
            "total_versions": len(versions),
            "latest_status": latest["status"] if latest else None,
            "latest_metrics": _parse_json(latest["metrics"]) if latest else {},
            "features": [
                {"name": f["name"], "status": f["status"], "latest_metrics": _parse_json(f.get("latest_metrics"))}
                for f in features
            ],
            "total_tests_passed": latest["tests_passed"] if latest else None,
            "total_tests_failed": latest["tests_failed"] if latest else None,
            "is_databricks_configured": self.databricks.is_configured,
            "is_entire_available": self.entire.is_available(),
        }

    def checkpoint(
        self,
        intent: Optional[str] = None,
        feature: Optional[str] = None,
        status: Optional[str] = None,
        tests_passed: Optional[int] = None,
        tests_failed: Optional[int] = None,
        metrics: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
        agent: Optional[str] = None,
        create_snapshot: bool = True,
    ) -> Dict[str, Any]:
        """Record a new development version by connecting Entire Checkpoint, Git changes, and test metrics."""
        project = self.db.get_project()
        if not project:
            # Auto initialize if not done yet
            self.db.initialize()
            self.db.create_project(self.config.project_id, self.config.project_name, self.project_path)
            project = self.db.get_project()

        # 1. Inspect Git HEAD
        head_commit = self.git.get_head_commit()
        if head_commit:
            commit_sha = head_commit["sha"]
            parent_sha = head_commit["parent"]
            commit_msg = head_commit["message"]
            branch = self.git.get_branch()
        else:
            commit_sha = "0000000000000000000000000000000000000000"
            parent_sha = None
            commit_msg = "Initial uncommitted / manual checkpoint"
            branch = "main"

        # 2. Inspect Entire Context
        checkpoint_id = self.entire.get_checkpoint_id_from_commit(commit_msg)
        session_id = None
        checkpoint_data = None

        if checkpoint_id:
            checkpoint_data = self.entire.explain_checkpoint(checkpoint_id)
        elif self.entire.is_available():
            # If no trailer in commit, check latest checkpoint from Entire CLI
            recent_checkpoints = self.entire.list_checkpoints()
            if recent_checkpoints:
                latest_cp = recent_checkpoints[0]
                checkpoint_id = latest_cp.get("id") or latest_cp.get("checkpoint_id")
                if checkpoint_id:
                    checkpoint_data = self.entire.explain_checkpoint(checkpoint_id)

        if checkpoint_data:
            session_id = checkpoint_data.get("session_id")
            if not intent:
                intent = self.entire.extract_intent(checkpoint_data)
            if not agent:
                agent = self.entire.extract_agent(checkpoint_data)

        # Fallback values for intent and agent if not specified
        if not intent:
            intent = commit_msg.split("\n")[0] if commit_msg else "Development update"
        if not agent:
            agent = "human-developer"

        # 3. Compute Git Diff Stats
        diff_stats = self.git.get_diff_stats(parent_sha, commit_sha)
        changed_files = diff_stats.get("files", [])
        additions = diff_stats.get("additions", 0)
        deletions = diff_stats.get("deletions", 0)

        # 4. Compare with previous version for regression detection
        latest_version_row = self.db.get_latest_version()
        prev_metrics = _parse_json(latest_version_row.get("metrics")) if latest_version_row else {}
        prev_passed = latest_version_row.get("tests_passed") if latest_version_row else None
        prev_failed = latest_version_row.get("tests_failed") if latest_version_row else None

        active_metrics = metrics or {}
        active_errors = errors or []

        is_reg, reg_reasons = detect_regression(
            current_metrics=active_metrics,
            current_tests_passed=tests_passed,
            current_tests_failed=tests_failed,
            previous_metrics=prev_metrics,
            previous_tests_passed=prev_passed,
            previous_tests_failed=prev_failed,
        )

        inferred_st = infer_status(
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            errors=active_errors,
            is_regression=is_reg,
            explicit_status=status,
        )

        # 5. Snapshot artifact
        artifact_path = None
        current_version_id = (project["current_version"] or 0) + 1
        if create_snapshot:
            artifact_path = self._create_snapshot_tar(current_version_id, commit_sha[:7])

        # 6. Build model instance for analysis generation
        dev_version_model = DevelopmentVersion(
            version_id=current_version_id,
            project_id=self.config.project_id,
            timestamp=datetime.now(),
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            agent=agent,
            intent=intent,
            git_commit=commit_sha,
            parent_commit=parent_sha,
            branch=branch,
            changed_files=changed_files,
            additions=additions,
            deletions=deletions,
            feature=feature,
            status=inferred_st,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            metrics=active_metrics,
            errors=active_errors,
            is_regression=is_reg,
            artifact_path=artifact_path,
        )

        prev_version_model = None
        if latest_version_row:
            try:
                prev_version_model = DevelopmentVersion(
                    version_id=latest_version_row["version_id"],
                    project_id=latest_version_row["project_id"],
                    git_commit=latest_version_row["git_commit"],
                    metrics=_parse_json(latest_version_row["metrics"]),
                    tests_passed=latest_version_row["tests_passed"],
                    tests_failed=latest_version_row["tests_failed"],
                )
            except Exception:
                pass

        analysis, recommendation = generate_analysis_and_recommendation(
            version=dev_version_model,
            previous=prev_version_model,
            regression_reasons=reg_reasons,
        )
        dev_version_model.analysis = analysis
        dev_version_model.recommendation = recommendation

        # 7. Persist to SQLite
        new_vid = self.db.create_version(
            project_id=self.config.project_id,
            timestamp=dev_version_model.timestamp.isoformat(),
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            agent=agent,
            intent=intent,
            git_commit=commit_sha,
            parent_commit=parent_sha,
            branch=branch,
            changed_files=changed_files,
            additions=additions,
            deletions=deletions,
            feature=feature,
            status=inferred_st.value,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            metrics=active_metrics,
            errors=active_errors,
            analysis=analysis,
            recommendation=recommendation,
            is_regression=1 if is_reg else 0,
            artifact_path=artifact_path,
        )
        dev_version_model.version_id = new_vid
        self.db.update_current_version(new_vid)

        # 8. Update Feature Table
        if feature:
            feat_st = FeatureStatus.IN_PROGRESS
            if inferred_st == VersionStatus.SUCCESS:
                feat_st = FeatureStatus.COMPLETE
            elif inferred_st == VersionStatus.REGRESSION:
                feat_st = FeatureStatus.PARTIAL
            elif inferred_st == VersionStatus.ERROR:
                feat_st = FeatureStatus.FAILED

            self.db.upsert_feature(
                project_id=self.config.project_id,
                name=feature,
                status=feat_st.value,
                metrics=active_metrics,
            )

        # 9. Sync to Databricks (or local fallback log)
        self.databricks.sync_version(dev_version_model)
        self.databricks.sync_event(
            event_type="checkpoint",
            data={"version_id": new_vid, "status": inferred_st.value, "is_regression": is_reg},
            version_id=new_vid,
        )

        return dev_version_model.model_dump(mode="json")

    def _create_snapshot_tar(self, version_id: int, commit_short: str) -> Optional[str]:
        """Create a lightweight tar.gz snapshot of the current workspace files."""
        artifacts_dir = self.config.artifacts_dir
        os.makedirs(artifacts_dir, exist_ok=True)
        filename = f"v{version_id}_{commit_short}.tar.gz"
        archive_path = os.path.join(artifacts_dir, filename)

        ignore_prefixes = {".git", ".devmemory", ".venv", "__pycache__", "node_modules", ".pytest_cache"}
        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                for root, dirs, files in os.walk(self.project_path):
                    # Filter out ignored directories in-place
                    dirs[:] = [d for d in dirs if d not in ignore_prefixes and not d.startswith(".")]
                    for file in files:
                        if file.endswith((".pyc", ".tar.gz", ".db", ".log")):
                            continue
                        full_p = os.path.join(root, file)
                        rel_p = os.path.relpath(full_p, self.project_path)
                        tar.add(full_p, arcname=rel_p)
            return archive_path
        except Exception:
            return None

    def history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get chronological version history with full metadata."""
        versions = self.db.get_all_versions(limit=limit)
        result = []
        for v in versions:
            result.append({
                "version_id": v["version_id"],
                "timestamp": v["timestamp"],
                "intent": v["intent"],
                "agent": v["agent"],
                "status": v["status"],
                "feature": v["feature"],
                "checkpoint_id": v["checkpoint_id"],
                "session_id": v["session_id"],
                "git_commit": v["git_commit"],
                "branch": v["branch"],
                "changed_files": _parse_json(v["changed_files"]),
                "additions": v["additions"],
                "deletions": v["deletions"],
                "tests_passed": v["tests_passed"],
                "tests_failed": v["tests_failed"],
                "metrics": _parse_json(v["metrics"]),
                "errors": _parse_json(v["errors"]),
                "analysis": v["analysis"],
                "recommendation": v["recommendation"],
                "is_regression": bool(v["is_regression"]),
                "artifact_path": v["artifact_path"],
            })
        return result

    def diff(self, version_a: int, version_b: int) -> Dict[str, Any]:
        """Compare two development versions across code, tests, and metrics."""
        va = self.db.get_version(version_a)
        vb = self.db.get_version(version_b)
        if not va or not vb:
            return {"error": f"Version {version_a} or {version_b} not found"}

        git_diff = self.git.get_diff_stats(va["git_commit"], vb["git_commit"])
        metrics_a = _parse_json(va["metrics"])
        metrics_b = _parse_json(vb["metrics"])

        metric_changes = {}
        all_keys = set(list(metrics_a.keys()) + list(metrics_b.keys()))
        for key in all_keys:
            old_val = metrics_a.get(key)
            new_val = metrics_b.get(key)
            if old_val is not None and new_val is not None:
                try:
                    chg = float(new_val) - float(old_val)
                    direction = "improved" if chg > 0 else "regressed" if chg < 0 else "unchanged"
                    metric_changes[key] = {
                        "before": old_val,
                        "after": new_val,
                        "change": round(chg, 4),
                        "direction": direction,
                    }
                except (ValueError, TypeError):
                    metric_changes[key] = {"before": old_val, "after": new_val}

        return {
            "version_a": dict(va),
            "version_b": dict(vb),
            "files": git_diff.get("files", []),
            "additions": git_diff.get("additions", 0),
            "deletions": git_diff.get("deletions", 0),
            "diff_text": git_diff.get("diff", ""),
            "metric_changes": metric_changes,
            "test_changes": {
                "passed": (vb["tests_passed"] or 0) - (va["tests_passed"] or 0),
                "failed": (vb["tests_failed"] or 0) - (va["tests_failed"] or 0),
            },
        }

    def restore(self, version_id: int) -> Dict[str, Any]:
        """Safely restore/checkout the Git state corresponding to a version."""
        target_version = self.db.get_version(version_id)
        if not target_version:
            return {"error": f"Version {version_id} not found."}

        commit_sha = target_version["git_commit"]
        branch_name = self.git.restore_commit(commit_sha)

        self.db.log_event(
            project_id=self.config.project_id,
            version_id=version_id,
            event_type="restore",
            data={"target_version": version_id, "commit": commit_sha, "branch": branch_name},
        )

        return {
            "status": "success",
            "message": f"Successfully checked out version v{version_id} ({commit_sha[:8]}) to branch '{branch_name}'",
            "branch": branch_name,
            "commit": commit_sha,
        }

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search across intents, features, agents, and analysis."""
        return self.db.search_versions(query)

    def context(self, feature: str = "", intent: str = "") -> Dict[str, Any]:
        """Provide AI context with past warnings and regression prevention guidance."""
        status_info = self.status()
        features = self.db.get_all_features()
        warnings = find_similar_attempts(self.db, intent=intent, feature=feature)
        prompt_snippet = format_agent_context(status_info, warnings, features)

        return {
            "project_name": status_info.get("project_name"),
            "current_version": status_info.get("current_version"),
            "total_versions": status_info.get("total_versions"),
            "completed_features": [f["name"] for f in features if f.get("status") == "COMPLETE"],
            "incomplete_features": [f["name"] for f in features if f.get("status") != "COMPLETE"],
            "latest_metrics": status_info.get("latest_metrics", {}),
            "warnings": warnings,
            "prompt_snippet": prompt_snippet,
        }

    def features(self) -> List[Dict[str, Any]]:
        """Get all tracked project features with their version histories."""
        features = self.db.get_all_features()
        result = []
        for f in features:
            versions = self.db.get_versions_by_feature(f["name"])
            result.append({
                "name": f["name"],
                "status": f["status"],
                "version_count": len(versions),
                "latest_metrics": _parse_json(f.get("latest_metrics")),
                "history": [
                    {
                        "version_id": v["version_id"],
                        "status": v["status"],
                        "metrics": _parse_json(v["metrics"]),
                        "timestamp": v["timestamp"],
                    }
                    for v in versions
                ],
            })
        return result

    def analytics(self) -> Dict[str, Any]:
        """Get analytics insights across agents and regression patterns."""
        local_versions = self.db.get_all_versions(limit=200)
        return self.databricks.get_analytics_summary(local_versions=local_versions)


def init(project_path: str = ".", name: str = "", project_id: str = "") -> DevMemoryProject:
    """Initialize DevMemory tracking in a project directory."""
    project_path = os.path.abspath(project_path)
    config = DevMemoryConfig.create(project_path, name=name, project_id=project_id)
    db = DevMemoryDB(project_path)
    db.initialize()
    db.create_project(config.project_id, config.project_name, project_path)
    return DevMemoryProject(project_path)


def _parse_json(val: Any) -> Any:
    """Safely parse a JSON string or return as-is if already a dict or list."""
    if val is None:
        return {}
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return {}
