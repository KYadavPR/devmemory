"""``devmemory checkpoint`` - the version-creation pipeline.

Each stage is recorded in a :class:`RunLog` so a failure is always traceable to a
stage and an integration. Cloud/optional steps (snapshot, Databricks) never fail
the run - local history is the source of truth.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from devmemory.domain.enums import VersionStatus
from devmemory.domain.errors import (
    CheckpointNotFoundError,
    DevMemoryError,
    GitRepositoryNotFoundError,
)
from devmemory.domain.models import (
    CheckpointReference,
    DevelopmentEvent,
    DevelopmentVersion,
    Metric,
    TestOutcome,
)
from devmemory.environment import collect_environment
from devmemory.logging import get_logger
from devmemory.pipeline.feature_detect import detect_feature
from devmemory.pipeline.runlog import RunLog, StageRecord
from devmemory.pipeline.status_rules import derive_status
from devmemory.services.context import ProjectContext
from devmemory.services.versions import create_version_from_event
from devmemory.storage.versions import VersionRepository

_log = get_logger(__name__)


class CheckpointRequest(BaseModel):
    intent: str | None = None
    feature: str | None = None
    agent: str | None = None
    status: VersionStatus | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    tests_skipped: int | None = None
    metrics: list[Metric] = []
    errors: list[str] = []
    allow_no_entire: bool = False
    force: bool = False


class CheckpointResult(BaseModel):
    version: DevelopmentVersion
    run_log: RunLog
    created: bool
    warnings: list[str] = []


def run_checkpoint(ctx: ProjectContext, request: CheckpointRequest) -> CheckpointResult:
    run = RunLog()
    warnings: list[str] = []

    try:
        with run.stage("verify_repository") as st:
            if not ctx.git.is_repository():
                raise GitRepositoryNotFoundError
            if not ctx.git.has_commits():
                raise DevMemoryError(
                    "The repository has no commits yet.",
                    hint="Commit your development change, then run `devmemory checkpoint`.",
                )
            st.data["repo_root"] = str(ctx.paths.repo_root)

        with run.stage("resolve_commit") as st:
            commit = ctx.git.commit("HEAD")
            parent = commit.parent
            branch = ctx.git.current_branch()
            st.data |= {"commit": commit.sha, "parent": parent, "branch": branch}

        with run.stage("check_working_tree") as st:
            state = ctx.git.working_tree_state()
            if state.has_uncommitted_changes:
                msg = (
                    f"{len(state.staged) + len(state.unstaged)} uncommitted change(s); "
                    "the version records the committed state only."
                )
                warnings.append(msg)
                st.status = "degraded"
                st.detail = msg

        with run.stage("check_idempotency") as st:
            existing = VersionRepository(ctx.db).find_by_commit(ctx.config.project_id, commit.sha)
            if existing is not None and not request.force:
                st.detail = f"{existing.version_id} already records this commit"
                run.version_id = existing.version_id
                run.finish(outcome="success")
                run.write(ctx.paths.runs_dir)
                return CheckpointResult(
                    version=existing, run_log=run, created=False, warnings=warnings
                )
            st.data["existing"] = existing.version_id if existing else None

        with run.stage("resolve_entire_checkpoint") as st:
            checkpoint = _resolve_checkpoint(ctx, commit.sha, commit.committed_at, branch, st)
            if checkpoint is None and not request.allow_no_entire:
                raise CheckpointNotFoundError(
                    "No Entire checkpoint could be associated with this commit.",
                    hint=(
                        "DevMemory versions are checkpoint-aware. Ensure Entire is enabled and "
                        "the AI session was captured, or pass --allow-no-entire."
                    ),
                )
            if checkpoint is None:
                warnings.append("recorded without Entire checkpoint context (--allow-no-entire)")
                st.status = "degraded"
            elif checkpoint.is_uncertain:
                warnings.append(
                    f"checkpoint association is uncertain "
                    f"(confidence {checkpoint.association_confidence:.2f})"
                )
                st.status = "degraded"

        with run.stage("collect_changes") as st:
            changed_files = ctx.git.changed_files(parent, commit.sha)
            st.data |= {
                "files": len(changed_files),
                "additions": sum(f.additions for f in changed_files),
                "deletions": sum(f.deletions for f in changed_files),
            }

        with run.stage("collect_environment"):
            environment = collect_environment(ctx.paths.repo_root)

        with run.stage("detect_feature") as st:
            intent = request.intent or (checkpoint.intent if checkpoint else None)
            feature = detect_feature(
                explicit=request.feature,
                intent=intent,
                commit_subject=commit.subject,
            )
            st.data["feature"] = feature[0] if feature else None

        with run.stage("collect_tests") as st:
            tests = _tests_from_request(request)
            if tests is not None:
                st.data |= {"passed": tests.passed, "failed": tests.failed}
            else:
                st.status = "skipped"

        with run.stage("determine_status") as st:
            status = derive_status(
                explicit=request.status,
                tests=tests,
                errors=request.errors,
                has_changes=bool(changed_files),
            )
            st.data["status"] = status.value

        with run.stage("build_event"):
            event = DevelopmentEvent(
                project_id=ctx.config.project_id,
                occurred_at=datetime.now(UTC),
                run_id=run.run_id,
                intent=intent,
                agent=request.agent or (checkpoint.agent if checkpoint else None),
                model=checkpoint.model if checkpoint else None,
                feature=feature[0] if feature else None,
                feature_derived_from=feature[1] if feature else None,
                commit=commit,
                parent_commit=parent,
                branch=branch,
                changed_files=changed_files,
                checkpoint=checkpoint,
                status=status,
                tests=tests,
                metrics=request.metrics,
                errors=request.errors,
                environment=environment,
            )

        with run.stage("persist_version") as st:
            version = create_version_from_event(ctx, event, force=request.force)
            run.version_id = version.version_id
            run.project_state_changed = True
            st.data["version"] = version.version_id

        run.finish(outcome="success")
    except DevMemoryError as exc:
        run.finish(outcome="error", error=exc.message)
        run.write(ctx.paths.runs_dir)
        raise
    except Exception as exc:
        run.finish(outcome="error", error=f"{type(exc).__name__}: {exc}")
        run.write(ctx.paths.runs_dir)
        raise DevMemoryError(f"checkpoint failed during the pipeline: {exc}") from exc

    run.write(ctx.paths.runs_dir)
    _log.info(
        "checkpoint.done",
        version=version.version_id,
        status=version.status.value,
        run_id=run.run_id,
    )
    return CheckpointResult(version=version, run_log=run, created=True, warnings=warnings)


# --- stage helpers -----------------------------------------------------------------


def _resolve_checkpoint(
    ctx: ProjectContext,
    commit_sha: str,
    committed_at: datetime | None,
    branch: str | None,
    stage: StageRecord,
) -> CheckpointReference | None:
    if not ctx.entire.is_installed():
        stage.detail = "Entire CLI not installed"
        return None
    ref = ctx.entire.resolve_for_commit(commit_sha, committed_at=committed_at, branch=branch)
    if ref is not None:
        stage.data = {
            "checkpoint": ref.checkpoint_id,
            "method": ref.association_method.value,
            "confidence": ref.association_confidence,
        }
    return ref


def _tests_from_request(request: CheckpointRequest) -> TestOutcome | None:
    if request.tests_passed is None and request.tests_failed is None:
        return None
    passed = request.tests_passed or 0
    failed = request.tests_failed or 0
    skipped = request.tests_skipped or 0
    return TestOutcome(
        command="(manual)",
        total=passed + failed + skipped,
        passed=passed,
        failed=failed,
        skipped=skipped,
        exit_code=0 if failed == 0 else 1,
    )


__all__ = ["CheckpointRequest", "CheckpointResult", "run_checkpoint"]
