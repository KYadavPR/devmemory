"""The state engine (§3).

Aggregates evidence from Git, Entire, tests, and optional Graph into one
:class:`NormalizedState`, computes an evidence-based :class:`TaskStatus`, and
stores a snapshot. It does **not** modify application code and does **not**
decide how code should be written.

Public surface (mirrors the MCP tools):
    create_task · get_state · refresh_state · get_checkpoint
    report_issue · resolve_issue · mark_complete
"""

from __future__ import annotations

from datetime import UTC, datetime

from devmemory.domain.enums import IssueStatus, RequirementStatus, TaskStatus, TestRunStatus
from devmemory.domain.errors import DevMemoryError
from devmemory.domain.taskloop import (
    Issue,
    NormalizedState,
    Requirement,
    StateGit,
    StateIssue,
    StateRequirement,
    StateSnapshot,
    StateTask,
    StateTests,
    Task,
    TaskTestRun,
)
from devmemory.logging import get_logger
from devmemory.services.brief import brief_context
from devmemory.services.context import ProjectContext
from devmemory.services.taskloop import collectors
from devmemory.services.taskloop.requirements import (
    apply_verdicts,
    evaluate_requirements,
    normalize_requirements,
)
from devmemory.storage.tasks import TaskRepository

_log = get_logger(__name__)


class TaskNotFoundError(DevMemoryError):
    exit_code = 3

    def __init__(self, task_id: str) -> None:
        super().__init__(f"No task {task_id!r}. Create one with `devmemory task new`.")


# --- task lifecycle --------------------------------------------------------


def create_task(
    ctx: ProjectContext,
    *,
    goal: str,
    task_id: str | None = None,
    test_command: str | None = None,
    push_policy: str = "manual",
) -> Task:
    """Normalize the goal into requirements and persist a new task (§5).

    The task's ``base_commit`` is pinned to current HEAD so later refreshes can
    measure cumulative progress.
    """
    repo = TaskRepository(ctx.db)
    tid = task_id or repo.next_task_id()
    if repo.get(tid) is not None:
        raise DevMemoryError(f"Task {tid!r} already exists.")

    head = ctx.git.head_sha() if ctx.git.is_repository() else None
    branch = ctx.git.current_branch() or "main"
    cmd = test_command or ctx.config.tests.command

    requirements = normalize_requirements(goal, ctx, brief=brief_context(ctx))
    task = Task(
        id=tid,
        goal=goal,
        status=TaskStatus.IN_PROGRESS,
        branch=branch,
        base_commit=head,
        test_command=cmd,
        push_policy=push_policy,
        requirements=requirements,
    )
    created = repo.create(task)
    _log.info("taskloop.task.created", task_id=tid, requirements=len(requirements), base=head)
    return created


def get_state(ctx: ProjectContext, task_id: str) -> NormalizedState:
    """Return the most recent stored snapshot, or a first snapshot if none exists."""
    repo = TaskRepository(ctx.db)
    if repo.get(task_id) is None:
        _raise_not_found(task_id)
    snap = repo.latest_snapshot(task_id)
    if snap is not None:
        return snap.state
    return refresh_state(ctx, task_id)


