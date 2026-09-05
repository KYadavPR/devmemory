"""``devmemory checkpoint`` - the version-creation pipeline.

Each stage is recorded in a :class:`RunLog` so a failure is always traceable to a
stage and an integration. Cloud/optional steps (snapshot, Databricks) never fail
the run - local history is the source of truth.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel

from devmemory.adapters.metrics import MetricsAdapter
from devmemory.adapters.tests import TestAdapter
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
from devmemory.pipeline.regression import RegressionThresholds, detect_regressions
from devmemory.pipeline.runlog import RunLog, StageRecord
from devmemory.pipeline.status_rules import derive_status
from devmemory.services.context import ProjectContext
from devmemory.services.databricks_sync import push_version
from devmemory.services.features import refresh_feature_status
from devmemory.services.memory import MemoryQuery, previous_attempts
from devmemory.services.versions import create_version_from_event
from devmemory.storage.artifacts import ArtifactStore
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
    run_tests: bool = True
    """Run the configured test command (unless explicit counts were given)."""
    metrics: list[Metric] = []
    metrics_file: str | None = None
    errors: list[str] = []
    snapshot: bool = True
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

        repo = VersionRepository(ctx.db)
        previous = repo.previous_relevant(
            ctx.config.project_id,
            before_number=(
                existing.version_number if existing else repo.count(ctx.config.project_id) + 1
            ),
        )

        with run.stage("collect_tests") as st:
            tests = _collect_tests(ctx, request, st)

        with run.stage("collect_metrics") as st:
            metrics = _collect_metrics(ctx, request, previous, st)

        with run.stage("check_previous_attempts") as st:
            prior = previous_attempts(
                ctx,
                MemoryQuery(
                    files=[f.path for f in changed_files],
                    feature=feature[0] if feature else None,
                    intent=intent,
                    limit=3,
                ),
            )
            for a in prior:
                if a.version_id in {v.version_id for v in [previous] if v}:
                    continue
                warnings.append(
                    f"similar prior attempt {a.version_id.upper()} [{a.status}] - "
                    f"{a.result}" + (f" ({a.recommendation})" if a.recommendation else "")
                )
            st.data["matches"] = [a.version_id for a in prior]
            if prior:
                st.status = "degraded"

        with run.stage("detect_regression") as st:
            regressions = detect_regressions(
                metrics=metrics,
                tests=tests,
                previous=previous,
                thresholds=RegressionThresholds(**ctx.config.regression.model_dump()),
            )
            for r in regressions:
                warnings.append(f"regression [{r.severity}] {r.detail}")
            st.data["count"] = len(regressions)
            if regressions:
                st.status = "degraded"

        with run.stage("determine_status") as st:
            status = derive_status(
                explicit=request.status,
                tests=tests,
                errors=request.errors,
                regressions=regressions,
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
                metrics=metrics,
                errors=request.errors,
                environment=environment,
            )

        with run.stage("persist_version") as st:
            version = create_version_from_event(
                ctx, event, force=request.force, regressions=regressions
            )
            run.version_id = version.version_id
            run.project_state_changed = True
            st.data["version"] = version.version_id

        with run.stage("refresh_feature") as st:
            if version.feature_id:
                updated = refresh_feature_status(ctx, version.feature_id)
                st.data["feature_status"] = updated.status.value if updated else None
            else:
                st.status = "skipped"

        with run.stage("publish_databricks") as st:
            try:
                sync = push_version(ctx, version)
                st.data |= {
                    "configured": sync.configured,
                    "pushed": sync.pushed,
                    "queued": sync.queued,
                }
                if not sync.configured:
                    st.status = "skipped"
                    st.detail = "queued to outbox (Databricks not configured)"
                elif sync.failed:
                    st.status = "degraded"
                    st.detail = sync.detail
            except DevMemoryError as exc:  # never fatal
                st.status = "degraded"
                st.detail = exc.message

        with run.stage("create_artifact") as st:
            if not request.snapshot or not ctx.config.artifacts.enabled:
                st.status = "skipped"
            else:
                try:
                    artifact = ArtifactStore(ctx.paths.artifacts_dir, ctx.git).create_snapshot(
                        version_id=version.version_id,
                        commit_sha=version.git_commit,
                        exclude=ctx.config.artifacts.exclude,
                    )
                    VersionRepository(ctx.db).add_artifact(artifact)
                    version.artifacts = [artifact]
                    st.data |= {"path": artifact.path, "bytes": artifact.size_bytes}
                except DevMemoryError as exc:
                    st.status = "degraded"
                    st.detail = exc.message
                    warnings.append(f"snapshot skipped: {exc.message}")

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


def _collect_tests(
    ctx: ProjectContext,
    request: CheckpointRequest,
    stage: StageRecord,
) -> TestOutcome | None:
    if request.tests_passed is not None or request.tests_failed is not None:
        passed = request.tests_passed or 0
        failed = request.tests_failed or 0
        skipped = request.tests_skipped or 0
        stage.detail = "manual counts"
        stage.data |= {"passed": passed, "failed": failed}
        return TestOutcome(
            command="(manual)",
            total=passed + failed + skipped,
            passed=passed,
            failed=failed,
            skipped=skipped,
            exit_code=0 if failed == 0 else 1,
        )

    command = ctx.config.tests.command
    if not command or not request.run_tests:
        stage.status = "skipped"
        stage.detail = "no test command configured" if not command else "--no-run-tests"
        return None

    try:
        outcome = TestAdapter(ctx.paths.repo_root).run(
            command,
            parser=ctx.config.tests.parser,
            junit_xml=ctx.config.tests.junit_xml,
            timeout=ctx.config.tests.timeout_seconds,
        )
    except DevMemoryError as exc:
        # A *collection* failure is a DevMemory problem, not a development result -
        # record the version without tests rather than aborting the run.
        stage.status = "degraded"
        stage.detail = exc.message
        return None
    stage.data |= {"passed": outcome.passed, "failed": outcome.failed, "exit": outcome.exit_code}
    return outcome


def _collect_metrics(
    ctx: ProjectContext,
    request: CheckpointRequest,
    previous: DevelopmentVersion | None,
    stage: StageRecord,
) -> list[Metric]:
    metrics = list(request.metrics)
    file = request.metrics_file or ctx.config.metrics.file
    command = ctx.config.metrics.command
    if file or command:
        try:
            collected = MetricsAdapter(ctx.paths.repo_root).collect(
                file=file,
                command=command,
                directions=ctx.config.metrics.directions,
            )
        except DevMemoryError as exc:
            stage.status = "degraded"
            stage.detail = exc.message
            collected = []
        by_name = {m.name for m in metrics}
        metrics.extend(m for m in collected if m.name not in by_name)

    # Backfill `before` from the previous version's `after` for the same metric.
    prev_after = {m.name: m.after for m in previous.metrics} if previous else {}
    for m in metrics:
        if m.before is None and m.name in prev_after:
            m.before = prev_after[m.name]

    stage.data["names"] = [m.name for m in metrics]
    if not metrics:
        stage.status = "skipped"
    return metrics


__all__ = ["CheckpointRequest", "CheckpointResult", "run_checkpoint"]
