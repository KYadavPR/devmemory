"""Evidence collectors for one state refresh.

Each collector wraps an existing DevMemory adapter and returns a normalized
state sub-model. Every one fails *gracefully* (§21): on any error it returns a
model with ``available=False`` / a ``NOT_RUN``/``ERROR`` status and a ``reason`` -
it never raises for "the tool just isn't here", and it never fabricates a count
or a checkpoint id.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from devmemory.adapters.tests import TestAdapter
from devmemory.domain.enums import TestRunStatus
from devmemory.domain.models import TestOutcome
from devmemory.domain.taskloop import StateCheckpoint, StateGit, StateImpact, StateTests
from devmemory.logging import get_logger
from devmemory.services.context import ProjectContext

_log = get_logger(__name__)

# Build-tool / test-runner droppings. The engine runs the test command on every
# refresh, so these churn constantly - they are never meaningful task work and
# must not keep a task out of READY (whether untracked or accidentally tracked).
_JUNK_PATH = re.compile(
    r"(^|/)(__pycache__|\.pytest_cache|\.ruff_cache|\.mypy_cache|node_modules"
    r"|\.tox|\.nox|htmlcov|\.coverage)(/|$)|\.pyc$|\.pyo$|(^|/)\.DS_Store$"
)


def _meaningful(paths: list[str]) -> list[str]:
    return [p for p in paths if not _JUNK_PATH.search(p)]


# --- git --------------------------------------------------------------------


def collect_git(ctx: ProjectContext, *, base_commit: str | None) -> StateGit:
    """Branch, HEAD, cumulative diff since the task's base commit, tree cleanliness.

    Git is the source of truth for committed code. If git is unavailable the
    engine treats the task as BLOCKED (§21).
    """
    git = ctx.git
    try:
        if not git.is_repository():
            return StateGit(available=False, reason="not a git repository")

        wt = git.working_tree_state()
        head = git.head_sha()
        subject = git.commit("HEAD").subject if head else None

        # "clean" for the READY gate ignores test-runner droppings (the engine
        # itself creates __pycache__/.pytest_cache every refresh).
        dirty = _meaningful(wt.staged) + _meaningful(wt.unstaged) + _meaningful(wt.untracked)
        tree_clean = not dirty

        files_changed = lines_added = lines_deleted = 0
        if head:
            # Cumulative task progress: base_commit..working-tree. Falls back to
            # the last commit's own diff when we have no base.
            diff_base = base_commit or git.parent_sha("HEAD")
            try:
                stat = git.diff_stat(diff_base, "HEAD")
                files_changed = stat.files_changed
                lines_added = stat.additions
                lines_deleted = stat.deletions
            except Exception as exc:
                _log.warning("taskloop.git.diffstat_failed", error=str(exc))

        _log.info("taskloop.collector.git", branch=wt.branch, clean=tree_clean)
        return StateGit(
            branch=wt.branch or "(detached)",
            commit_sha=head,
            commit_subject=subject,
            files_changed=files_changed,
            lines_added=lines_added,
            lines_deleted=lines_deleted,
            working_tree_clean=tree_clean,
            available=True,
        )
    except Exception as exc:
        _log.warning("taskloop.collector.git_failed", error=str(exc))
        return StateGit(available=False, reason=f"git error: {exc}")


# --- entire ----------------------------------------------------------------


def collect_checkpoint(ctx: ProjectContext, *, head_sha: str | None) -> StateCheckpoint:
    """Latest relevant checkpoint + the one tied to HEAD, plus a session id.

    Never fabricates a checkpoint id (§21). If Entire is absent/disabled the
    result is an empty :class:`StateCheckpoint` and the rest of the state still
    works (§21).
    """
    entire = ctx.entire
    out = StateCheckpoint()
    try:
        if not entire.is_installed():
            return out

        # The checkpoint associated with the current commit (trailer / heuristic).
        if head_sha:
            ref = entire.resolve_for_commit(head_sha)
            if ref is not None:
                out.last_committed_id = ref.checkpoint_id
                out.commit_sha = ref.commit_sha
                out.association = ref.association_method.value
                for sess in ref.sessions:
                    if sess.session_id:
                        out.session_id = sess.session_id
                        break

        # The newest checkpoint on the branch (may be ahead of HEAD, uncommitted).
        checkpoints = entire.list_checkpoints(limit=1)
        if checkpoints:
            cid = checkpoints[0].get("id") or checkpoints[0].get("checkpoint_id")
            if isinstance(cid, str):
                out.current_id = cid
        out.current_id = out.current_id or out.last_committed_id

        if out.session_id is None:
            for row in entire.list_sessions(limit=5):
                sid = row.get("session_id")
                if isinstance(sid, str) and row.get("status") == "active":
                    out.session_id = sid
                    break

        _log.info(
            "taskloop.collector.entire",
            current=out.current_id,
            committed=out.last_committed_id,
        )
        return out
    except Exception as exc:
        _log.warning("taskloop.collector.entire_failed", error=str(exc))
        return out  # empty, not fabricated


# --- tests ---------------------------------------------------------------


def collect_tests(
    ctx: ProjectContext,
    *,
    command: str | None,
    output_dir: Path,
) -> StateTests:
    """Run the configured test command and normalize the result.

    Supports pytest, ``npm test`` / ``npm run test`` (jest/mocha via the generic
    parser), and go. Parsing failures yield ``FAILED_TO_PARSE`` rather than
    invented counts (§9). A command that cannot start yields ``ERROR`` (§21).
    """
    if not command:
        return StateTests(status=TestRunStatus.NOT_RUN)

    cfg = ctx.config.tests
    adapter = TestAdapter(ctx.paths.repo_root)
    try:
        outcome = adapter.run(
            command,
            parser=cfg.parser,
            junit_xml=cfg.junit_xml,
            timeout=cfg.timeout_seconds,
        )
    except Exception as exc:
        _log.warning("taskloop.collector.tests_error", command=command, error=str(exc))
        return StateTests(command=command, status=TestRunStatus.ERROR)

    output_path: str | None = None
    if outcome.output:
        output_dir.mkdir(parents=True, exist_ok=True)
        fname = f"tests-{int(time.time())}.log"
        (output_dir / fname).write_text(outcome.output, encoding="utf-8")
        output_path = str((output_dir / fname).relative_to(ctx.paths.repo_root))

    status = _classify_tests(outcome)
    _log.info(
        "taskloop.collector.tests",
        command=command,
        status=status.value,
        passed=outcome.passed,
        failed=outcome.failed,
    )
    return StateTests(
        command=command,
        passed=outcome.passed,
        failed=outcome.failed,
        skipped=outcome.skipped,
        status=status,
        exit_code=outcome.exit_code,
        output_path=output_path,
    )


def _classify_tests(outcome: TestOutcome) -> TestRunStatus:
    total = outcome.passed + outcome.failed + outcome.skipped
    # pytest exit 5 = "no tests were collected". The TestAdapter synthesizes
    # errors=1 for any non-zero exit, so check the code before the count.
    if outcome.exit_code == 5 and outcome.failed == 0:
        return TestRunStatus.FAILED_TO_PARSE
    if outcome.failed > 0 or outcome.errors > 0:
        return TestRunStatus.FAILED
    if total == 0:
        # Command ran, nothing parsed. A clean exit means an unknown format;
        # a non-zero exit is a real failure.
        if outcome.exit_code in (0, None):
            return TestRunStatus.FAILED_TO_PARSE
        return TestRunStatus.FAILED
    if outcome.exit_code in (0, None):
        return TestRunStatus.PASSED
    return TestRunStatus.FAILED


# --- graph (optional) --------------------------------------------------


def collect_impact(
    ctx: ProjectContext, *, head_sha: str | None, base_commit: str | None = None
) -> StateImpact:
    """A small, useful change-impact count from the Entire ``graph`` plugin.

    Cumulative for the task: the entity-level diff from ``base_commit`` to HEAD
    (falls back to the last commit alone when there is no base). Not a
    visualization, not a graph DB (§8). If the plugin is unavailable the result
    is ``available=False`` with a reason and the state still works.
    """
    graph = ctx.graph
    try:
        if not graph.is_available:
            probe = graph.probe()
            return StateImpact(available=False, reason=probe.detail or "graph plugin not installed")
        if not head_sha:
            return StateImpact(available=False, reason="no commit to analyze")

        if base_commit and base_commit != head_sha:
            impact = graph.diff_impact(base_commit, "HEAD") or graph.commit_impact(head_sha)
        else:
            impact = graph.commit_impact(head_sha)
        if impact is None:
            return StateImpact(available=False, reason="graph returned no impact for this commit")

        affected_files = len({e.path for e in impact.entities})
        affected_tests = sum(
            1
            for e in impact.entities
            if "test" in e.path.lower() or e.path.lower().endswith("_test.go")
        )
        details = [
            f"{e.change_type} {e.kind} {e.name} ({e.dependents_count} dependents)"
            for e in impact.hotspots[:8]
        ]
        _log.info("taskloop.collector.graph", affected_files=affected_files)
        return StateImpact(
            affected_files=affected_files,
            affected_tests=affected_tests,
            available=True,
            details=details,
        )
    except Exception as exc:
        _log.warning("taskloop.collector.graph_failed", error=str(exc))
        return StateImpact(available=False, reason=f"graph error: {exc}")


__all__ = ["collect_checkpoint", "collect_git", "collect_impact", "collect_tests"]
