"""Local "Ask" - a Databricks-free chat layer over the project's own SQLite DB.

When no Genie space is configured, the dashboard's Ask page falls back to this:
the configured LLM writes a single read-only SQL query against the local
metadata database, DevMemory runs it (read-only connection + a keyword guard),
and the LLM turns the rows into a short plain-English answer.

What leaves the machine: the database *schema* (DDL, no data), the question, the
generated SQL, and the result rows - sent to whichever LLM provider has a key
(the same providers the analysis chain uses). Nothing else. With no key and no
Genie space, :attr:`LocalAskAdapter.is_available` is ``False`` and the dashboard
shows how to enable one.
"""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from typing import Any

from devmemory.adapters import local_model as lm
from devmemory.adapters.genie import GenieAnswer
from devmemory.analysis.llm import call_llm
from devmemory.config import resolve_llm_api_key
from devmemory.logging import get_logger
from devmemory.services.context import ProjectContext

_log = get_logger(__name__)

_MAX_ROWS = 50
_CLOUD_PROVIDERS = ("anthropic", "openai", "gemini", "openrouter")
_KNOWN_PROVIDERS = ("local", *_CLOUD_PROVIDERS)

_WRITE_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|replace|pragma|vacuum|reindex)\b",
    re.IGNORECASE,
)
_READ_START_RE = re.compile(r"^\s*(with|select)\b", re.IGNORECASE)

_SQL_SYSTEM = (
    "You translate a question about a software project's development history into "
    "exactly ONE read-only SQLite query. Rules: a single SELECT (a leading WITH is "
    "fine); never write; never use multiple statements; never use PRAGMA. Prefer "
    "explicit column lists and readable aliases. Add a sensible LIMIT (<= 50) "
    "unless the question asks for a single aggregate. Reply with ONLY a JSON "
    'object: {"sql": "<query>", "explanation": "<one sentence, plain English>"}.'
)
_ANSWER_SYSTEM = (
    "You answer a question about a software project using the result of a SQL "
    "query that has already been run for you. Be concise and concrete, and cite "
    "the actual numbers from the rows. If the rows are empty, say so plainly. "
    "Plain text - no markdown tables."
)

# Local mode keeps no server-side state except this small conversation buffer,
# so follow-up questions ("and which of those failed?") have a little context.
_HISTORY: dict[str, list[tuple[str, str]]] = {}
_HISTORY_MAX = 200


class _UnsafeQueryError(RuntimeError):
    """The generated SQL did not pass the read-only guard."""


