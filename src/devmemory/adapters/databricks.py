"""Databricks adapter - publish normalized development telemetry to Delta tables
and run analytical queries.

REST only: the SQL Statement Execution API against a serverless SQL warehouse.
No Spark, no cluster. Credentials come from the environment
(``DATABRICKS_HOST`` / ``DATABRICKS_TOKEN`` / ``DATABRICKS_WAREHOUSE_ID``).

Only a fixed allowlist of normalized fields is ever sent - never source code,
transcripts, or secrets. A failure here never touches local history; the caller
falls back to the local analytics path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from devmemory.config import DevMemoryConfig, resolve_databricks_credentials
from devmemory.domain.errors import DatabricksError
from devmemory.domain.models import DevelopmentVersion
from devmemory.logging import get_logger

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

_log = get_logger(__name__)

# Fields allowed to leave the machine. Anything not here is never published.
_VERSION_FIELDS = (
    "project_id",
    "version_id",
    "version_number",
    "intent",
    "agent",
    "model",
    "checkpoint_id",
    "association_method",
    "association_confidence",
    "git_commit",
    "parent_commit",
    "branch",
    "feature",
    "status",
    "files_changed",
    "lines_added",
    "lines_removed",
    "is_regression",
    "regression_severity",
    "tests_total",
    "tests_passed",
    "tests_failed",
    "committed_at",
    "recorded_at",
)


class DatabricksUnavailableError(DatabricksError):
    """Databricks is not configured, the SDK is missing, or the workspace is unreachable."""


class DatabricksAdapter:
    def __init__(self, config: DevMemoryConfig) -> None:
        self._config = config
        self._catalog = config.databricks.catalog
        self._schema = config.databricks.schema_name
        self._client: WorkspaceClient | None = None
        self._warehouse_id: str = ""

    @property
    def is_configured(self) -> bool:
        return resolve_databricks_credentials() is not None

    def table(self, name: str) -> str:
        return f"{self._catalog}.{self._schema}.{name}"

    # -- connection ---------------------------------------------------

    def _workspace(self) -> WorkspaceClient:
        if self._client is not None:
            return self._client
        creds = resolve_databricks_credentials()
        if creds is None:
            raise DatabricksUnavailableError(
                "Databricks credentials are not set.",
                hint="Set DATABRICKS_HOST, DATABRICKS_TOKEN and DATABRICKS_WAREHOUSE_ID.",
            )
        try:
            from databricks.sdk import WorkspaceClient
        except ImportError as exc:  # pragma: no cover - extra not installed
            raise DatabricksUnavailableError(
                "the databricks extra is not installed",
                hint="pip install 'devmemory[databricks]'",
            ) from exc
        self._client = WorkspaceClient(host=creds.host, token=creds.token)
        self._warehouse_id = creds.warehouse_id
        return self._client

    # -- statement execution (named `:param` markers only) -----------

    def _execute(self, statement: str, params: dict[str, object] | None = None) -> Any:
        from databricks.sdk.service.sql import StatementParameterListItem, StatementState

        client = self._workspace()
        parameters = (
            [StatementParameterListItem(name=k, value=_as_param(v)) for k, v in params.items()]
            if params
            else None
        )
        try:
            resp = client.statement_execution.execute_statement(
                warehouse_id=self._warehouse_id,
                statement=statement,
                parameters=parameters,
                wait_timeout="30s",
                catalog=self._catalog,
                schema=self._schema,
            )
        except Exception as exc:
            raise DatabricksUnavailableError(f"statement failed: {exc}") from exc

        state = resp.status.state if resp.status else None
        if state is not StatementState.SUCCEEDED:
            detail = resp.status.error.message if resp.status and resp.status.error else state
            raise DatabricksError(f"Databricks statement did not succeed: {detail}")
        return resp

    def query(
        self, statement: str, params: dict[str, object] | None = None
    ) -> list[dict[str, Any]]:
        resp = self._execute(statement, params)
        schema = resp.manifest.schema if resp.manifest else None
        cols = [c.name for c in (schema.columns or [])] if schema else []
        data = (resp.result.data_array if resp.result else None) or []
        return [dict(zip(cols, row, strict=False)) for row in data]

    def execute(self, statement: str, params: dict[str, object] | None = None) -> None:
        self._execute(statement, params)

    # -- schema -----------------------------------------------------

    def bootstrap(self) -> None:
        """Create the schema and Delta tables if they do not exist. Idempotent."""
        self.execute(f"CREATE SCHEMA IF NOT EXISTS {self._catalog}.{self._schema}")
        for ddl in _SCHEMA_DDL:
            self.execute(ddl.format(t=f"{self._catalog}.{self._schema}"))
        _log.info("databricks.bootstrap", schema=f"{self._catalog}.{self._schema}")

    # -- publish ---------------------------------------------------

    def publish_version(self, version: DevelopmentVersion) -> None:
        row = version_record(version)
        self.bootstrap()

        cols = ", ".join(_VERSION_FIELDS)
        values = ", ".join(f":{f}" for f in _VERSION_FIELDS)
        # Spark SQL rejects a column-alias list after the subquery (`s (a, b, ...)`);
        # alias each column inside the SELECT instead.
        source = ", ".join(f":{f} AS {f}" for f in _VERSION_FIELDS)
        updates = ", ".join(
            f"{f} = :{f}" for f in _VERSION_FIELDS if f not in ("project_id", "version_id")
        )
        merge = (
            f"MERGE INTO {self.table('fact_versions')} t "
            f"USING (SELECT {source}) s "
            f"ON t.project_id = s.project_id AND t.version_id = s.version_id "
            f"WHEN MATCHED THEN UPDATE SET {updates} "
            f"WHEN NOT MATCHED THEN INSERT ({cols}) VALUES ({values})"
        )
        self.execute(merge, {f: row.get(f) for f in _VERSION_FIELDS})
        self._publish_children(version)
        _log.info("databricks.published", version=version.version_id)

    def _publish_children(self, version: DevelopmentVersion) -> None:
        vid, pid = version.version_id, self._config.project_id
        scope: dict[str, object] = {"pid": pid, "vid": vid}
        for table in ("fact_changed_files", "fact_metrics", "fact_tests", "fact_regressions"):
            self.execute(
                f"DELETE FROM {self.table(table)} WHERE project_id = :pid AND version_id = :vid",
                scope,
            )
        for i, f in enumerate(version.changed_files):
            self.execute(
                f"INSERT INTO {self.table('fact_changed_files')} "
                "(project_id, version_id, path, change_type, additions, deletions) "
                "VALUES (:pid, :vid, :path, :ct, :add, :del)",
                {
                    **scope,
                    "path": f.path,
                    "ct": f.change_type.value,
                    "add": f.additions,
                    "del": f.deletions,
                    "_i": i,
                },
            )
        for m in version.metrics:
            self.execute(
                f"INSERT INTO {self.table('fact_metrics')} "
                "(project_id, version_id, name, before_value, after_value, unit, direction) "
                "VALUES (:pid, :vid, :name, :before, :after, :unit, :dir)",
                {
                    **scope,
                    "name": m.name,
                    "before": m.before,
                    "after": m.after,
                    "unit": m.unit,
                    "dir": m.direction.value,
                },
            )
        if version.tests and version.tests.ran:
            t = version.tests
            self.execute(
                f"INSERT INTO {self.table('fact_tests')} "
                "(project_id, version_id, total, passed, failed, skipped, command) "
                "VALUES (:pid, :vid, :total, :passed, :failed, :skipped, :cmd)",
                {
                    **scope,
                    "total": t.total,
                    "passed": t.passed,
                    "failed": t.failed,
                    "skipped": t.skipped,
                    "cmd": t.command,
                },
            )
        for r in version.regressions:
            self.execute(
                f"INSERT INTO {self.table('fact_regressions')} "
                "(project_id, version_id, kind, metric, before_value, after_value, "
                "change_percent, severity) "
                "VALUES (:pid, :vid, :kind, :metric, :before, :after, :pct, :sev)",
                {
                    **scope,
                    "kind": r.kind,
                    "metric": r.metric,
                    "before": r.before,
                    "after": r.after,
                    "pct": r.change_percent,
                    "sev": r.severity,
                },
            )


# --- record shaping -----------------------------------------------------------


def version_record(version: DevelopmentVersion) -> dict[str, Any]:
    """The exact allowlisted row published for a version. No source, no secrets."""
    cp = version.primary_checkpoint
    worst = max(
        (r.severity for r in version.regressions),
        key=lambda s: {"HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(s, 0),
        default=None,
    )
    record: dict[str, Any] = {
        "project_id": version.project_id,
        "version_id": version.version_id,
        "version_number": version.version_number,
        "intent": (version.intent or "")[:2000] or None,
        "agent": version.agent,
        "model": version.model,
        "checkpoint_id": cp.checkpoint_id if cp else None,
        "association_method": version.entire_association_method.value,
        "association_confidence": version.entire_association_confidence,
        "git_commit": version.git_commit,
        "parent_commit": version.parent_commit,
        "branch": version.branch,
        "feature": version.feature_id.split(":", 1)[-1] if version.feature_id else None,
        "status": version.status.value,
        "files_changed": version.files_changed,
        "lines_added": version.lines_added,
        "lines_removed": version.lines_removed,
        "is_regression": bool(version.regressions) or version.status.value == "REGRESSION",
        "regression_severity": worst,
        "tests_total": version.tests.total if version.tests and version.tests.ran else None,
        "tests_passed": version.tests.passed if version.tests and version.tests.ran else None,
        "tests_failed": version.tests.failed if version.tests and version.tests.ran else None,
        "committed_at": version.committed_at.isoformat() if version.committed_at else None,
        "recorded_at": version.created_at.isoformat(),
    }
    return {k: record.get(k) for k in _VERSION_FIELDS}


def outbox_event(version: DevelopmentVersion) -> dict[str, Any]:
    return {
        "kind": "version",
        "queued_at": datetime.now(UTC).isoformat(),
        "record": version_record(version),
        "changed_files": [
            {
                "path": f.path,
                "change_type": f.change_type.value,
                "additions": f.additions,
                "deletions": f.deletions,
            }
            for f in version.changed_files
        ],
        "metrics": [
            {
                "name": m.name,
                "before": m.before,
                "after": m.after,
                "unit": m.unit,
                "direction": m.direction.value,
            }
            for m in version.metrics
        ],
        "regressions": [r.model_dump(mode="json") for r in version.regressions],
    }


def _as_param(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


_SCHEMA_DDL = (
    """CREATE TABLE IF NOT EXISTS {t}.fact_versions (
        project_id STRING, version_id STRING, version_number INT, intent STRING,
        agent STRING, model STRING, checkpoint_id STRING, association_method STRING,
        association_confidence DOUBLE, git_commit STRING, parent_commit STRING, branch STRING,
        feature STRING, status STRING, files_changed INT, lines_added INT, lines_removed INT,
        is_regression BOOLEAN, regression_severity STRING, tests_total INT, tests_passed INT,
        tests_failed INT, committed_at STRING, recorded_at STRING
    ) USING DELTA""",
    """CREATE TABLE IF NOT EXISTS {t}.fact_changed_files (
        project_id STRING, version_id STRING, path STRING, change_type STRING,
        additions INT, deletions INT
    ) USING DELTA""",
    """CREATE TABLE IF NOT EXISTS {t}.fact_metrics (
        project_id STRING, version_id STRING, name STRING, before_value DOUBLE,
        after_value DOUBLE, unit STRING, direction STRING
    ) USING DELTA""",
    """CREATE TABLE IF NOT EXISTS {t}.fact_tests (
        project_id STRING, version_id STRING, total INT, passed INT, failed INT,
        skipped INT, command STRING
    ) USING DELTA""",
    """CREATE TABLE IF NOT EXISTS {t}.fact_regressions (
        project_id STRING, version_id STRING, kind STRING, metric STRING,
        before_value DOUBLE, after_value DOUBLE, change_percent DOUBLE, severity STRING
    ) USING DELTA""",
)


__all__ = ["DatabricksAdapter", "DatabricksUnavailableError", "outbox_event", "version_record"]
