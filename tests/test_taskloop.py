"""The state-aware coding loop: engine, collectors, requirement evaluation, and
the two-cycle NEEDS_WORK -> READY demo (§26). No LLM key is set in tests, so the
rule-based requirement evaluator is exercised.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest

from devmemory.domain.enums import RequirementStatus, TaskStatus
from devmemory.domain.enums import TestRunStatus as RunStatus
from devmemory.services.context import ProjectContext
from devmemory.services.projects import init_project
from devmemory.services.taskloop import engine
from devmemory.storage.tasks import TaskRepository
from tests.conftest import TmpGitRepo

_PYTEST = f"{sys.executable} -m pytest -q"


@pytest.fixture
def project(git_repo: TmpGitRepo, monkeypatch: pytest.MonkeyPatch) -> Iterator[ProjectContext]:
    # ensure no LLM path: force the rule-based evaluator
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    git_repo.write("pkg/__init__.py", "")
    git_repo.write("pkg/calc.py", "def add(a, b):\n    return a + b\n")
    git_repo.write(
        "tests/test_calc.py",
        "from pkg.calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    )
    git_repo.commit("chore: baseline package")
    init_project(git_repo.path, name="Calc", project_id="calc")
    git_repo.commit("chore: devmemory")
    ctx = ProjectContext.load(git_repo.path)
    try:
        yield ctx
    finally:
        ctx.close()


# --- requirement normalization ------------------------------------------


def test_normalize_requirements_rules_split(project: ProjectContext) -> None:
    task = engine.create_task(
        project,
        goal="Add a subtract helper; add a multiply helper; keep tests green",
    )
    descriptions = [r.description for r in task.requirements]
    assert len(task.requirements) == 3
    assert task.requirements[0].id == "R1"
    assert any("subtract" in d.lower() for d in descriptions)
    assert any("multiply" in d.lower() for d in descriptions)


def test_normalize_always_adds_a_tests_requirement(project: ProjectContext) -> None:
    task = engine.create_task(project, goal="Add a divide helper")
    assert any("test" in r.description.lower() for r in task.requirements)


def test_create_task_pins_base_commit(project: ProjectContext) -> None:
    head = project.git.head_sha()
    task = engine.create_task(project, goal="Add a divide helper and tests")
    assert task.base_commit == head
    assert task.status is TaskStatus.IN_PROGRESS


# --- collectors --------------------------------------------------------


def test_refresh_collects_git_and_runs_tests(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    task = engine.create_task(
        project, goal="Add a subtract helper and a test", test_command=_PYTEST
    )
    state = engine.refresh_state(project, task.id)

    assert state.git.available is True
    assert state.git.branch == "main"
    assert state.git.commit_sha == git_repo.rev("HEAD")
    assert state.git.working_tree_clean is True
    assert state.tests.command == _PYTEST
    assert state.tests.status is RunStatus.PASSED
    assert state.tests.passed >= 1
    assert state.snapshot_id is not None


def test_tests_not_run_when_no_command(project: ProjectContext) -> None:
    task = engine.create_task(project, goal="Add a divide helper")
    # config has no tests.command and none passed -> NOT_RUN
    object.__setattr__(project.config.tests, "command", None)
    repo = TaskRepository(project.db)
    t = repo.get(task.id)
    assert t is not None
    repo._db.execute("UPDATE tasks SET test_command = NULL WHERE id = ?", (task.id,))
    state = engine.refresh_state(project, task.id)
    assert state.tests.status is RunStatus.NOT_RUN


def test_impact_collector_is_optional(project: ProjectContext) -> None:
    task = engine.create_task(project, goal="Add a helper and tests", test_command=_PYTEST)
    state = engine.refresh_state(project, task.id)
    # graph plugin may or may not be installed; either way the state still works
    assert isinstance(state.impact.available, bool)
    if state.impact.available:
        assert state.impact.affected_files >= 0
    else:
        assert state.impact.reason
    assert state.overall_status in set(TaskStatus)


def test_failing_tests_produce_needs_work_and_an_issue(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    task = engine.create_task(project, goal="Add a subtract helper and tests", test_command=_PYTEST)
    git_repo.write(
        "tests/test_calc.py",
        "from pkg.calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 999\n",
    )
    git_repo.commit("test: break it")
    state = engine.refresh_state(project, task.id)

    assert state.tests.status is RunStatus.FAILED
    assert state.overall_status is TaskStatus.NEEDS_WORK
    assert any("fail" in f.lower() for f in state.findings)
    assert any(i.kind == "test" for i in state.unresolved)


# --- the closed loop (§26) -------------------------------------------


def test_two_cycles_needs_work_then_ready(project: ProjectContext, git_repo: TmpGitRepo) -> None:
    task = engine.create_task(
        project,
        goal="Add a subtract helper to pkg.calc; relevant tests exist and pass",
        test_command=_PYTEST,
    )
    assert [r.id for r in task.requirements] == ["R1", "R2"]

    # Cycle 1: nothing implemented yet -> NEEDS_WORK
    s1 = engine.refresh_state(project, task.id)
    assert s1.overall_status is TaskStatus.NEEDS_WORK
    assert any(r.status is not RequirementStatus.COMPLETE for r in s1.requirements)
    assert s1.recommended_focus

    # Agent implements + commits
    git_repo.write(
        "pkg/calc.py",
        "def add(a, b):\n    return a + b\n\n\ndef subtract(a, b):\n    return a - b\n",
    )
    git_repo.write(
        "tests/test_calc.py",
        "from pkg.calc import add, subtract\n\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n\n"
        "def test_subtract():\n    assert subtract(5, 3) == 2\n",
    )
    git_repo.commit("feat: add subtract helper + test")

    # Agent records its verdict for the feature requirement; the engine still
    # verifies the checkable parts (tests, tree) itself.
    s2 = engine.set_requirement_status(
        project,
        task_id=task.id,
        requirement_id="R1",
        status=RequirementStatus.COMPLETE,
        note="implemented pkg.calc.subtract",
    )

    # Cycle 2: R1 asserted + R2 (tests) verified by the engine -> READY
    assert s2.tests.status is RunStatus.PASSED
    assert s2.git.working_tree_clean is True
    assert all(r.status is RequirementStatus.COMPLETE for r in s2.requirements)
    assert s2.overall_status is TaskStatus.READY

    # snapshots accumulate: create -> NEEDS_WORK (#1) -> NEEDS_WORK -> READY
    statuses = [s.overall_status for s in engine.list_snapshots(project, task.id)]
    assert statuses[0] is TaskStatus.READY
    assert TaskStatus.NEEDS_WORK in statuses


def test_dirty_tree_defers_requirement_evaluation(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    task = engine.create_task(project, goal="Add a subtract helper and tests", test_command=_PYTEST)
    git_repo.write("pkg/calc.py", "def add(a, b):\n    return a + b\n\n# work in progress\n")
    # not committed
    state = engine.refresh_state(project, task.id)
    assert state.git.working_tree_clean is False
    assert any("dirty" in f.lower() or "commit" in f.lower() for f in state.findings)
    assert state.overall_status is TaskStatus.NEEDS_WORK


# --- issues & blocking --------------------------------------------


def test_report_blocking_issue_forces_blocked(
    project: ProjectContext, git_repo: TmpGitRepo
) -> None:
    task = engine.create_task(project, goal="Add a helper and tests", test_command=_PYTEST)
    issue = engine.report_issue(
        project,
        task_id=task.id,
        description="Need product decision on the API shape",
        blocking=True,
    )
    assert issue.id is not None

    state = engine.refresh_state(project, task.id)
    assert state.overall_status is TaskStatus.BLOCKED
    assert any(i.blocking for i in state.unresolved)

    # resolve it -> no longer blocked
    assert engine.resolve_issue(project, issue_id=issue.id) is True
    state2 = engine.refresh_state(project, task.id)
    assert state2.overall_status is not TaskStatus.BLOCKED


def test_mark_complete_never_blindly_ready(project: ProjectContext) -> None:
    task = engine.create_task(project, goal="Add a divide helper and tests", test_command=_PYTEST)
    state = engine.mark_complete(project, task.id)
    # nothing implemented -> the completion evaluation must NOT return READY
    assert state.overall_status is not TaskStatus.READY


# --- get_state / persistence ------------------------------------


def test_get_state_returns_latest_snapshot(project: ProjectContext) -> None:
    task = engine.create_task(project, goal="Add a helper and tests", test_command=_PYTEST)
    refreshed = engine.refresh_state(project, task.id)
    fetched = engine.get_state(project, task.id)
    assert fetched.snapshot_id == refreshed.snapshot_id
    assert fetched.overall_status == refreshed.overall_status


def test_unknown_task_raises(project: ProjectContext) -> None:
    with pytest.raises(engine.TaskNotFoundError):
        engine.get_state(project, "TASK-999")
