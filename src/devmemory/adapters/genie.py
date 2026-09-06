"""Databricks Genie - a natural-language chat layer over the published telemetry.

Genie answers questions in plain English against a *Genie space* that sits on
top of the ``devmemory.analytics`` Delta tables (see
:mod:`devmemory.adapters.databricks`). This adapter is a thin wrapper over the
Databricks SDK's Genie Conversation API: one call per turn, returning the
answer text, the SQL Genie ran, and a small preview of the rows.

Everything degrades gracefully (§21): with no credentials, no ``databricks``
extra, or no space id, :attr:`GenieAdapter.is_configured` is ``False`` and the
dashboard simply hides the chat.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from devmemory.config import DevMemoryConfig, resolve_databricks_credentials
from devmemory.domain.errors import DatabricksError
from devmemory.logging import get_logger

if TYPE_CHECKING:
    from databricks.sdk import WorkspaceClient

_log = get_logger(__name__)

_MAX_ROWS = 50


class GenieUnavailableError(DatabricksError):
    """Genie is not configured, the SDK is missing, or the space is unreachable."""


class GenieAnswer(BaseModel):
    conversation_id: str | None = None
    message_id: str | None = None
    question: str
    text: str | None = None
    sql: str | None = None
    sql_description: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int | None = None
    truncated: bool = False
    error: str | None = None


class GenieAdapter:
    def __init__(self, config: DevMemoryConfig) -> None:
        self._config = config
        self._space_id = (
            os.environ.get("DATABRICKS_GENIE_SPACE_ID") or config.databricks.genie_space_id or ""
        ).strip()
        self._client: WorkspaceClient | None = None

    @property
    def space_id(self) -> str:
        return self._space_id

    @property
    def is_configured(self) -> bool:
        return bool(self._space_id) and resolve_databricks_credentials() is not None

    def unavailable_reason(self) -> str | None:
        if not self._space_id:
            return "no Genie space configured (set databricks.genie_space_id or DATABRICKS_GENIE_SPACE_ID)"
        if resolve_databricks_credentials() is None:
            return "Databricks credentials are not set (DATABRICKS_HOST / DATABRICKS_TOKEN)"
        return None

    # -- connection ---------------------------------------------------

    def _workspace(self) -> WorkspaceClient:
        if self._client is not None:
            return self._client
        creds = resolve_databricks_credentials()
        if creds is None:
            raise GenieUnavailableError("Databricks credentials are not set.")
        try:
            from databricks.sdk import WorkspaceClient
        except ImportError as exc:  # pragma: no cover - extra not installed
            raise GenieUnavailableError(
                "the databricks extra is not installed",
                hint="pip install 'devmemory-cli[databricks]'",
            ) from exc
        self._client = WorkspaceClient(host=creds.host, token=creds.token)
        return self._client

    # -- one chat turn ----------------------------------------------

    def ask(self, question: str, *, conversation_id: str | None = None) -> GenieAnswer:
        """Send one question and wait for the answer. Pass ``conversation_id`` to
        continue an existing thread (Genie keeps the earlier context)."""
        if not self._space_id:
            raise GenieUnavailableError("no Genie space configured")
        w = self._workspace()
        q = question.strip()
        try:
            if conversation_id:
                msg = w.genie.create_message_and_wait(self._space_id, conversation_id, q)
            else:
                msg = w.genie.start_conversation_and_wait(self._space_id, q)
        except Exception as exc:
            raise GenieUnavailableError(f"Genie request failed: {exc}") from exc

        answer = GenieAnswer(
            question=q,
            conversation_id=msg.conversation_id,
            message_id=msg.message_id,
            error=msg.error.error if msg.error is not None else None,
        )
        self._fill_from_attachments(w, msg, answer)
        _log.info(
            "genie.answer",
            space=self._space_id,
            conversation=answer.conversation_id,
            has_sql=answer.sql is not None,
            rows=len(answer.rows),
        )
        return answer

    def _fill_from_attachments(
        self, w: WorkspaceClient, msg: Any, answer: GenieAnswer
    ) -> None:
        for att in msg.attachments or []:
            if getattr(att, "text", None) and att.text.content:
                answer.text = (answer.text or "") + att.text.content
            query = getattr(att, "query", None)
            if query is None:
                continue
            answer.sql = query.query
            answer.sql_description = query.description
            if not answer.text and query.description:
                answer.text = query.description
            try:
                self._attach_rows(w, msg, att.attachment_id, answer)
            except Exception as exc:  # results are best-effort
                _log.warning("genie.results_failed", error=str(exc))

    def _attach_rows(
        self, w: WorkspaceClient, msg: Any, attachment_id: str, answer: GenieAnswer
    ) -> None:
        res = w.genie.get_message_query_result_by_attachment(
            self._space_id, msg.conversation_id, msg.message_id, attachment_id
        )
        sr = res.statement_response
        if sr is None:
            return
        schema = sr.manifest.schema if sr.manifest else None
        cols = (schema.columns or []) if schema else []
        answer.columns = [c.name for c in cols if c.name]
        data = (sr.result.data_array if sr.result else None) or []
        answer.row_count = len(data)
        answer.truncated = len(data) > _MAX_ROWS
        answer.rows = [list(r) for r in data[:_MAX_ROWS]]


__all__ = ["GenieAdapter", "GenieAnswer", "GenieUnavailableError"]
