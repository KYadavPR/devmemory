"""Databricks SQL connector and analytics adapter for DevMemory.

Sends development versions and events to Databricks Delta Lake tables for
cross-project analytics, agent effectiveness evaluation, and regression tracking.
Falls back safely to local event logging if Databricks is not configured.
"""

import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from devmemory.config import DevMemoryConfig
from devmemory.models import DevelopmentVersion


class DatabricksAdapter:
    """Manages synchronization and queries to Databricks Delta tables."""

    def __init__(self, config: DevMemoryConfig):
        self.config = config
        self._connector = None

    @property
    def is_configured(self) -> bool:
        """Check if required Databricks credentials are provided."""
        return bool(
            self.config.databricks_host
            and self.config.databricks_http_path
            and self.config.databricks_token
        )

    def _get_connection(self):
        """Create a Databricks SQL connection if library and config are present."""
        if not self.is_configured:
            return None
        try:
            from databricks import sql
            return sql.connect(
                server_hostname=self.config.databricks_host,
                http_path=self.config.databricks_http_path,
                access_token=self.config.databricks_token,
            )
        except Exception:
            return None

    def initialize_tables(self) -> bool:
        """Create Databricks Delta Lake tables if connected."""
        conn = self._get_connection()
        if not conn:
            return False

        catalog = self.config.databricks_catalog
        schema = self.config.databricks_schema

        try:
            with conn.cursor() as cursor:
                cursor.execute(f"CREATE CATALOG IF NOT EXISTS {catalog}")
                cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {catalog}.{schema}.development_versions (
                        version_id INT,
                        project_id STRING,
                        timestamp TIMESTAMP,
                        checkpoint_id STRING,
                        session_id STRING,
                        agent STRING,
                        intent STRING,
                        git_commit STRING,
                        parent_commit STRING,
                        branch STRING,
                        changed_files ARRAY<STRING>,
                        additions INT,
                        deletions INT,
                        feature STRING,
                        status STRING,
                        tests_passed INT,
                        tests_failed INT,
                        metrics MAP<STRING, DOUBLE>,
                        errors ARRAY<STRING>,
                        analysis STRING,
                        recommendation STRING,
                        is_regression BOOLEAN,
                        artifact_path STRING
                    ) USING DELTA
                    """
                )
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {catalog}.{schema}.development_events (
                        event_id STRING,
                        project_id STRING,
                        version_id INT,
                        event_type STRING,
                        timestamp TIMESTAMP,
                        source STRING,
                        data STRING
                    ) USING DELTA
                    """
                )
            conn.close()
            return True
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            return False

    def sync_version(self, version: DevelopmentVersion) -> bool:
        """Send a development version record to Databricks, with local fallback."""
        conn = self._get_connection()
        if conn:
            try:
                catalog = self.config.databricks_catalog
                schema = self.config.databricks_schema
                table = f"{catalog}.{schema}.development_versions"

                # Parse float metrics
                metrics_map = {k: float(v) for k, v in version.metrics.items() if isinstance(v, (int, float))}

                with conn.cursor() as cursor:
                    sql_stmt = f"""
                    INSERT INTO {table}
                    (version_id, project_id, timestamp, checkpoint_id, session_id, agent, intent,
                     git_commit, parent_commit, branch, changed_files, additions, deletions,
                     feature, status, tests_passed, tests_failed, metrics, errors, analysis,
                     recommendation, is_regression, artifact_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    cursor.execute(
                        sql_stmt,
                        [
                            version.version_id,
                            version.project_id,
                            version.timestamp.isoformat(),
                            version.checkpoint_id,
                            version.session_id,
                            version.agent,
                            version.intent,
                            version.git_commit,
                            version.parent_commit,
                            version.branch,
                            version.changed_files,
                            version.additions,
                            version.deletions,
                            version.feature,
                            version.status.value,
                            version.tests_passed,
                            version.tests_failed,
                            metrics_map,
                            version.errors,
                            version.analysis,
                            version.recommendation,
                            version.is_regression,
                            version.artifact_path,
                        ],
                    )
                conn.close()
                return True
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

        # Local fallback logging
        self._log_local_sync("version", version.model_dump(mode="json"))
        return False

    def sync_event(self, event_type: str, data: Dict[str, Any], version_id: Optional[int] = None) -> bool:
        """Send a development event to Databricks or log locally."""
        conn = self._get_connection()
        if conn:
            try:
                catalog = self.config.databricks_catalog
                schema = self.config.databricks_schema
                table = f"{catalog}.{schema}.development_events"

                with conn.cursor() as cursor:
                    sql_stmt = f"""
                    INSERT INTO {table} (event_id, project_id, version_id, event_type, timestamp, source, data)
                    VALUES (uuid(), ?, ?, ?, ?, 'devmemory', ?)
                    """
                    cursor.execute(
                        sql_stmt,
                        [
                            self.config.project_id,
                            version_id,
                            event_type,
                            datetime.now().isoformat(),
                            json.dumps(data),
                        ],
                    )
                conn.close()
                return True
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

        self._log_local_sync("event", {"event_type": event_type, "version_id": version_id, "data": data})
        return False

    def get_analytics_summary(self, local_versions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Produce cross-version analytics either from live Databricks or local versions fallback."""
        conn = self._get_connection()
        if conn:
            try:
                catalog = self.config.databricks_catalog
                schema = self.config.databricks_schema
                table = f"{catalog}.{schema}.development_versions"

                analytics: Dict[str, Any] = {"source": "databricks_live"}
                with conn.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT agent, COUNT(*) as total,
                               SUM(CASE WHEN is_regression THEN 1 ELSE 0 END) as regressions
                        FROM {table}
                        WHERE agent IS NOT NULL
                        GROUP BY agent
                        """
                    )
                    analytics["agent_performance"] = [
                        {"agent": r[0], "total": r[1], "regressions": r[2]}
                        for r in cursor.fetchall()
                    ]
                conn.close()
                return analytics
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

        # Local heuristics fallback from local version list
        versions = local_versions or []
        agent_stats: Dict[str, Dict[str, int]] = {}
        file_fail_counts: Dict[str, int] = {}
        total_regressions = 0

        for v in versions:
            agent = v.get("agent") or "Unknown"
            if agent not in agent_stats:
                agent_stats[agent] = {"total": 0, "regressions": 0, "success": 0}
            agent_stats[agent]["total"] += 1
            if v.get("is_regression") or v.get("status") == "REGRESSION":
                agent_stats[agent]["regressions"] += 1
                total_regressions += 1
            elif v.get("status") == "SUCCESS":
                agent_stats[agent]["success"] += 1

            # Track files in failed versions
            if v.get("is_regression") or v.get("status") in ("REGRESSION", "ERROR"):
                cf = v.get("changed_files")
                files = json.loads(cf) if isinstance(cf, str) else (cf or [])
                for f in files:
                    file_fail_counts[f] = file_fail_counts.get(f, 0) + 1

        top_risky_files = sorted(
            [{"file": k, "fail_count": v} for k, v in file_fail_counts.items()],
            key=lambda x: x["fail_count"],
            reverse=True,
        )[:5]

        agent_perf = [
            {
                "agent": k,
                "total": v["total"],
                "regressions": v["regressions"],
                "success_rate": round((v["success"] / v["total"]) * 100, 1) if v["total"] > 0 else 0,
            }
            for k, v in agent_stats.items()
        ]

        return {
            "source": "local_analytics",
            "is_databricks_connected": self.is_configured,
            "total_regressions": total_regressions,
            "agent_performance": agent_perf,
            "risky_files": top_risky_files,
            "recommended_query": "SELECT agent, COUNT(*) as regressions FROM development_versions WHERE is_regression = TRUE GROUP BY agent ORDER BY regressions DESC;",
        }

    def _log_local_sync(self, item_type: str, payload: Dict[str, Any]):
        """Log unsynced Databricks records to a local JSONL queue."""
        log_path = os.path.join(self.config.devmemory_dir, "databricks_sync_queue.jsonl")
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                record = {
                    "timestamp": datetime.now().isoformat(),
                    "type": item_type,
                    "payload": payload,
                }
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass
