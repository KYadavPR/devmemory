"""Phase 4: the `devmemory checkpoint` pipeline."""

from __future__ import annotations

import json

import pytest

from devmemory.domain.enums import AssociationMethod, VersionStatus
from devmemory.domain.errors import CheckpointNotFoundError
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.pipeline.feature_detect import detect_feature
from devmemory.pipeline.status_rules import derive_status
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project, project_status
from tests.conftest import TmpGitRepo


@pytest.fixture
def project(git_repo: TmpGitRepo) -> ProjectContext:
    git_repo.write("app.py", "print('v0')\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    git_repo.commit("chore: enable devmemory")
    return ProjectContext.load(git_repo.path)


# --- feature detection / status rules ---------------------------------------------


@pytest.mark.parametrize(
    ("explicit", "intent", "subject", "expected"),
    [
        ("Payments", None, None, ("Payments", "cli")),
        (None, "feat(auth): add refresh tokens", None, ("Auth", "intent")),
        (None, None, "fix(image-classification): tune lr", ("Image Classification", "commit")),
        (None, "shorten the JWT expiry window", None, ("Authentication", "intent")),
        (None, "misc cleanup", "chore: tidy", None),
    ],
)
def test_detect_feature(explicit, intent, subject, expected) -> None:
    assert detect_feature(explicit=explicit, intent=intent, commit_subject=subject) == expected


def test_derive_status() -> None:
    from devmemory.domain.models import TestOutcome

    assert derive_status(explicit=VersionStatus.REGRESSION, tests=None, errors=[]) is (
        VersionStatus.REGRESSION
    )
    assert derive_status(explicit=None, tests=None, errors=["boom"]) is VersionStatus.ERROR
    ok = TestOutcome(command="pytest", total=10, passed=10)
    assert derive_status(explicit=None, tests=ok, errors=[]) is VersionStatus.SUCCESS
    mixed = TestOutcome(command="pytest", total=10, passed=7, failed=3)
    assert derive_status(explicit=None, tests=mixed, errors=[]) is VersionStatus.PARTIAL_SUCCESS
    assert derive_status(explicit=None, tests=None, errors=[]) is VersionStatus.NEEDS_REVIEW


# --- pipeline -------------------------------------------------------------------


def test_checkpoint_requires_entire_by_default(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    git_repo.write("app.py", "print('v1')\n")
    git_repo.commit("feat: change")
    with pytest.raises(CheckpointNotFoundError):
        run_checkpoint(project, CheckpointRequest())
    project.close()


def test_checkpoint_allow_no_entire(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("auth.py", "def login(): ...\n")
    git_repo.commit("feat: add login")

    result = run_checkpoint(
        project,
        CheckpointRequest(
            allow_no_entire=True,
            intent="Add JWT authentication",
            tests_passed=12,
            tests_failed=0,
            metrics=[],
        ),
    )
    assert result.created is True
    v = result.version
    assert v.version_id == "v1"
    assert v.status is VersionStatus.SUCCESS
    assert v.intent == "Add JWT authentication"
    assert v.feature_id == "demo:authentication"
    assert v.entire_association_method is AssociationMethod.NONE
    assert "without Entire checkpoint context" in " ".join(result.warnings)

    # run log written
    logs = list(project.paths.runs_dir.glob("*.json"))
    assert len(logs) == 1
    log = json.loads(logs[0].read_text())
    assert log["outcome"] == "success"
    assert log["project_state_changed"] is True
    assert [s["name"] for s in log["stages"]][:3] == [
        "verify_repository",
        "resolve_commit",
        "check_working_tree",
    ]
    project.close()


def test_checkpoint_resolves_real_trailer(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    cp = "cp778899aabb"
    git_repo.write("model.py", "lr = 0.1\n")
    sha = git_repo.commit("feat: model", trailers={"Entire-Checkpoint": cp})
    git_repo.make_entire_checkpoint(cp, intent="Improve accuracy", commit_sha=sha)

    result = run_checkpoint(project, CheckpointRequest())
    v = result.version
    assert v.primary_checkpoint is not None
    assert v.primary_checkpoint.checkpoint_id == cp
    assert v.entire_association_method is AssociationMethod.TRAILER
    assert v.intent == "Improve accuracy"
    assert v.agent == "Claude Code"
    project.close()


def test_checkpoint_idempotent(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("a.py", "x = 1\n")
    git_repo.commit("feat: a")

    first = run_checkpoint(project, CheckpointRequest(allow_no_entire=True))
    assert first.created is True

    again = run_checkpoint(project, CheckpointRequest(allow_no_entire=True))
    assert again.created is False
    assert again.version.version_id == first.version.version_id

    forced = run_checkpoint(project, CheckpointRequest(allow_no_entire=True, force=True))
    assert forced.created is True
    assert forced.version.version_number == 1
    project.close()


def test_checkpoint_warns_on_dirty_tree(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("a.py", "x = 1\n")
    git_repo.commit("feat: a")
    git_repo.write("a.py", "x = 2  # uncommitted\n")

    result = run_checkpoint(project, CheckpointRequest(allow_no_entire=True))
    assert any("uncommitted" in w for w in result.warnings)
    project.close()


def test_status_reflects_versions(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("a.py", "x = 1\n")
    git_repo.commit("feat: a")
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, status=VersionStatus.SUCCESS))

    report = project_status(project)
    assert report.version_count == 1
    assert report.latest_version_id == "v1"
    assert report.latest_status == "SUCCESS"
    assert report.head_has_version is True
    project.close()
