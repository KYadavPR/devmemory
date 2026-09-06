"""Requirement normalization and evaluation (§5).

At task creation the human goal is normalized into a small explicit list. On each
refresh, requirements that are not already COMPLETE are re-evaluated against the
evidence - Git diff, changed files, the checkpoint intent, and test results.

An LLM is used *only where it helps* and its output is always structured and
auditable ({requirement_id, status, reason, evidence}). When no LLM key is
configured a deterministic rule-based evaluator runs instead - never a guess from
Git statistics alone.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from devmemory.analysis.llm import call_llm
from devmemory.domain.enums import RequirementStatus, TestRunStatus
from devmemory.domain.taskloop import (
    Requirement,
    RequirementVerdict,
    StateGit,
    StateTests,
)
from devmemory.logging import get_logger
from devmemory.services.context import ProjectContext

_log = get_logger(__name__)

_MAX_DIFF_BYTES = 6000
_TESTS_HINT = re.compile(r"\btest", re.IGNORECASE)

_NORMALIZE_SYSTEM = (
    "You split a software task into a SHORT list of explicit, independently "
    "checkable requirements (aim for 3-6). Each must be verifiable from the code "
    "and tests. Always include a final requirement that the relevant tests exist "
    "and pass. Reply with ONLY a JSON array: "
    '[{"id":"R1","description":"..."}, ...]. No prose.'
)

_EVAL_SYSTEM = (
    "You evaluate whether each requirement is satisfied by the EVIDENCE provided "
    "(git diff, changed files, checkpoint intent, test results). Judge only from "
    "evidence - do not assume work that is not shown. Never infer completion from "
    "line counts alone. Reply with ONLY a JSON array: "
    '[{"requirement_id":"R3","status":"COMPLETE|PARTIAL|INCOMPLETE|UNKNOWN",'
    '"reason":"one sentence","evidence":["..."]}]. No prose.'
)


# --- normalization --------------------------------------------------------


def normalize_requirements(
    goal: str, ctx: ProjectContext, *, brief: str | None = None
) -> list[Requirement]:
    """Turn the human goal into R1..Rn. LLM when a key is configured, else rules.

    ``brief`` is the project's single source of truth (see
    :mod:`devmemory.services.brief`); when present it is given to the LLM as
    context so requirements reflect the project's constraints and conventions.
    """
    providers = ctx.config.analysis.providers
    prompt = f"TASK:\n{goal.strip()}"
    if brief:
        prompt = f"PROJECT BRIEF (source of truth):\n{brief.strip()}\n\n{prompt}"
    text = call_llm(
        prompt,
        system=_NORMALIZE_SYSTEM,
        providers=providers,
        model=ctx.config.analysis.model,
    )
    parsed = _parse_json_array(text) if text else None
    if parsed:
        reqs: list[Requirement] = []
        for i, item in enumerate(parsed, start=1):
            if not isinstance(item, dict):
                continue
            desc = str(item.get("description") or "").strip()
            if not desc:
                continue
            reqs.append(Requirement(id=f"R{i}", description=desc, evaluated_by=""))
        if reqs:
            _log.info("taskloop.requirements.normalized", count=len(reqs), by="llm")
            return reqs

    reqs = _rule_based_split(goal)
    _log.info("taskloop.requirements.normalized", count=len(reqs), by="rules")
    return reqs


def _rule_based_split(goal: str) -> list[Requirement]:
    """Conservative split on clause boundaries (', and ' / ';' / newline / '. ' /
    numbered list markers). Always ends with a 'tests exist and pass' requirement."""
    raw = re.split(r"(?:,\s+and\s+)|(?:\s+and\s+then\s+)|[;\n]|(?:\.\s+)|(?:^|\s)\d+[.)]\s+", goal)
    clauses = [c.strip(" .\t-") for c in raw if len(c.strip(" .\t-")) > 6]
    if not clauses:
        clauses = [goal.strip()]
    reqs = [
        Requirement(id=f"R{i}", description=c[:1].upper() + c[1:]) for i, c in enumerate(clauses, 1)
    ]
    if not any(_TESTS_HINT.search(r.description) for r in reqs):
        reqs.append(
            Requirement(id=f"R{len(reqs) + 1}", description="Relevant tests exist and pass")
        )
    return reqs


# --- evaluation ----------------------------------------------------------


def evaluate_requirements(
    requirements: list[Requirement],
    *,
    ctx: ProjectContext,
    git: StateGit,
    tests: StateTests,
    checkpoint_intent: str | None,
    base_commit: str | None,
) -> list[RequirementVerdict]:
    """Re-evaluate every not-yet-COMPLETE requirement against current evidence.

    COMPLETE requirements are returned unchanged (a satisfied requirement stays
    satisfied unless the agent explicitly reopens it).
    """
    pending = [r for r in requirements if r.status is not RequirementStatus.COMPLETE]
    done = [
        RequirementVerdict(
            requirement_id=r.id, status=r.status, reason=r.reason, evidence=r.evidence
        )
        for r in requirements
        if r.status is RequirementStatus.COMPLETE
    ]
    if not pending:
        return done

    changed = _changed_paths(ctx, base_commit)
    diff_excerpt = _diff_excerpt(ctx, base_commit)

    verdicts = _evaluate_llm(pending, git, tests, checkpoint_intent, changed, diff_excerpt, ctx)
    if verdicts is None:
        verdicts = [
            _evaluate_one_rule(r, tests=tests, changed=changed, diff=diff_excerpt) for r in pending
        ]
    return done + verdicts


def _evaluate_llm(
    pending: list[Requirement],
    git: StateGit,
    tests: StateTests,
    checkpoint_intent: str | None,
    changed: list[str],
    diff_excerpt: str,
    ctx: ProjectContext,
) -> list[RequirementVerdict] | None:
    payload = {
        "requirements": [{"id": r.id, "description": r.description} for r in pending],
        "evidence": {
            "changed_files": changed,
            "checkpoint_intent": checkpoint_intent,
            "tests": {
                "status": tests.status.value,
                "passed": tests.passed,
                "failed": tests.failed,
            },
            "git": {
                "files_changed": git.files_changed,
                "lines_added": git.lines_added,
                "working_tree_clean": git.working_tree_clean,
            },
            "diff_excerpt": diff_excerpt,
        },
    }
    text = call_llm(
        json.dumps(payload, indent=2),
        system=_EVAL_SYSTEM,
        providers=ctx.config.analysis.providers,
        model=ctx.config.analysis.model,
    )
    parsed = _parse_json_array(text) if text else None
    if not parsed:
        return None

    by_id = {r.id for r in pending}
    out: list[RequirementVerdict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        rid = str(item.get("requirement_id") or "")
        if rid not in by_id:
            continue
        try:
            status = RequirementStatus(str(item.get("status", "UNKNOWN")).upper())
        except ValueError:
            status = RequirementStatus.UNKNOWN
        evidence = item.get("evidence")
        out.append(
            RequirementVerdict(
                requirement_id=rid,
                status=status,
                reason=str(item.get("reason") or "").strip()[:400] or "evaluated by LLM",
                evidence=[str(e) for e in evidence][:8] if isinstance(evidence, list) else [],
            )
        )
    seen = {v.requirement_id for v in out}
    for r in pending:
        if r.id not in seen:
            out.append(_evaluate_one_rule(r, tests=tests, changed=changed, diff=diff_excerpt))
    _log.info("taskloop.requirements.evaluated", by="llm", pending=len(pending))
    return out


def _evaluate_one_rule(
    req: Requirement,
    *,
    tests: StateTests,
    changed: list[str],
    diff: str,
) -> RequirementVerdict:
    """Deterministic fallback: keyword overlap with changed paths + diff, and a
    real check for the 'tests pass' requirement. Conservative - it will say
    INCOMPLETE/PARTIAL rather than claim completion it cannot see."""
    desc = req.description.lower()

    if _TESTS_HINT.search(desc) and ("pass" in desc or "exist" in desc or "green" in desc):
        if tests.status is TestRunStatus.PASSED and tests.passed > 0:
            return RequirementVerdict(
                requirement_id=req.id,
                status=RequirementStatus.COMPLETE,
                reason=f"{tests.passed} tests pass, 0 failed",
                evidence=[f"tests: {tests.command}"],
            )
        if tests.status in (TestRunStatus.NOT_RUN,):
            return RequirementVerdict(
                requirement_id=req.id,
                status=RequirementStatus.INCOMPLETE,
                reason="no test command configured / tests not run",
            )
        return RequirementVerdict(
            requirement_id=req.id,
            status=RequirementStatus.INCOMPLETE,
            reason=f"tests {tests.status.value.lower()} ({tests.failed} failed)",
        )

    keywords = {w for w in re.findall(r"[a-z_]{4,}", desc) if w not in _STOPWORDS}
    hay = " ".join(changed).lower() + "\n" + diff.lower()
    hits = sorted(k for k in keywords if k in hay)
    if not keywords:
        status, reason = (
            RequirementStatus.UNKNOWN,
            "requirement not keyword-checkable; inspect repo",
        )
    elif len(hits) >= max(2, len(keywords) // 2):
        status = RequirementStatus.PARTIAL
        reason = f"evidence in changed code for: {', '.join(hits)} (verify behavior + tests)"
    elif hits:
        status = RequirementStatus.PARTIAL
        reason = f"weak evidence ({', '.join(hits)}); likely more work needed"
    else:
        status = RequirementStatus.INCOMPLETE
        reason = "no implementation evidence in the diff for this requirement"
    return RequirementVerdict(
        requirement_id=req.id,
        status=status,
        reason=reason,
        evidence=[f"changed: {p}" for p in changed[:5]],
    )


_STOPWORDS = {
    "that",
    "this",
    "with",
    "have",
    "from",
    "when",
    "then",
    "must",
    "should",
    "will",
    "into",
    "your",
    "user",
    "users",
    "able",
    "exists",
    "exist",
    "support",
    "handle",
    "using",
    "provide",
}


# --- evidence helpers --------------------------------------------------


def _changed_paths(ctx: ProjectContext, base_commit: str | None) -> list[str]:
    try:
        base = base_commit or ctx.git.parent_sha("HEAD")
        return [f.path for f in ctx.git.changed_files(base, "HEAD")]
    except Exception as exc:
        _log.warning("taskloop.requirements.changed_paths_failed", error=str(exc))
        return []


def _diff_excerpt(ctx: ProjectContext, base_commit: str | None) -> str:
    try:
        base = base_commit or ctx.git.parent_sha("HEAD")
        text = ctx.git.diff_text(base, "HEAD")
    except Exception:
        return ""
    return text[:_MAX_DIFF_BYTES]


def _parse_json_array(text: str | None) -> list[object] | None:
    if not text:
        return None
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def apply_verdicts(
    requirements: list[Requirement], verdicts: list[RequirementVerdict], *, by: str
) -> list[Requirement]:
    """Merge verdicts back onto the requirement list (pure - no I/O)."""
    now = datetime.now(UTC)
    by_id = {v.requirement_id: v for v in verdicts}
    out: list[Requirement] = []
    for req in requirements:
        v = by_id.get(req.id)
        if v is None:
            out.append(req)
            continue
        out.append(
            req.model_copy(
                update={
                    "status": v.status,
                    "reason": v.reason,
                    "evidence": v.evidence,
                    "evaluated_at": now,
                    "evaluated_by": by,
                }
            )
        )
    return out


__all__ = ["apply_verdicts", "evaluate_requirements", "normalize_requirements"]