def refresh_state(ctx: ProjectContext, task_id: str) -> NormalizedState:
    """Run every collector, re-evaluate requirements, recompute status, store a
    snapshot, and return it (§11 ``refresh_state``)."""
    started = datetime.now(UTC)
    repo = TaskRepository(ctx.db)
    task = repo.get(task_id) or _raise_not_found(task_id)
    _log.info("taskloop.refresh.started", task_id=task_id)

    # 1-3. collectors (each degrades gracefully)
    git = collectors.collect_git(ctx, base_commit=task.base_commit)
    checkpoint = collectors.collect_checkpoint(ctx, head_sha=git.commit_sha)
    tests = collectors.collect_tests(
        ctx, command=task.test_command, output_dir=ctx.paths.cache_dir / "taskloop" / task_id
    )
    impact = collectors.collect_impact(
        ctx, head_sha=git.commit_sha, base_commit=task.base_commit
    )

    # persist the test run
    if tests.status is not TestRunStatus.NOT_RUN:
        repo.add_test_run(
            TaskTestRun(
                task_id=task_id,
                command=tests.command or "",
                status=tests.status,
                passed=tests.passed,
                failed=tests.failed,
                skipped=tests.skipped,
                exit_code=tests.exit_code,
                output_path=tests.output_path,
            )
        )

    # link the current commit to the task
    if git.commit_sha:
        repo.link_commit(task_id, git.commit_sha)

    # 5. re-evaluate requirements (skip if the working tree is dirty - uncommitted
    #    work is not evidence yet; §13 commits before refresh)
    requirements = task.requirements
    if git.available and git.working_tree_clean and git.commit_sha:
        checkpoint_ref = None
        if checkpoint.last_committed_id:
            ref = ctx.entire.get_checkpoint(checkpoint.last_committed_id)
            checkpoint_ref = ref.intent if ref else None
        verdicts = evaluate_requirements(
            requirements,
            ctx=ctx,
            git=git,
            tests=tests,
            checkpoint_intent=checkpoint_ref,
            base_commit=task.base_commit,
        )
        requirements = apply_verdicts(requirements, verdicts, by="llm-or-rules")
        for req in requirements:
            repo.update_requirement(task_id, req)

    # 6. refresh engine-owned unresolved items (test failures)
    repo.resolve_issues_by_kind(task_id, "test")
    if tests.status in (TestRunStatus.FAILED, TestRunStatus.ERROR):
        if tests.status is TestRunStatus.ERROR:
            detail = "Test command could not run"
        elif tests.failed == 0 and tests.passed == 0:
            detail = f"Tests did not complete (exit {tests.exit_code})"
        else:
            detail = f"{tests.failed} test(s) failing, {tests.passed} passing"
        repo.add_issue(
            Issue(
                task_id=task_id,
                kind="test",
                blocking=False,
                description=detail + (f" - see {tests.output_path}" if tests.output_path else ""),
            )
        )
    open_issues = repo.open_issues(task_id)

    # 7. compute overall status
    overall, findings, focus = _compute_status(
        task=task, git=git, tests=tests, requirements=requirements, open_issues=open_issues
    )

    state = NormalizedState(
        task=StateTask(id=task.id, goal=task.goal, status=overall),
        requirements=[
            StateRequirement(id=r.id, description=r.description, status=r.status, reason=r.reason)
            for r in requirements
        ],
        checkpoint=checkpoint,
        git=git,
        tests=tests,
        impact=impact,
        unresolved=[
            StateIssue(id=i.id, description=i.description, kind=i.kind, blocking=i.blocking)
            for i in open_issues
        ],
        findings=findings,
        recommended_focus=focus,
        overall_status=overall,
        refreshed_at=started,
    )

    # 8. store the snapshot; keep the task row's status in sync
    snap = repo.append_snapshot(state)
    state.snapshot_id = snap.id
    repo.set_status(task_id, overall)

    _log.info(
        "taskloop.refresh.done",
        task_id=task_id,
        status=overall.value,
        snapshot=snap.id,
        duration_s=round((datetime.now(UTC) - started).total_seconds(), 2),
    )
    return state


def get_checkpoint(ctx: ProjectContext, checkpoint_id: str) -> dict[str, object]:
    """Compact, useful metadata for one checkpoint via Entire (§11 ``get_checkpoint``).

    Never a full transcript by default.
    """
    ref = ctx.entire.get_checkpoint(checkpoint_id)
    if ref is None:
        return {"checkpoint_id": checkpoint_id, "available": False, "reason": "not found in Entire"}
    return {
        "checkpoint_id": ref.checkpoint_id,
        "available": True,
        "intent": ref.intent,
        "agent": ref.agent,
        "model": ref.model,
        "commit_sha": ref.commit_sha,
        "created_at": ref.created_at.isoformat() if ref.created_at else None,
        "association": ref.association_method.value,
        "sessions": [s.session_id for s in ref.sessions if s.session_id],
        "tokens_total": ref.tokens.total or None,
    }


def report_issue(
    ctx: ProjectContext, *, task_id: str, description: str, blocking: bool = False
) -> Issue:
    """Persist an unresolved item raised by the agent (§11 ``report_issue``)."""
    repo = TaskRepository(ctx.db)
    if repo.get(task_id) is None:
        _raise_not_found(task_id)
    issue = repo.add_issue(
        Issue(task_id=task_id, description=description.strip(), kind="agent", blocking=blocking)
    )
    _log.info("taskloop.issue.reported", task_id=task_id, issue_id=issue.id, blocking=blocking)
    return issue


def resolve_issue(ctx: ProjectContext, *, issue_id: int) -> bool:
    ok = TaskRepository(ctx.db).resolve_issue(issue_id)
    _log.info("taskloop.issue.resolved", issue_id=issue_id, ok=ok)
    return ok


def set_requirement_status(
    ctx: ProjectContext,
    *,
    task_id: str,
    requirement_id: str,
    status: RequirementStatus,
    note: str = "",
) -> NormalizedState:
    """Manual requirement verdict (``evaluated_by='manual'``) - the agent asserts
    it implemented something; the engine still independently verifies the
    checkable parts (tests pass, tree clean) before it will report READY.

    A manually-COMPLETE requirement is re-checked on the next refresh only if the
    agent lowers it again - satisfied stays satisfied.
    """
    repo = TaskRepository(ctx.db)
    task = repo.get(task_id) or _raise_not_found(task_id)
    match = next((r for r in task.requirements if r.id == requirement_id), None)
    if match is None:
        raise DevMemoryError(f"Task {task_id} has no requirement {requirement_id!r}.")
    repo.update_requirement(
        task_id,
        match.model_copy(
            update={
                "status": status,
                "reason": note.strip() or f"set to {status.value} by the agent",
                "evidence": match.evidence,
                "evaluated_at": datetime.now(UTC),
                "evaluated_by": "manual",
            }
        ),
    )
    _log.info(
        "taskloop.requirement.set", task_id=task_id, requirement=requirement_id, status=status.value
    )
    return refresh_state(ctx, task_id)


