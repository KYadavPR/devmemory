"""Phase 9: project snapshots + safe restore."""

from __future__ import annotations

import tarfile

import pytest

from devmemory.adapters.git import GitAdapter
from devmemory.domain.enums import VersionStatus
from devmemory.domain.errors import RestoreSafetyError
from devmemory.pipeline.checkpoint import CheckpointRequest, run_checkpoint
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from devmemory.services.restore import restore_preview, restore_version
from devmemory.storage.artifacts import ArtifactStore
from tests.conftest import TmpGitRepo


@pytest.fixture
def project(git_repo: TmpGitRepo) -> ProjectContext:
    git_repo.write("app.py", "print('v0')\n")
    git_repo.write("src/lib.py", "VALUE = 1\n")
    git_repo.commit("chore: init")
    init_project(git_repo.path, name="Demo", project_id="demo")
    git_repo.commit("chore: devmemory")
    return ProjectContext.load(git_repo.path)


# --- artifacts ------------------------------------------------------------------


def test_snapshot_contains_committed_tree_only(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    git_repo.write("app.py", "print('v1')\n")
    git_repo.commit("feat: change")
    git_repo.write("app.py", "print('uncommitted')\n")  # working-tree noise

    git = GitAdapter(git_repo.path)
    store = ArtifactStore(project.paths.artifacts_dir, git)
    artifact = store.create_snapshot(version_id="v1", commit_sha=git.head_sha() or "")

    archive = git_repo.path / artifact.path
    assert archive.is_file()
    assert artifact.sha256
    with tarfile.open(archive, "r:gz") as tf:
        names = set(tf.getnames())
        assert "app.py" in names
        assert "src/lib.py" in names
        assert not any(n == ".git" or n.startswith(".git/") for n in names)
        assert not any(n == ".devmemory" or n.startswith(".devmemory/") for n in names)
        assert tf.extractfile("app.py").read() == b"print('v1')\n"  # committed, not working tree

    # deterministic hash for the same commit
    again = store.create_snapshot(version_id="v1", commit_sha=git.head_sha() or "")
    assert again.sha256 == artifact.sha256
    project.close()


def test_pipeline_creates_artifact(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    git_repo.write("app.py", "print('v1')\n")
    git_repo.commit("feat: change")
    result = run_checkpoint(project, CheckpointRequest(allow_no_entire=True))
    assert len(result.version.artifacts) == 1
    a = result.version.artifacts[0]
    assert (git_repo.path / a.path).is_file()

    reloaded = ProtoReload(project).version("v1")
    assert reloaded.artifacts and reloaded.artifacts[0].sha256 == a.sha256
    project.close()


class ProtoReload:
    def __init__(self, ctx: ProjectContext) -> None:
        self._ctx = ctx

    def version(self, ref: str):
        from devmemory.services.versions import get_version

        return get_version(self._ctx, ref)


# --- restore -------------------------------------------------------------------


def _make_two_versions(project: ProjectContext, repo: TmpGitRepo) -> None:
    repo.write("app.py", "VERSION = 1\n")
    repo.commit("feat: v1")
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, status=VersionStatus.SUCCESS))
    repo.write("app.py", "VERSION = 2\n")
    repo.commit("feat: v2")
    run_checkpoint(project, CheckpointRequest(allow_no_entire=True, status=VersionStatus.SUCCESS))


def test_restore_preview(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _make_two_versions(project, git_repo)
    preview = restore_preview(project, "v1")
    assert preview.version_id == "v1"
    assert preview.already_there is False
    assert preview.working_tree_clean is True
    assert preview.safety_tag.startswith("devmemory/safety/")
    project.close()


def test_restore_refuses_dirty_tree(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _make_two_versions(project, git_repo)
    git_repo.write("app.py", "VERSION = 2  # local edit\n")
    with pytest.raises(RestoreSafetyError):
        restore_version(project, "v1")
    project.close()


def test_restore_detached_creates_safety_tag(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _make_two_versions(project, git_repo)
    v2_sha = GitAdapter(git_repo.path).head_sha()

    result = restore_version(project, "v1")
    git = GitAdapter(git_repo.path)
    assert git.current_branch() is None  # detached
    assert (git_repo.path / "app.py").read_text() == "VERSION = 1\n"
    assert result.safety_tag in git.list_refs("refs/tags/")[0][1] or any(
        result.safety_tag in name for _, name in git.list_refs("refs/tags/")
    )
    # the safety tag points at the old HEAD
    assert git.resolve(result.safety_tag) == v2_sha

    events = project.db.query("SELECT type FROM events WHERE type = 'restore'")
    assert len(events) == 1
    project.close()


def test_restore_allow_dirty_keeps_stash(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _make_two_versions(project, git_repo)
    git_repo.write("app.py", "VERSION = 2  # wip\n")
    result = restore_version(project, "v1", allow_dirty=True)
    assert result.stash_ref
    git = GitAdapter(git_repo.path)
    assert git.resolve(result.stash_ref)  # a real object
    project.close()


def test_restore_already_there_is_noop(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    _make_two_versions(project, git_repo)
    result = restore_version(project, "v2")
    assert "nothing to do" in result.message.lower()
    project.close()


def test_api_restore_gated(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    from fastapi.testclient import TestClient

    from devmemory.api.app import create_app

    _make_two_versions(project, git_repo)
    project.close()

    with TestClient(create_app(git_repo.path)) as c:
        assert c.get("/api/versions/v1/restore/preview").status_code == 200
        assert c.post("/api/versions/v1/restore").status_code == 403

    with TestClient(create_app(git_repo.path, enable_restore=True)) as c:
        r = c.post("/api/versions/v1/restore")
        assert r.status_code == 200
        assert r.json()["target_commit"]
