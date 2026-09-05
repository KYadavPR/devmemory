"""Phase 10: Databricks adapter (record shaping + mocked statement execution) and
the offline outbox sync. No real workspace is ever contacted."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from devmemory.adapters.databricks import (
    _VERSION_FIELDS,
    DatabricksAdapter,
    _as_param,
    outbox_event,
    version_record,
)
from devmemory.cli.app import app
from devmemory.domain.enums import (
    AssociationMethod,
    ChangeType,
    MetricDirection,
    VersionStatus,
)
from devmemory.domain.models import (
    ChangedFile,
    CheckpointReference,
    DevelopmentVersion,
    Metric,
    Regression,
    TestOutcome,
)
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.databricks_sync import drain, enqueue, push_version, sync_status
from devmemory.services.projects import init_project
from tests.conftest import TmpGitRepo

runner = CliRunner()


# --- a version with a secret-looking intent and real source paths -----------------


def _sample_version() -> DevelopmentVersion:
    return DevelopmentVersion(
        version_id="v7",
        version_number=7,
        project_id="demo",
        intent="export DATABRICKS_TOKEN=dapi-supersecret then " + "context " * 500,
        agent="Claude Code",
        model="claude-sonnet-5",
        git_commit="a" * 40,
        parent_commit="b" * 40,
        branch="main",
        feature_id="demo:authentication",
        status=VersionStatus.REGRESSION,
        files_changed=2,
        lines_added=10,
        lines_removed=3,
        changed_files=[
            ChangedFile(
                path="src/auth/tokens.py",
                change_type=ChangeType.MODIFIED,
                additions=10,
                deletions=3,
            ),
        ],
        primary_checkpoint=CheckpointReference(
            checkpoint_id="01J8ZZZ",
            association_method=AssociationMethod.TRAILER,
            association_confidence=1.0,
        ),
        entire_association_method=AssociationMethod.TRAILER,
        entire_association_confidence=1.0,
        tests=TestOutcome(command="pytest", total=30, passed=24, failed=6, skipped=0),
        metrics=[
            Metric(
                name="latency_ms",
                before=100.0,
                after=400.0,
                unit="ms",
                direction=MetricDirection.LOWER_IS_BETTER,
            )
        ],
        regressions=[
            Regression(
                kind="metric",
                metric="latency_ms",
                before=100.0,
                after=400.0,
                change_percent=300.0,
                severity="HIGH",
                detail="latency up 300%",
            )
        ],
        created_at=datetime(2026, 9, 6, 12, 0, tzinfo=UTC),
        committed_at=datetime(2026, 9, 6, 11, 0, tzinfo=UTC),
    )


def test_version_record_is_exactly_the_allowlist() -> None:
    record = version_record(_sample_version())
    assert set(record) == set(_VERSION_FIELDS)


def test_version_record_carries_no_source_transcript_or_secret() -> None:
    v = _sample_version()
    blob = json.dumps(version_record(v))

    # the changed-file *path* is telemetry, but never file contents / diffs / transcripts
    for banned in ("diff", "transcript", "patch", "content", "prompt.txt"):
        assert banned not in blob
    # the intent is truncated and still travels, but nothing longer than the cap
    assert len(version_record(v)["intent"]) <= 2000
    # a secret pasted into the intent is not something we can scrub here, but the
    # normalized record must not invent secret-bearing fields
    assert "token" not in set(_VERSION_FIELDS)
    assert "api_key" not in set(_VERSION_FIELDS)


def test_version_record_values() -> None:
    record = version_record(_sample_version())
    assert record["version_id"] == "v7"
    assert record["feature"] == "authentication"
    assert record["checkpoint_id"] == "01J8ZZZ"
    assert record["association_method"] == "trailer"
    assert record["is_regression"] is True
    assert record["regression_severity"] == "HIGH"
    assert record["tests_total"] == 30
    assert record["committed_at"] == "2026-09-06T11:00:00+00:00"


def test_outbox_event_shape() -> None:
    event = outbox_event(_sample_version())
    assert event["kind"] == "version"
    assert event["record"]["version_id"] == "v7"
    assert event["changed_files"][0]["path"] == "src/auth/tokens.py"
    assert event["metrics"][0]["name"] == "latency_ms"
    assert event["regressions"][0]["severity"] == "HIGH"


def test_as_param_coercions() -> None:
    assert _as_param(None) is None
    assert _as_param(True) == "true"
    assert _as_param(False) == "false"
    assert _as_param(42) == "42"
    assert _as_param(3.5) == "3.5"


# --- mocked statement execution --------------------------------------------------


class _FakeCol:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeSchema:
    def __init__(self, cols: list[str]) -> None:
        self.columns = [_FakeCol(c) for c in cols]


class _FakeManifest:
    def __init__(self, cols: list[str]) -> None:
        self.schema = _FakeSchema(cols)


class _FakeResult:
    def __init__(self, rows: list[list[object]]) -> None:
        self.data_array = rows


class _FakeStatus:
    def __init__(self) -> None:
        from databricks.sdk.service.sql import StatementState

        self.state = StatementState.SUCCEEDED
        self.error = None


class _FakeResp:
    def __init__(self, cols: list[str] | None, rows: list[list[object]] | None) -> None:
        self.status = _FakeStatus()
        self.manifest = _FakeManifest(cols) if cols is not None else None
        self.result = _FakeResult(rows) if rows is not None else None


class _FakeStatementExecution:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.cols: list[str] | None = None
        self.rows: list[list[object]] | None = None

    def execute_statement(self, **kw: object) -> _FakeResp:
        self.calls.append(kw)
        return _FakeResp(self.cols, self.rows)


class _FakeClient:
    def __init__(self) -> None:
        self.statement_execution = _FakeStatementExecution()


@pytest.fixture
def fake_adapter(config: object) -> tuple[DatabricksAdapter, _FakeClient]:
    adapter = DatabricksAdapter(config)  # type: ignore[arg-type]
    fake = _FakeClient()
    adapter._client = fake  # type: ignore[assignment]
    adapter._warehouse_id = "wh-test"
    return adapter, fake


def test_query_binds_named_params_never_interpolates(
    fake_adapter: tuple[DatabricksAdapter, _FakeClient],
) -> None:
    adapter, fake = fake_adapter
    fake.statement_execution.cols = ["version_id", "status"]
    fake.statement_execution.rows = [["v1", "SUCCESS"], ["v2", "REGRESSION"]]

    table = adapter.table("fact_versions")
    rows = adapter.query(
        f"SELECT version_id, status FROM {table} WHERE project_id = :pid",  # noqa: S608
        {"pid": "demo"},
    )

    assert rows == [
        {"version_id": "v1", "status": "SUCCESS"},
        {"version_id": "v2", "status": "REGRESSION"},
    ]
    call = fake.statement_execution.calls[0]
    assert call["warehouse_id"] == "wh-test"
    params = call["parameters"]
    assert params is not None
    assert params[0].name == "pid"  # type: ignore[index]
    assert params[0].value == "demo"  # type: ignore[index]
    # the literal value must not have been baked into the SQL text
    assert "demo" not in str(call["statement"])


def test_publish_version_merges_with_bound_params(
    fake_adapter: tuple[DatabricksAdapter, _FakeClient],
) -> None:
    adapter, fake = fake_adapter
    adapter.publish_version(_sample_version())

    statements = [str(c["statement"]) for c in fake.statement_execution.calls]
    merge = next(s for s in statements if s.startswith("MERGE INTO"))
    assert ":version_id" in merge and ":project_id" in merge
    # the secret pasted in the intent must never appear inline in any statement
    assert not any("dapi-supersecret" in s for s in statements)
    # children are inserted with :param markers too
    assert any("INSERT INTO" in s and ":path" in s for s in statements)


def test_execute_raises_on_non_success(
    fake_adapter: tuple[DatabricksAdapter, _FakeClient],
) -> None:
    from devmemory.domain.errors import DatabricksError

    adapter, fake = fake_adapter

    class _FailResp(_FakeResp):
        def __init__(self) -> None:
            super().__init__(None, None)
            from databricks.sdk.service.sql import StatementState

            self.status.state = StatementState.FAILED

    fake.statement_execution.execute_statement = lambda **kw: _FailResp()  # type: ignore[assignment]
    with pytest.raises(DatabricksError):
        adapter.execute("SELECT 1")


# --- offline outbox / sync ------------------------------------------------------


@pytest.fixture
def project(git_repo: TmpGitRepo) -> Iterator[ProjectContext]:
    git_repo.write("app.py", "x = 0\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    git_repo.commit("chore: devmemory")
    ctx = ProjectContext.load(git_repo.path)
    try:
        yield ctx
    finally:
        ctx.close()


def _seed(project: ProjectContext, repo: TmpGitRepo, n: int = 2) -> None:
    for i in range(n):
        repo.write("app.py", f"x = {i + 1}\n")
        repo.commit(f"feat: change {i + 1}")
        run_checkpoint(
            project,
            CheckpointRequest(
                allow_no_entire=True,
                intent=f"Change number {i + 1}",
                status=VersionStatus.SUCCESS,
            ),
        )


def test_pipeline_queues_to_outbox_when_databricks_disabled(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    _seed(project, git_repo, n=2)
    queued = sorted(p.stem for p in project.paths.outbox_dir.glob("*.json"))
    assert queued == ["v1", "v2"]

    event = json.loads((project.paths.outbox_dir / "v1.json").read_text())
    assert event["record"]["version_id"] == "v1"


def test_enqueue_is_idempotent(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    from devmemory.storage.versions import VersionRepository

    _seed(project, git_repo, n=1)
    v = VersionRepository(project.db).get("v1")
    assert v is not None
    path_a = enqueue(project, v)
    path_b = enqueue(project, v)
    assert path_a == path_b
    assert len(list(project.paths.outbox_dir.glob("*.json"))) == 1


def test_push_version_without_credentials_reports_unconfigured(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    from devmemory.storage.versions import VersionRepository

    _seed(project, git_repo, n=1)
    v = VersionRepository(project.db).get("v1")
    assert v is not None
    result = push_version(project, v)
    assert result.configured is False
    assert result.queued == ["v1"]


def test_sync_status_unconfigured(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _seed(project, git_repo, n=2)
    s = sync_status(project)
    assert s.configured is False
    assert sorted(s.queued) == ["v1", "v2"]
    assert s.detail == "not configured"


def test_drain_publishes_and_clears_outbox_with_mocked_workspace(
    project: ProjectContext, git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(project, git_repo, n=2)
    assert len(list(project.paths.outbox_dir.glob("*.json"))) == 2

    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-not-real")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh-test")
    project.config.databricks.enabled = True

    fake = _FakeClient()
    monkeypatch.setattr(DatabricksAdapter, "_workspace", lambda self: fake)

    result = drain(project)
    assert result.configured is True
    assert sorted(result.pushed) == ["v1", "v2"]
    assert result.failed == []
    assert list(project.paths.outbox_dir.glob("*.json")) == []
    assert any(str(c["statement"]).startswith("MERGE INTO") for c in fake.statement_execution.calls)


def test_drain_keeps_outbox_when_workspace_unreachable(
    project: ProjectContext, git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(project, git_repo, n=2)

    monkeypatch.setenv("DATABRICKS_HOST", "https://example.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-not-real")
    monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh-test")
    project.config.databricks.enabled = True

    fake = _FakeClient()

    def _unreachable(**kw: object) -> _FakeResp:
        raise ConnectionError("network down")

    fake.statement_execution.execute_statement = _unreachable  # type: ignore[assignment]
    monkeypatch.setattr(DatabricksAdapter, "_workspace", lambda self: fake)

    result = drain(project)
    assert sorted(result.queued) == ["v1", "v2"]
    assert result.pushed == []
    assert "could not reach Databricks" in (result.detail or "")
    assert len(list(project.paths.outbox_dir.glob("*.json"))) == 2


def test_cli_databricks_status_and_push(
    project: ProjectContext, git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(project, git_repo, n=2)
    project.close()
    monkeypatch.chdir(git_repo.path)

    result = runner.invoke(app, ["databricks", "status"])
    assert result.exit_code == 0, result.output
    assert "configured: False" in result.output
    assert "queued: 2" in result.output

    result = runner.invoke(app, ["databricks", "push"])
    assert result.exit_code == 0, result.output
    assert "not configured" in result.output.lower() or "credentials are not set" in result.output
