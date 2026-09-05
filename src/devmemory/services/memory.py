"""Development memory: surface previous attempts so failed approaches aren't repeated.

Given a scope (files being touched, a feature, an intent), find the historical
versions that are relevant - especially the ones that failed or regressed - and
return them with a short "why this matched" and a recommendation.

Retrieval is deliberately simple (file overlap + feature + FTS keyword match +
status). Embeddings can be layered on later without changing this interface.
"""

from __future__ import annotations

from pydantic import BaseModel

from devmemory.domain.enums import VersionStatus
from devmemory.domain.models import DevelopmentVersion
from devmemory.services.context import ProjectContext
from devmemory.storage.repositories import FeatureRepository
from devmemory.storage.versions import VersionRepository

_ADVERSE = {VersionStatus.REGRESSION, VersionStatus.ERROR}


class PreviousAttempt(BaseModel):
    version_id: str
    version_number: int
    status: str
    intent: str | None
    agent: str | None
    feature: str | None
    git_commit: str
    files: list[str]
    change_summary: str
    result: str
    recommendation: str | None
    is_adverse: bool
    score: float
    matched_on: list[str]


class MemoryQuery(BaseModel):
    files: list[str] = []
    feature: str | None = None
    intent: str | None = None
    include_successes: bool = False
    limit: int = 10


def previous_attempts(ctx: ProjectContext, query: MemoryQuery) -> list[PreviousAttempt]:
    repo = VersionRepository(ctx.db)
    project_id = ctx.config.project_id
    want_files = {_norm(f) for f in query.files}

    feature_id: str | None = None
    if query.feature:
        feat = FeatureRepository(ctx.db).get_by_name(project_id, query.feature)
        feature_id = feat.feature_id if feat else None

    candidates: dict[str, DevelopmentVersion] = {}
    if query.intent:
        for v in _by_ids(repo, repo.search_ids(project_id, query.intent, limit=40)):
            candidates[v.version_id] = v
    for v in repo.page(project_id, limit=500, ascending=False):
        candidates.setdefault(v.version_id, v)

    scored: list[PreviousAttempt] = []
    for v in candidates.values():
        attempt = _score(v, want_files, feature_id, query)
        if attempt is not None:
            scored.append(attempt)

    scored.sort(key=lambda a: (a.score, a.version_number), reverse=True)
    return scored[: query.limit]


def _score(
    v: DevelopmentVersion,
    want_files: set[str],
    feature_id: str | None,
    query: MemoryQuery,
) -> PreviousAttempt | None:
    is_adverse = v.status in _ADVERSE or bool(v.regressions)
    if not is_adverse and not query.include_successes:
        return None

    matched: list[str] = []
    score = 0.0

    v_files = {_norm(f.path) for f in v.changed_files}
    overlap = want_files & v_files
    if overlap:
        score += 3.0 + 0.5 * len(overlap)
        matched.append("files: " + ", ".join(sorted(overlap)[:3]))

    if feature_id and v.feature_id == feature_id:
        score += 2.5
        matched.append(f"feature: {query.feature}")

    if query.intent and v.intent:
        shared = _keyword_overlap(query.intent, v.intent)
        if shared:
            score += 1.0 + 0.4 * len(shared)
            matched.append("intent: " + ", ".join(sorted(shared)[:3]))

    if is_adverse:
        score += 1.5

    if score <= 0 or not matched:
        return None

    return PreviousAttempt(
        version_id=v.version_id,
        version_number=v.version_number,
        status=v.status.value,
        intent=v.intent,
        agent=v.agent,
        feature=v.feature_id.split(":", 1)[-1] if v.feature_id else None,
        git_commit=v.git_commit,
        files=[f.path for f in v.changed_files],
        change_summary=_change_summary(v),
        result=_result_summary(v),
        recommendation=_recommendation(v),
        is_adverse=is_adverse,
        score=round(score, 2),
        matched_on=matched,
    )


def _change_summary(v: DevelopmentVersion) -> str:
    files = ", ".join(f.path for f in v.changed_files[:3])
    more = f" (+{len(v.changed_files) - 3} more)" if len(v.changed_files) > 3 else ""
    return f"{files}{more}  +{v.lines_added}/-{v.lines_removed}" if files else v.intent or "—"


def _result_summary(v: DevelopmentVersion) -> str:
    parts: list[str] = []
    for r in v.regressions:
        if r.before is not None and r.after is not None:
            parts.append(f"{r.metric or r.kind} {r.before:g} → {r.after:g}")
        elif r.detail:
            parts.append(r.detail)
    if not parts and v.tests and v.tests.ran and not v.tests.all_passed:
        parts.append(f"{v.tests.failed} tests failed")
    if not parts:
        for m in v.metrics:
            if m.before is not None and m.after is not None:
                parts.append(f"{m.name} {m.before:g} → {m.after:g}")
    return "; ".join(parts) or v.status.value


def _recommendation(v: DevelopmentVersion) -> str | None:
    if v.analysis and v.analysis.recommendation:
        return v.analysis.recommendation
    if v.status is VersionStatus.REGRESSION or v.regressions:
        return "This approach regressed here - avoid repeating it, or address the cause first."
    if v.status is VersionStatus.ERROR:
        return "This approach errored - check the fix that followed before retrying."
    return None


def _keyword_overlap(a: str, b: str) -> set[str]:
    return _keywords(a) & _keywords(b)


_STOP = {
    "the",
    "a",
    "an",
    "to",
    "of",
    "and",
    "or",
    "for",
    "in",
    "on",
    "with",
    "is",
    "add",
    "fix",
    "update",
    "change",
    "make",
    "use",
    "improve",
    "implement",
    "this",
    "that",
    "it",
    "be",
    "into",
    "from",
    "so",
}


def _keywords(text: str) -> set[str]:
    return {
        w
        for w in "".join(c if c.isalnum() else " " for c in text.lower()).split()
        if len(w) > 2 and w not in _STOP
    }


def _by_ids(repo: VersionRepository, ids: list[str]) -> list[DevelopmentVersion]:
    return [v for vid in ids if (v := repo.get(vid)) is not None]


def _norm(path: str) -> str:
    return path.replace("\\", "/").lstrip("./").lower()


__all__ = ["MemoryQuery", "PreviousAttempt", "previous_attempts"]