class LocalAskAdapter:
    def __init__(self, ctx: ProjectContext) -> None:
        self._ctx = ctx

    # -- availability ----------------------------------------------------

    def _local_model_ready(self) -> bool:
        return self._ctx.config.local_model.enabled and lm.is_ready(self._ctx.config.local_model)

    def _providers(self) -> list[str]:
        """The analysis provider chain, then any other usable provider. The
        on-device model goes first when it's ready, so the default path needs
        no key; a configured cloud preference still wins if it comes earlier."""
        chain = [p.strip().lower() for p in self._ctx.config.analysis.providers]
        ordered = [p for p in chain if p in _KNOWN_PROVIDERS]
        if self._local_model_ready() and "local" not in ordered:
            ordered.insert(0, "local")
        ordered += [p for p in _CLOUD_PROVIDERS if p not in ordered]
        return ordered

    def _first_usable_provider(self) -> str | None:
        for p in self._providers():
            if p == "local" and self._local_model_ready():
                return "local"
            if p != "local" and resolve_llm_api_key(p):
                return p
        return None

    @property
    def is_available(self) -> bool:
        return self._first_usable_provider() is not None

    @property
    def is_offline(self) -> bool:
        """True when the answering engine runs entirely on this machine."""
        return self._first_usable_provider() == "local"

    def unavailable_reason(self) -> str | None:
        if self.is_available:
            return None
        return (
            "no local model and no LLM API key - run `devmemory model pull` for an "
            "on-device model, or set ANTHROPIC_API_KEY / OPENAI_API_KEY / "
            "GEMINI_API_KEY / OPENROUTER_API_KEY (or configure a Databricks Genie space)"
        )

    @property
    def engine_label(self) -> str:
        provider = self._first_usable_provider()
        if provider == "local":
            name = self._ctx.config.local_model.filename.removesuffix(".gguf")
            return f"on-device - {name}"
        return f"local - {provider or 'LLM'} (text-to-SQL over SQLite)"

    # -- schema --------------------------------------------------------

    def _schema(self) -> str:
        rows = self._ctx.db.query(
            "SELECT sql FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%' "
            "AND name NOT LIKE '%_config' AND name NOT LIKE '%_data' "
            "AND name NOT LIKE '%_idx' AND name NOT LIKE '%_content' "
            "AND name NOT LIKE '%_docsize' AND sql IS NOT NULL ORDER BY name"
        )
        return "\n\n".join(r["sql"].strip() for r in rows if r["sql"])

    # -- one chat turn ------------------------------------------------

    def ask(self, question: str, *, conversation_id: str | None = None) -> GenieAnswer:
        question = question.strip()
        providers = self._providers()
        model = self._ctx.config.analysis.model
        conv = conversation_id or uuid.uuid4().hex
        prior = _HISTORY.get(conv, [])
        answer = GenieAnswer(question=question, conversation_id=conv)

        context = ""
        if prior:
            context = (
                "EARLIER IN THIS CONVERSATION:\n"
                + "\n".join(f"Q: {q}\nA: {a}" for q, a in prior[-3:])
                + "\n\n"
            )

        sql_prompt = (
            f"{context}SQLite schema:\n{self._schema()}\n\n"
            f"Question: {question}\n\nReturn the JSON now."
        )
        raw = call_llm(
            sql_prompt,
            system=_SQL_SYSTEM,
            providers=providers,
            model=model,
            local_model=self._ctx.config.local_model,
        )
        if not raw:
            answer.error = "no LLM provider answered (check API keys and rate limits)"
            return answer

        sql, explanation = _parse_sql(raw)
        if not sql:
            answer.error = "the LLM did not return a usable query"
            answer.text = raw.strip()[:500] or None
            return answer
        answer.sql = sql
        answer.sql_description = explanation

        try:
            columns, rows = self._run_readonly(sql)
        except _UnsafeQueryError as exc:
            answer.error = f"refused to run the generated query: {exc}"
            return answer
        except sqlite3.Error as exc:
            answer.error = f"query failed: {exc}"
            return answer

        answer.columns = columns
        answer.row_count = len(rows)
        answer.truncated = len(rows) > _MAX_ROWS
        answer.rows = [list(r) for r in rows[:_MAX_ROWS]]

        summary_prompt = (
            f"Question: {question}\n\nSQL that was run:\n{sql}\n\n"
            f"Columns: {columns}\n"
            f"Rows (JSON): {json.dumps(answer.rows, default=str)[:6000]}\n\n"
            "Write the answer now."
        )
        text = call_llm(
            summary_prompt,
            system=_ANSWER_SYSTEM,
            providers=providers,
            model=model,
            local_model=self._ctx.config.local_model,
        )
        answer.text = (text or explanation or "").strip() or None

        if len(_HISTORY) < _HISTORY_MAX or conv in _HISTORY:
            _HISTORY[conv] = [*prior, (question, answer.text or "")][-6:]
        _log.info("local_ask.answer", rows=len(answer.rows), truncated=answer.truncated)
        return answer

    # -- guarded execution -----------------------------------------

    def _run_readonly(self, sql: str) -> tuple[list[str], list[tuple[Any, ...]]]:
        stripped = sql.strip().rstrip(";").strip()
        if ";" in stripped:
            raise _UnsafeQueryError("multiple statements are not allowed")
        if not _READ_START_RE.match(stripped):
            raise _UnsafeQueryError("only SELECT / WITH queries are allowed")
        if _WRITE_RE.search(stripped):
            raise _UnsafeQueryError("the query contains a write keyword")

        # A separate, genuinely read-only connection - not the shared one.
        uri = f"file:{self._ctx.paths.db.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5.0)
        try:
            cur = conn.execute(stripped)
            cols = [d[0] for d in (cur.description or [])]
            fetched = cur.fetchmany(_MAX_ROWS + 1)
            return cols, fetched
        finally:
            conn.close()


# --- helpers ----------------------------------------------------------------------


def _parse_sql(raw: str) -> tuple[str | None, str | None]:
    data = _json_object(raw)
    if data is None:
        return None, None
    sql = str(data.get("sql") or "").strip()
    explanation = str(data.get("explanation") or "").strip() or None
    return (sql or None), explanation


def _json_object(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1].removeprefix("json").strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


__all__ = ["LocalAskAdapter"]