def mark_complete(ctx: ProjectContext, task_id: str) -> NormalizedState:
    """Trigger a completion evaluation - never blindly mark READY (§11).

    Runs a full refresh (which re-evaluates all evidence) and returns the state.
    The caller sees READY only if the evidence supports it.
    """
    repo = TaskRepository(ctx.db)
    if repo.get(task_id) is None:
        _raise_not_found(task_id)
    _log.info("taskloop.mark_complete.requested", task_id=task_id)
    state = refresh_state(ctx, task_id)
    if state.overall_status is not TaskStatus.READY:
        _log.info(
            "taskloop.mark_complete.denied",
            task_id=task_id,
            status=state.overall_status.value,
        )
    return state


# --- status computation --------------------------------------------------


def _compute_status(
    *,
    task: Task,
    git: StateGit,
    tests: StateTests,
    requirements: list[Requirement],
    open_issues: list[Issue],
) -> tuple[TaskStatus, list[str], list[str]]:
    """Evidence-based status per §4. Returns (status, findings, recommended_focus)."""
    reqs = requirements
    findings: list[str] = []
    focus: list[str] = []

    # BLOCKED: git is the source of truth; without it nothing is verifiable.
    if not git.available:
        findings.append(f"Git unavailable: {git.reason}")
        return TaskStatus.BLOCKED, findings, ["Restore git access before continuing"]

    blockers = [i for i in open_issues if i.blocking and i.status is IssueStatus.OPEN]
    if blockers:
        for i in blockers:
            findings.append(f"Blocking issue #{i.id}: {i.description}")
        return TaskStatus.BLOCKED, findings, ["Resolve the blocking issue or escalate to a human"]

    incomplete = [r for r in reqs if r.status is not RequirementStatus.COMPLETE]
    unknown = [r for r in reqs if r.status is RequirementStatus.UNKNOWN]
    tests_ok = tests.status is TestRunStatus.PASSED or (
        tests.status is TestRunStatus.NOT_RUN and task.test_command is None
    )
    non_blocking_issues = [i for i in open_issues if not i.blocking]

    # findings
    if not git.working_tree_clean:
        findings.append("Working tree is dirty - commit before the state can be fully evaluated")
        focus.append("Commit the current changes")
    if tests.status is TestRunStatus.FAILED and (tests.failed or tests.passed):
        findings.append(f"{tests.failed} test(s) failing")
        focus.append("Fix failing tests")
    elif tests.status is TestRunStatus.FAILED:
        findings.append(f"Test command did not complete (exit {tests.exit_code})")
        focus.append("Repair the test command / environment")
    elif tests.status is TestRunStatus.ERROR:
        findings.append("Test command could not run")
        focus.append("Repair the test command / environment")
    elif tests.status is TestRunStatus.FAILED_TO_PARSE:
        findings.append("No parseable test results (no tests collected, or unknown format)")
        focus.append("Add tests, or set tests.parser / tests.command")
    elif tests.status is TestRunStatus.NOT_RUN and task.test_command:
        findings.append("Tests configured but not yet run")
    for r in incomplete:
        findings.append(f"{r.id} {r.status.value}: {r.reason or r.description}")
        focus.append(f"{r.id}: {r.description}")
    for i in non_blocking_issues:
        findings.append(f"Open issue #{i.id}: {i.description}")

    # READY: requirements complete, tests pass, no open issues, tree clean.
    if reqs and not incomplete and tests_ok and not non_blocking_issues and git.working_tree_clean:
        return TaskStatus.READY, findings or ["All requirements satisfied; tests pass"], []

    # IN_PROGRESS: nothing conclusive yet (no commits, everything still unknown).
    nothing_evaluated = not reqs or (
        len(unknown) == len(reqs) and tests.status is TestRunStatus.NOT_RUN
    )
    if nothing_evaluated and git.working_tree_clean and not non_blocking_issues:
        return TaskStatus.IN_PROGRESS, findings, focus or ["Begin implementing the requirements"]

    # otherwise there is concrete unfinished work
    return TaskStatus.NEEDS_WORK, findings, focus[:6]


def _raise_not_found(task_id: str) -> Task:
    raise TaskNotFoundError(task_id)


def latest_task(ctx: ProjectContext) -> Task | None:
    return TaskRepository(ctx.db).latest()


def list_tasks(ctx: ProjectContext) -> list[Task]:
    return TaskRepository(ctx.db).list_tasks()


def get_task(ctx: ProjectContext, task_id: str) -> Task:
    return TaskRepository(ctx.db).get(task_id) or _raise_not_found(task_id)


def list_snapshots(ctx: ProjectContext, task_id: str, *, limit: int = 20) -> list[StateSnapshot]:
    return TaskRepository(ctx.db).snapshots(task_id, limit=limit)


__all__ = [
    "TaskNotFoundError",
    "create_task",
    "get_checkpoint",
    "get_state",
    "get_task",
    "latest_task",
    "list_snapshots",
    "list_tasks",
    "mark_complete",
    "refresh_state",
    "report_issue",
    "resolve_issue",
    "set_requirement_status",
]
