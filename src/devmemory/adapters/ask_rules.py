"""Built-in "Ask" answers - zero configuration, no LLM, no Databricks.

This is the floor under the Ask chat: it recognises the common questions people
ask about a development history and answers them straight from the local
database. It is not open-ended - it matches a question to one of a fixed set of
intents (counts, regressions, failing tests, file churn, feature/agent
breakdowns, metric trends, recent activity, a single version) and renders a
templated answer plus a table. Anything it does not recognise gets a short list
of what it *can* answer, and a note that an LLM key unlocks free-form questions.

The richer engines (:mod:`devmemory.adapters.local_ask` with an LLM key, or
Databricks Genie) are tried first when available; this one always works.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from typing import Any

from devmemory.adapters.genie import GenieAnswer
from devmemory.domain.enums import VersionStatus
from devmemory.domain.models import DevelopmentVersion
from devmemory.logging import get_logger
from devmemory.services.context import ProjectContext
from devmemory.storage.versions import VersionRepository

_log = get_logger(__name__)

_ADVERSE = {VersionStatus.REGRESSION, VersionStatus.ERROR}


class _Result:
    __slots__ = ("columns", "rows", "text")

    def __init__(
        self,
        text: str,
        columns: list[str] | None = None,
        rows: list[list[Any]] | None = None,
    ) -> None:
        self.text = text
        self.columns = columns or []
        self.rows = rows or []


Handler = Callable[[list[DevelopmentVersion], str, "re.Match[str] | None"], _Result]


class RulesAskAdapter:
    def __init__(self, ctx: ProjectContext) -> None:
        self._ctx = ctx

    @property
    def is_available(self) -> bool:
        return True

    @property
    def engine_label(self) -> str:
        return "built-in (common questions, no LLM)"

    def ask(self, question: str, *, conversation_id: str | None = None) -> GenieAnswer:
        q = question.strip()
        low = q.lower()
        versions = VersionRepository(self._ctx.db).page(
            self._ctx.config.project_id, limit=5000, ascending=True
        )
        answer = GenieAnswer(question=q, conversation_id=conversation_id)

        if not versions:
            answer.text = (
                "There are no development versions recorded yet. Run "
                "`devmemory backfill` to import your git history, or `devmemory "
                "checkpoint` after a commit."
            )
            return answer

        for trigger, handler in _INTENTS:
            match = trigger(low)
            if match is None:
                continue
            result = handler(versions, low, match if isinstance(match, re.Match) else None)
            answer.text = result.text
            answer.columns = result.columns
            answer.rows = result.rows
            answer.row_count = len(result.rows)
            _log.info("ask_rules.answer", rows=len(result.rows))
            return answer

        answer.text = _help_text(versions)
        return answer


# --- triggers -------------------------------------------------------------------


def _kw(*words: str) -> Callable[[str], object]:
    def _match(low: str) -> object:
        return True if any(w in low for w in words) else None

    return _match


def _re(pattern: str) -> Callable[[str], object]:
    rx = re.compile(pattern)

    def _match(low: str) -> object:
        return rx.search(low)

    return _match


# --- handlers ------------------------------------------------------------------


def _feature_name(v: DevelopmentVersion) -> str | None:
    return v.feature_id.split(":", 1)[-1] if v.feature_id else None


def _day(v: DevelopmentVersion) -> str:
    return (v.committed_at or v.created_at).strftime("%Y-%m-%d")


def _is_adverse(v: DevelopmentVersion) -> bool:
    return v.status in _ADVERSE or bool(v.regressions)


def _h_count(vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None) -> _Result:
    by_status: Counter[str] = Counter(v.status.value for v in vs)
    first, last = vs[0], vs[-1]
    text = (
        f"{len(vs)} development versions ({first.version_id}-{last.version_id}), "
        f"recorded {_day(first)} to {_day(last)}."
    )
    rows = [[s, n] for s, n in by_status.most_common()]
    return _Result(text, ["status", "versions"], rows)


def _h_regressions(vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None) -> _Result:
    bad = [v for v in vs if _is_adverse(v)]
    if not bad:
        return _Result("No versions regressed or carry a regression. Clean history.")
    rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    rows: list[list[object]] = []
    for v in reversed(bad):
        worst = max(v.regressions, key=lambda r: rank.get(r.severity, 0), default=None)
        rows.append(
            [
                v.version_id,
                _feature_name(v) or "-",
                v.agent or "-",
                worst.severity if worst else v.status.value,
                (worst.detail if worst and worst.detail else "status marked " + v.status.value)[:80],
            ]
        )
    return _Result(
        f"{len(bad)} of {len(vs)} versions regressed or carry a regression "
        f"(newest first).",
        ["version", "feature", "agent", "severity", "detail"],
        rows,
    )


def _h_failed_tests(vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None) -> _Result:
    failed = [v for v in vs if v.tests and v.tests.ran and v.tests.failed > 0]
    if not failed:
        ran = [v for v in vs if v.tests and v.tests.ran]
        if not ran:
            return _Result("No version has recorded test results.")
        return _Result(f"No version has failing tests ({len(ran)} ran tests).")
    rows = [
        [v.version_id, v.tests.passed, v.tests.failed, _day(v), (v.intent or "-")[:70]]
        for v in reversed(failed)
        if v.tests
    ]
    return _Result(
        f"{len(failed)} versions had failing tests (newest first).",
        ["version", "passed", "failed", "date", "intent"],
        rows,
    )


def _h_churn(vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None) -> _Result:
    changes: Counter[str] = Counter()
    adverse: Counter[str] = Counter()
    pair: Counter[tuple[str, str]] = Counter()
    for v in vs:
        paths = [f.path for f in v.changed_files]
        bad = _is_adverse(v)
        for p in paths:
            changes[p] += 1
            if bad:
                adverse[p] += 1
        for i in range(len(paths)):
            for j in range(i + 1, len(paths)):
                lo, hi = sorted((paths[i], paths[j]))
                pair[(lo, hi)] += 1

    if "together" in low or "co-change" in low or "cochange" in low or "same time" in low:
        pairs = pair.most_common(12)
        if not pairs:
            return _Result("Not enough multi-file changes to find co-change pairs.")
        return _Result(
            "File pairs that change together most often:",
            ["file a", "file b", "times together"],
            [[a, b, n] for (a, b), n in pairs],
        )

    return _Result(
        "Most-churned files (risk = share of their changes that regressed):",
        ["path", "changes", "adverse", "risk"],
        [[p, c, adverse[p], round(adverse[p] / c, 2)] for p, c in changes.most_common(15)],
    )


def _h_features(vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None) -> _Result:
    by: dict[str, list[DevelopmentVersion]] = defaultdict(list)
    for v in vs:
        name = _feature_name(v)
        if name:
            by[name].append(v)
    if not by:
        return _Result("No versions are attributed to a feature area yet.")
    order_by_regr = "regress" in low or "worst" in low or "most" in low
    rows_data = []
    for name, group in by.items():
        succ = sum(1 for v in group if v.status is VersionStatus.SUCCESS)
        regr = sum(1 for v in group if _is_adverse(v))
        rows_data.append((name, len(group), succ, regr, round(succ / len(group) * 100, 1), group[-1].status.value))
    rows_data.sort(key=lambda r: (-r[3], -r[1]) if order_by_regr else (-r[1], -r[3]))
    text = (
        "Features by regressions, then attempts:"
        if order_by_regr
        else "Features by number of attempts:"
    )
    return _Result(
        text,
        ["feature", "attempts", "successes", "regressions", "success %", "latest"],
        [list(r) for r in rows_data],
    )


def _h_agents(vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None) -> _Result:
    by: dict[str, list[DevelopmentVersion]] = defaultdict(list)
    for v in vs:
        by[v.agent or "unknown"].append(v)
    rows_data = []
    for agent, group in by.items():
        succ = sum(1 for v in group if v.status is VersionStatus.SUCCESS)
        regr = sum(1 for v in group if _is_adverse(v))
        rows_data.append((agent, len(group), round(succ / len(group) * 100, 1), regr))
    rows_data.sort(key=lambda r: -r[1])
    return _Result(
        "Versions by agent:",
        ["agent", "versions", "success %", "regressions"],
        [list(r) for r in rows_data],
    )


def _h_recent(vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None) -> _Result:
    n = 12
    rows = [
        [
            v.version_id,
            v.status.value,
            _feature_name(v) or "-",
            f"+{v.lines_added}/-{v.lines_removed}",
            _day(v),
            (v.intent or "-")[:60],
        ]
        for v in reversed(vs[-n:])
    ]
    return _Result(
        f"The {min(n, len(vs))} most recent versions (newest first):",
        ["version", "status", "feature", "churn", "date", "intent"],
        rows,
    )


_METRIC_HINT_RE = re.compile(r"[a-z_][a-z0-9_]{2,}")


def _h_metric_trend(
    vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None
) -> _Result:
    names = {m.name for v in vs for m in v.metrics}
    if not names:
        return _Result("No metrics have been recorded on any version.")
    hinted = set(_METRIC_HINT_RE.findall(low))
    target = next((n for n in names if n.lower() in low), None)
    if target is None:
        target = next((n for n in names if any(h in n.lower() for h in hinted)), None)
    if target is None:
        listing = ", ".join(sorted(names))
        return _Result(f"Which metric? Recorded metrics: {listing}.")
    series = [(v, m) for v in vs for m in v.metrics if m.name == target]
    rows = [[v.version_id, m.before, m.after, _day(v)] for v, m in series]
    first_after = next((m.after for _, m in series if m.after is not None), None)
    last_after = next((m.after for _, m in reversed(series) if m.after is not None), None)
    delta = ""
    if first_after is not None and last_after is not None and first_after != 0:
        pct = (last_after - first_after) / abs(first_after) * 100
        delta = f" - {pct:+.1f}% from {first_after} to {last_after}"
    return _Result(
        f"`{target}` across {len(series)} versions{delta}.",
        ["version", "before", "after", "date"],
        rows,
    )


def _h_failed_approaches(
    vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None
) -> _Result:
    groups: dict[tuple[str, ...], list[DevelopmentVersion]] = defaultdict(list)
    for v in vs:
        if not _is_adverse(v):
            continue
        sig = tuple(sorted(f.path for f in v.changed_files))
        if sig:
            groups[sig].append(v)
    repeats = [(sig, g) for sig, g in groups.items() if len(g) >= 2]
    if not repeats:
        return _Result("No file-set has an adverse outcome recorded more than once.")
    repeats.sort(key=lambda x: -len(x[1]))
    rows = [
        [", ".join(sig)[:80], len(g), " ".join(v.version_id for v in g), (g[0].intent or "-")[:60]]
        for sig, g in repeats[:10]
    ]
    return _Result(
        "File-sets that produced an adverse result more than once:",
        ["files", "times", "versions", "example intent"],
        rows,
    )


def _h_success_rate(
    vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None
) -> _Result:
    succ = sum(1 for v in vs if v.status is VersionStatus.SUCCESS)
    rate = round(succ / len(vs) * 100, 1)
    return _Result(
        f"Overall success rate: {rate}% ({succ} of {len(vs)} versions marked SUCCESS)."
    )


def _h_version_detail(
    vs: list[DevelopmentVersion], low: str, m: re.Match[str] | None
) -> _Result:
    if m is None:
        return _h_recent(vs, low, None)
    vid = f"v{m.group(1)}"
    v = next((x for x in vs if x.version_id == vid), None)
    if v is None:
        return _Result(f"No {vid} in this project (have {vs[0].version_id}-{vs[-1].version_id}).")
    if "chang" in low or "file" in low or "diff" in low:
        rows = [
            [f.path, f.change_type.value if hasattr(f.change_type, "value") else str(f.change_type),
             f"+{f.additions}", f"-{f.deletions}"]
            for f in v.changed_files
        ]
        return _Result(
            f"{vid} changed {len(v.changed_files)} file(s), "
            f"+{v.lines_added}/-{v.lines_removed}:",
            ["path", "type", "add", "del"],
            rows,
        )
    tests = (
        f"{v.tests.passed} passed / {v.tests.failed} failed"
        if v.tests and v.tests.ran
        else "not run"
    )
    metrics = ", ".join(f"{mm.name} {mm.before}->{mm.after}" for mm in v.metrics) or "none"
    text = (
        f"{vid} [{v.status.value}] - {v.intent or 'no intent recorded'}\n"
        f"feature: {_feature_name(v) or '-'}   agent: {v.agent or '-'}   "
        f"commit: {v.git_commit[:12]}   {_day(v)}\n"
        f"changes: {v.files_changed} files, +{v.lines_added}/-{v.lines_removed}\n"
        f"tests: {tests}\nmetrics: {metrics}"
    )
    if v.regressions:
        text += "\nregressions: " + "; ".join(r.detail or r.severity for r in v.regressions)
    return _Result(text)


def _h_biggest(vs: list[DevelopmentVersion], low: str, _m: re.Match[str] | None) -> _Result:
    ordered = sorted(vs, key=lambda v: -(v.lines_added + v.lines_removed))[:12]
    rows = [
        [v.version_id, v.files_changed, f"+{v.lines_added}", f"-{v.lines_removed}", (v.intent or "-")[:60]]
        for v in ordered
    ]
    return _Result(
        "Versions with the largest diffs:",
        ["version", "files", "add", "del", "intent"],
        rows,
    )


def _h_file_history(
    vs: list[DevelopmentVersion], low: str, m: re.Match[str] | None
) -> _Result:
    if m is None:
        return _h_churn(vs, low, None)
    path_frag = m.group(0)
    touching = [v for v in vs if any(path_frag in f.path for f in v.changed_files)]
    if not touching:
        return _Result(f"No recorded version touches a file matching `{path_frag}`.")
    adverse = [v for v in touching if _is_adverse(v)]
    rows = [
        [v.version_id, v.status.value, _day(v), (v.intent or "-")[:60]]
        for v in reversed(touching)
    ]
    verdict = (
        f"{len(adverse)} of {len(touching)} changes here had an adverse outcome - treat with care."
        if adverse
        else f"All {len(touching)} changes here landed cleanly."
    )
    return _Result(
        f"`{path_frag}` has been changed in {len(touching)} version(s). {verdict}",
        ["version", "status", "date", "intent"],
        rows,
    )


def _help_text(vs: list[DevelopmentVersion]) -> str:
    return (
        "I answer common questions from your local history without any API key:\n"
        "  - how many versions / success rate / recent activity\n"
        "  - what regressed, which versions failed tests\n"
        "  - most-churned files, which files change together\n"
        "  - feature breakdown (\"which features regressed the most\")\n"
        "  - agent breakdown, biggest diffs, failed approaches\n"
        "  - a metric over time (name it), or a single version (\"show v7\")\n\n"
        "For open-ended questions, set an LLM API key (OPENROUTER_API_KEY, "
        "GEMINI_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY) where you run "
        "`devmemory serve`, or point DevMemory at a Databricks Genie space."
    )


# --- intent table (first match wins; specific before generic) ------------------

_VERSION_RE = r"\bv(\d{1,4})\b"
_PATHISH_RE = r"[\w./-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|rb|sql|md|json|ya?ml|toml|css|html)"

_INTENTS: list[tuple[Callable[[str], object], Handler]] = [
    # test-failure phrasing before the broad "fail" regression trigger
    (_kw("failed test", "failing test", "test failure", "tests fail", "which tests"), _h_failed_tests),
    (_re(_PATHISH_RE), _h_file_history),
    (_re(_VERSION_RE), _h_version_detail),
    (_kw("didn't work", "did not work", "failed approach", "tried before", "gave up"), _h_failed_approaches),
    (_kw("together", "co-change", "cochange", "same time", "churn", "hot file", "risky file"), _h_churn),
    (_kw("feature"), _h_features),
    (_kw("fail", "broke", "broken", "regress", "worse", "regression"), _h_regressions),
    (_kw("agent", "model ", "who wrote", "who did"), _h_agents),
    (_kw("metric", "latency", "over time", "trend", "how did", "moved", "move"), _h_metric_trend),
    (_kw("success rate", "pass rate", "how often"), _h_success_rate),
    (_kw("recent", "lately", "latest", "last few", "what happened", "activity", "newest"), _h_recent),
    (_kw("biggest", "largest", "most change", "big diff", "huge"), _h_biggest),
    (_kw("how many", "count", "number of", "total"), _h_count),
]


__all__ = ["RulesAskAdapter"]
