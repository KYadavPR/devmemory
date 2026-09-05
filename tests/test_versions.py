"""Phase 3: DevelopmentEvent normalization + version registry + persistence."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from devmemory.adapters.git import GitAdapter
from devmemory.domain.enums import AssociationMethod, MetricDirection, VersionStatus
from devmemory.domain.models import (
    CheckpointReference,
    DevelopmentEvent,
    Metric,
    TestOutcome,
)
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from devmemory.services.versions import (
    VersionExistsError,
    VersionNotFoundError,
    create_version_from_event,
    get_version,
    list_versions,
    search_versions,
    version_diff,
)
from devmemory.storage.repositories import FeatureRepository
from tests.conftest import TmpGitRepo


@pytest.fixture
def initialized(git_repo: TmpGitRepo) -> ProjectContext:
    git_repo.write("model.py", "lr = 0.001\n")
    git_repo.write("README.md", "# demo\n")
    git_repo.commit("feat: baseline")
    init_project(git_repo.path, name="VisionAI", project_id="visionai")
    git_repo.commit("chore: enable devmemory")  # commit config.json + .gitignore
    return ProjectContext.load(git_repo.path)


def _event(
    ctx: ProjectContext,
    repo: TmpGitRepo,
    *,
    rev: str = "HEAD",
    intent: str | None = None,
    feature: str | None = None,
    checkpoint: CheckpointReference | None = None,
    metrics: list[Metric] | None = None,
    tests: TestOutcome | None = None,
    status: VersionStatus | None = None,
) -> DevelopmentEvent:
    git = GitAdapter(repo.path)
    commit = git.commit(rev)
    return DevelopmentEvent(
        project_id=ctx.config.project_id,
        occurred_at=datetime.now(UTC),
        intent=intent,
        feature=feature,
        commit=commit,
        parent_commit=commit.parent,
        branch=git.current_branch(),
        changed_files=git.changed_files(commit.parent, commit.sha),
        checkpoint=checkpoint,
        metrics=metrics or [],
        tests=tests,
        status=status,
    )


def test_migration_0002_creates_all_tables(initialized: ProjectContext) -> None:
    tables = {
        r["name"]
        for r in initialized.db.connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table')"
        )
    }
    assert {
        "versions",
        "changed_files",
        "entire_checkpoints",
        "version_checkpoints",
        "features",
        "tests",
        "metrics",
        "regressions",
        "analysis",
        "artifacts",
        "doc_flags",
        "events",
    } <= tables
    # FTS virtual table
    assert (
        initialized.db.connection.execute("SELECT count(*) FROM version_search").fetchone()[0] == 0
    )
    initialized.close()


def test_create_and_hydrate_roundtrip(initialized: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("model.py", "lr = 0.0005\nscheduler = True\n")
    git_repo.commit("feat: tune lr", trailers={"Entire-Checkpoint": "cp0001aaaa11"})

    checkpoint = CheckpointReference(
        checkpoint_id="cp0001aaaa11",
        commit_sha=git_repo.rev(),
        intent="Improve classification accuracy",
        agent="Claude Code",
        model="claude-sonnet-5",
        association_method=AssociationMethod.TRAILER,
        association_confidence=1.0,
    )
    event = _event(
        initialized,
        git_repo,
        intent="Improve classification accuracy",
        feature="Image Classification",
        checkpoint=checkpoint,
        metrics=[
            Metric(name="accuracy", before=89.2, after=93.4, unit="%"),
            Metric(
                name="latency_ms",
                before=420,
                after=310,
                unit="ms",
                direction=MetricDirection.LOWER_IS_BETTER,
            ),
        ],
        tests=TestOutcome(command="pytest", total=148, passed=143, failed=5),
        status=VersionStatus.SUCCESS,
    )

    version = create_version_from_event(initialized, event)
    assert version.version_id == "v1"
    assert version.version_number == 1

    fetched = get_version(initialized, "v1")
    assert fetched.intent == "Improve classification accuracy"
    assert fetched.agent == "Claude Code"
    assert fetched.status is VersionStatus.SUCCESS
    assert fetched.files_changed == 1
    assert fetched.lines_added == 2
    assert fetched.primary_checkpoint is not None
    assert fetched.primary_checkpoint.checkpoint_id == "cp0001aaaa11"
    assert fetched.entire_association_method is AssociationMethod.TRAILER
    assert {m.name for m in fetched.metrics} == {"accuracy", "latency_ms"}
    assert next(m for m in fetched.metrics if m.name == "latency_ms").is_improvement
    assert fetched.tests is not None
    assert fetched.tests.passed == 143
    assert fetched.feature_id == "visionai:image-classification"

    feature = FeatureRepository(initialized.db).get_by_name("visionai", "Image Classification")
    assert feature is not None
    initialized.close()


def test_idempotent_on_same_commit(initialized: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("a.py", "x = 1\n")
    git_repo.commit("feat: a")
    event = _event(initialized, git_repo)

    create_version_from_event(initialized, event)
    with pytest.raises(VersionExistsError):
        create_version_from_event(initialized, event)

    forced = create_version_from_event(initialized, event, force=True)
    assert forced.version_number == 1  # force re-records the same version in place
    assert list_versions(initialized) == [forced]
    initialized.close()


def test_version_numbering_increments(initialized: ProjectContext, git_repo: TmpGitRepo) -> None:
    for i in range(3):
        git_repo.write("a.py", f"x = {i}\n")
        git_repo.commit(f"change {i}")
        create_version_from_event(initialized, _event(initialized, git_repo))
    versions = list_versions(initialized)
    assert [v.version_id for v in versions] == ["v1", "v2", "v3"]
    initialized.close()


def test_search_finds_by_intent_and_file(initialized: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("auth.py", "def login(): ...\n")
    git_repo.commit("feat: auth")
    create_version_from_event(
        initialized,
        _event(initialized, git_repo, intent="Add JWT authentication", feature="Authentication"),
    )
    git_repo.write("model.py", "lr = 0.1\n")
    git_repo.commit("feat: model")
    create_version_from_event(
        initialized, _event(initialized, git_repo, intent="Tune the learning rate")
    )

    hits = search_versions(initialized, "authentication")
    assert [v.version_id for v in hits] == ["v1"]
    assert [v.version_id for v in search_versions(initialized, "learning rate")] == ["v2"]
    assert [v.version_id for v in search_versions(initialized, "auth.py")] == ["v1"]
    initialized.close()


def test_version_diff(initialized: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("m.py", "a = 1\n")
    git_repo.commit("v1")
    create_version_from_event(
        initialized,
        _event(initialized, git_repo, metrics=[Metric(name="accuracy", before=80, after=85)]),
    )
    git_repo.write("m.py", "a = 1\nb = 2\n")
    git_repo.commit("v2")
    create_version_from_event(
        initialized,
        _event(initialized, git_repo, metrics=[Metric(name="accuracy", before=85, after=91)]),
    )

    diff = version_diff(initialized, "v1", "v2")
    assert diff.from_version_id == "v1"
    assert diff.stat.additions == 1
    assert "b = 2" in diff.diff_text
    assert diff.metric_changes["accuracy"]["before"] == 85
    assert diff.metric_changes["accuracy"]["after"] == 91
    initialized.close()


def test_get_missing_version_raises(initialized: ProjectContext) -> None:
    with pytest.raises(VersionNotFoundError):
        get_version(initialized, "v99")
    initialized.close()
