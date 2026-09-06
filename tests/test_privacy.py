"""Track 1: Privacy Boundary Test Suite.

Verifies:
1. Raw Entire Checkpoint prompts and transcripts must NOT be sent to external services (Databricks).
2. DevMemory must continue providing useful output when sensitive Checkpoint fields are redacted, missing, or unavailable.
3. Existing local functionality must continue working without requiring external services.
4. The system never invents or guesses developer intent when Entire prompts or transcripts are missing, empty, or redacted.
5. Context completeness (COMPLETE / PARTIAL / MISSING) is accurately tracked across versions and checkpoints.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devmemory.adapters.databricks import (
    _VERSION_FIELDS,
    outbox_event,
    version_record,
)
from devmemory.adapters.entire import EntireAdapter
from devmemory.analysis.base import AnalysisInput
from devmemory.analysis.rules import RulesProvider
from devmemory.cli.app import app
from devmemory.domain.enums import (
    AssociationMethod,
    ChangeType,
    ContextStatus,
    MetricDirection,
    VersionStatus,
)
from devmemory.domain.models import (
    ChangedFile,
    CheckpointReference,
    DevelopmentEvent,
    DevelopmentVersion,
    Metric,
    TestOutcome,
)
from devmemory.privacy.boundary import (
    SAFE_EXPORT_FIELDS,
    SENSITIVE_FIELDS,
    compute_context_status,
    determine_analysis_confidence,
    is_missing_or_redacted,
    is_redacted,
    sanitize_for_export,
)
from devmemory.services.context import ProjectContext
from devmemory.services.memory import MemoryQuery, previous_attempts
from devmemory.services.projects import init_project
from devmemory.services.taskloop.engine import get_checkpoint
from devmemory.services.versions import create_version_from_event
from devmemory.storage.versions import VersionRepository
from tests.conftest import TmpGitRepo

runner = CliRunner()


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


def test_is_redacted_detection() -> None:
    """Verify detection of various redaction tokens and sentinels."""
    assert is_redacted("[REDACTED]") is True
    assert is_redacted("<REDACTED>") is True
    assert is_redacted("REDACTED") is True
    assert is_redacted("***") is True
    assert is_redacted("[MASKED]") is True
    assert is_redacted("<MASKED>") is True
    assert is_redacted("[REMOVED]") is True
    assert is_redacted("[CONFIDENTIAL]") is True
    assert is_redacted("  [redacted]  ") is True

    # Real user prompts must not be treated as redacted
    assert is_redacted("Fix the auth token expiration issue") is False
    assert is_redacted("Implement billing retry loop") is False
    assert is_redacted("") is False
    assert is_redacted(None) is False

    assert is_missing_or_redacted(None) is True
    assert is_missing_or_redacted("") is True
    assert is_missing_or_redacted("   ") is True
    assert is_missing_or_redacted("[REDACTED]") is True
    assert is_missing_or_redacted("Valid user prompt") is False


def test_compute_context_status() -> None:
    """Verify context status computation for COMPLETE, PARTIAL, and MISSING cases."""
    # No checkpoint -> MISSING
    assert compute_context_status(has_checkpoint=False) == ContextStatus.MISSING
    assert compute_context_status(has_checkpoint=False, intent="anything") == ContextStatus.MISSING

    # Checkpoint present with clear prompt -> COMPLETE
    assert compute_context_status(has_checkpoint=True, intent="Refactor storage") == ContextStatus.COMPLETE

    # Checkpoint present but prompt is None or redacted -> PARTIAL
    assert compute_context_status(has_checkpoint=True, intent=None) == ContextStatus.PARTIAL
    assert compute_context_status(has_checkpoint=True, intent="[REDACTED]") == ContextStatus.PARTIAL
    assert compute_context_status(has_checkpoint=True, intent="", redacted_fields=["intent"]) == ContextStatus.PARTIAL
    assert compute_context_status(has_checkpoint=True, intent="Valid", redacted_fields=["messages"]) == ContextStatus.PARTIAL


def test_databricks_export_excludes_all_sensitive_fields() -> None:
    """Requirement 1: Raw prompt, intent, transcript must NEVER cross boundary to Databricks."""
    # Ensure sensitive fields are in SENSITIVE_FIELDS blocklist
    for field in ("prompt", "transcript", "intent", "raw_context", "messages"):
        assert field in SENSITIVE_FIELDS

    # Ensure none of SENSITIVE_FIELDS are in Databricks _VERSION_FIELDS
    leaks = [f for f in SENSITIVE_FIELDS if f in _VERSION_FIELDS]
    assert leaks == [], f"Found sensitive fields in Databricks export allowlist: {leaks}"

    # Ensure context_status IS in Databricks _VERSION_FIELDS
    assert "context_status" in _VERSION_FIELDS

    # Verify a version with sensitive data in intent produces a clean record
    v = DevelopmentVersion(
        version_id="v1",
        version_number=1,
        project_id="demo",
        intent="Super secret user prompt that must not leak to databricks",
        context_status=ContextStatus.COMPLETE,
        git_commit="c" * 40,
        created_at=datetime.now(UTC),
    )

    record = version_record(v)
    assert "intent" not in record
    assert "prompt" not in record
    assert "transcript" not in record
    assert record["context_status"] == "COMPLETE"

    event = outbox_event(v)
    blob = json.dumps(event)
    for forbidden in ("prompt.txt", "transcript", "diff", "intent"):
        assert forbidden not in blob


def test_redacted_checkpoint_ingestion(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    """Requirement 2: DevMemory works safely when Entire checkpoint fields are redacted."""
    # Commit a file
    git_repo.write("auth/login.py", "def login(): pass\n")
    sha = git_repo.commit("feat: add login handler")

    # Create a checkpoint reference with redacted intent
    cp = CheckpointReference(
        checkpoint_id="cp-redacted-01",
        commit_sha=sha,
        intent="[REDACTED]",
        context_status=ContextStatus.PARTIAL,
        redacted_fields=["intent"],
        association_method=AssociationMethod.TRAILER,
        association_confidence=1.0,
    )

    # Ingest event
    commit_info = project.git.commit(sha)
    assert commit_info is not None

    event = DevelopmentEvent(
        project_id="demo",
        occurred_at=datetime.now(UTC),
        intent=None,
        context_status=ContextStatus.PARTIAL,
        redacted_fields=["intent"],
        commit=commit_info,
        changed_files=[
            ChangedFile(path="auth/login.py", change_type=ChangeType.ADDED, additions=1, deletions=0)
        ],
        checkpoint=cp,
        status=VersionStatus.SUCCESS,
    )

    version = create_version_from_event(project, event)

    # Verify version properties:
    # 1. intent is None (not string '[REDACTED]')
    assert version.intent is None
    # 2. context_status is PARTIAL
    assert version.context_status == ContextStatus.PARTIAL
    # 3. redacted_fields contains 'intent'
    assert "intent" in version.redacted_fields
    # 4. git and file data is preserved
    assert version.files_changed == 1
    assert version.lines_added == 1

    # Verify retrieval from repository
    repo = VersionRepository(project.db)
    fetched = repo.get(version.version_id)
    assert fetched is not None
    assert fetched.intent is None
    assert fetched.context_status == ContextStatus.PARTIAL
    assert "intent" in fetched.redacted_fields


def test_missing_checkpoint_handling(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    """Requirement 3: Version created with no checkpoint context (offline / local only)."""
    git_repo.write("core/engine.py", "def run(): return 42\n")
    sha = git_repo.commit("feat: add core engine")

    commit_info = project.git.commit(sha)
    assert commit_info is not None

    # Event with no checkpoint
    event = DevelopmentEvent(
        project_id="demo",
        occurred_at=datetime.now(UTC),
        intent=None,
        context_status=ContextStatus.MISSING,
        redacted_fields=["checkpoint", "intent"],
        commit=commit_info,
        changed_files=[
            ChangedFile(path="core/engine.py", change_type=ChangeType.ADDED, additions=1, deletions=0)
        ],
        checkpoint=None,
        status=VersionStatus.SUCCESS,
        tests=TestOutcome(command="pytest", total=5, passed=5, failed=0),
    )

    version = create_version_from_event(project, event)
    assert version.context_status == ContextStatus.MISSING
    assert version.primary_checkpoint is None
    assert version.tests is not None and version.tests.all_passed

    # Local memory retrieval still works
    attempts = previous_attempts(
        project,
        MemoryQuery(files=["core/engine.py"], include_successes=True),
    )
    assert len(attempts) >= 1
    assert attempts[0].version_id == version.version_id
    assert attempts[0].context_status == "MISSING"


def test_no_false_certainty_in_rules_analysis() -> None:
    """Requirement 4: No false certainty - never invent developer intent when missing or redacted."""
    provider = RulesProvider()

    # Case A: Partial context (intent redacted)
    input_partial = AnalysisInput(
        version_id="v1",
        intent=None,
        context_status="PARTIAL",
        analysis_confidence="LIMITED",
        redacted_fields=["intent"],
        feature=None,
        agent=None,
        model=None,
        status="SUCCESS",
        is_adverse=False,
        files_changed=3,
        lines_added=40,
        lines_removed=10,
    )

    analysis_partial = provider.analyze(input_partial)
    # Must not fabricate an intent statement
    assert "prompt context unavailable/redacted" in analysis_partial.summary
    assert any("unavailable or redacted" in w for w in analysis_partial.warnings)
    assert analysis_partial.reasoning is not None
    assert "code evidence only" in analysis_partial.reasoning

    # Case B: Missing context (no checkpoint)
    input_missing = AnalysisInput(
        version_id="v2",
        intent=None,
        context_status="MISSING",
        analysis_confidence="CODE_EVIDENCE_ONLY",
        redacted_fields=["checkpoint", "intent"],
        feature=None,
        agent=None,
        model=None,
        status="SUCCESS",
        is_adverse=False,
        files_changed=1,
        lines_added=5,
        lines_removed=0,
    )

    analysis_missing = provider.analyze(input_missing)
    assert "no checkpoint context" in analysis_missing.summary
    assert any("unavailable or redacted" in w for w in analysis_missing.warnings)


def test_mcp_get_checkpoint_context_metadata(project: ProjectContext) -> None:
    """Verify MCP get_checkpoint returns context status and redacted fields."""
    cp = CheckpointReference(
        checkpoint_id="cp-mcp-test",
        intent=None,
        context_status=ContextStatus.PARTIAL,
        redacted_fields=["intent"],
        association_method=AssociationMethod.MANUAL,
        association_confidence=0.9,
    )
    # Save to db
    from devmemory.storage.repositories import CheckpointRepository

    CheckpointRepository(project.db).upsert("demo", cp)

    # Retrieve through taskloop engine / MCP
    data = get_checkpoint(project, "cp-mcp-test")
    assert data["available"] is True
    assert data["context_status"] == "PARTIAL"
    assert "intent" in data["redacted_fields"]


def test_privacy_audit_cli(project: ProjectContext) -> None:
    """Verify devmemory privacy-audit runs and reports compliance."""
    result = runner.invoke(app, ["privacy-audit", "--repo", str(project.paths.repo_root)])
    assert result.exit_code == 0
    assert "Privacy Boundary Audit" in result.output
    assert "PASS" in result.output

    # JSON mode
    json_result = runner.invoke(app, ["privacy-audit", "--repo", str(project.paths.repo_root), "--json"])
    assert json_result.exit_code == 0
    parsed = json.loads(json_result.output)
    assert parsed["all_passed"] is True
    assert len(parsed["checks"]) >= 4
    assert parsed["project_id"] == "demo"
