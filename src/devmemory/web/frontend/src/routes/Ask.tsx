import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useGenieStatus, askGenie, useAnalytics, useVersions } from "@/api/client";
import { Card, PageHead, EmptyState } from "@/components/primitives";
import { Icon } from "@/components/Icon";
import { m, AnimatePresence, useReducedMotion, spring, ThinkingDots } from "@/lib/motion";
import type { GenieAnswer, AnalyticsSummary, VersionListItem } from "@/api/types";

type Turn =
  | { role: "user"; text: string }
  | { role: "genie"; answer: GenieAnswer }
  | { role: "error"; text: string };

/**
 * Openers drawn from this project's own history — a real feature, a real file, a
 * real metric name — so the first click asks something that actually has an
 * answer here. Falls back to shape-only questions on an empty project.
 */
function suggestions(a: AnalyticsSummary | undefined, versions: VersionListItem[]): string[] {
  const out = ["Which features regressed the most?", "Show every version that failed tests, newest first"];
  const feature = a?.features.find((f) => f.regressions > 0)?.feature ?? a?.features[0]?.feature;
  if (feature) out.push(`What happened in ${feature}?`);
  const file = a?.file_churn[0]?.path;
  if (file) out.push(`Which versions touched ${file}?`);
  else out.push("What files change together most often?");
  const metric = versions.find((v) => Object.keys(v.metrics ?? {}).length)?.metrics;
  const name = metric ? Object.keys(metric)[0] : null;
  if (name) out.push(`How did ${name} move over time?`);
  return out.slice(0, 4);
}

function errorDetail(message: string): string {
  try {
    const parsed = JSON.parse(message);
    if (parsed && typeof parsed.detail === "string") return parsed.detail;
  } catch {
    /* not json */
  }
  return message;
}

export function Ask() {
  const reduce = useReducedMotion();
  const status = useGenieStatus();
  const analytics = useAnalytics();
  const versions = useVersions(200);
  const openers = suggestions(analytics.data, versions.data ?? []);
  const mode = status.data?.mode ?? "none";
  const engineLabel = mode === "genie" ? "Genie" : "Ask";
  const subtitle =
    mode === "genie"
      ? "Natural-language questions over your development history, answered by Databricks Genie against the devmemory.analytics tables."
      : mode === "local"
        ? "Natural-language questions over your development history. A local LLM writes SQL against your DevMemory database and explains the result - no Databricks needed."
        : "Common questions about your development history, answered straight from your local data - no API key needed.";
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (q: string) => askGenie(q, conversationId),
    onSuccess: (answer) => {
      if (answer.conversation_id) setConversationId(answer.conversation_id);
      setTurns((t) => [...t, { role: "genie", answer }]);
    },
    onError: (err: Error) => {
      setTurns((t) => [...t, { role: "error", text: errorDetail(err.message) }]);
    },
  });

  useEffect(() => {
    scrollerRef.current?.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: "smooth" });
  }, [turns, ask.isPending]);

  const send = (q: string) => {
    const question = q.trim();
    if (!question || ask.isPending) return;
    setTurns((t) => [...t, { role: "user", text: question }]);
    setDraft("");
    ask.mutate(question);
  };

  const newChat = () => {
    setTurns([]);
    setConversationId(null);
  };

  return (
    /* A conversation is reading-width, not dashboard-width. */
    <div style={{ maxWidth: 900 }}>
      <PageHead
        title="Ask"
        subtitle={subtitle}
        actions={
          turns.length > 0 ? (
            <button className="btn" onClick={newChat}>
              <Icon name="plus" size={14} /> New chat
            </button>
          ) : undefined
        }
      />

      {status.data && !status.data.configured ? (
        <Card title="Ask is not configured" pad>
          <p className="text-sm">{status.data.reason}</p>
          <p className="muted text-sm">
            The quickest path is a local LLM - set any one API key in the environment (or a{" "}
            <code>.env</code> next to where you run <code>devmemory serve</code>):
          </p>
          <pre className="loop-prompt">{`# any one of these enables Ask, no Databricks required
OPENROUTER_API_KEY=sk-or-...
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...`}</pre>
          <p className="muted text-sm">
            Or point DevMemory at a Databricks Genie space for warehouse-scale queries:
          </p>
          <pre className="loop-prompt">{`# .devmemory/config.json
"databricks": { "enabled": true, "genie_space_id": "01ef..." }

# or the environment
DATABRICKS_HOST=...       DATABRICKS_TOKEN=...
DATABRICKS_GENIE_SPACE_ID=01ef...`}</pre>
        </Card>
      ) : (
        <Card flush>
          <div className="chat" ref={scrollerRef}>
            {turns.length === 0 && (
              <div className="chat__empty">
                <EmptyState
                  icon="sparkles"
                  title="Ask about your project"
                  sub={
                    mode === "local"
                      ? "A local LLM writes the SQL, DevMemory runs it read-only, and the LLM explains the result."
                      : mode === "genie"
                        ? "Genie writes the SQL, runs it on Databricks, and explains the result."
                        : "Pick a question below, or ask about versions, regressions, tests, files, features, agents or a metric over time."
                  }
                />
                {status.data?.engine && (
                  <p className="muted text-xs" style={{ marginTop: 4 }}>
                    engine: {status.data.engine}
                    {status.data.offline && " · runs on this machine, nothing leaves"}
                  </p>
                )}
                {mode === "rules" && status.data?.reason && (
                  <p className="muted text-xs" style={{ marginTop: 6, maxWidth: 460 }}>
                    {status.data.reason}
                  </p>
                )}
                <div className="chat__suggest">
                  {openers.map((s) => (
                    <button key={s} className="chip" onClick={() => send(s)}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <AnimatePresence initial={false}>
              {turns.map((turn, i) => (
                <m.div
                  key={i}
                  initial={reduce ? false : { opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={spring.gentle}
                >
                  <TurnView turn={turn} engineLabel={engineLabel} />
                </m.div>
              ))}
            </AnimatePresence>

            {ask.isPending && (
              <m.div
                className="chat__msg chat__msg--genie"
                initial={reduce ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={spring.gentle}
              >
                <div className="chat__role">{engineLabel}</div>
                <div className="chat__body row" style={{ gap: 8, color: "var(--text-muted)" }}>
                  <ThinkingDots /> thinking…
                </div>
              </m.div>
            )}
          </div>

          <form
            className="chat__input"
            onSubmit={(e) => {
              e.preventDefault();
              send(draft);
            }}
          >
            <input
              className="input"
              placeholder="Ask a question about this project…"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={ask.isPending || !status.data?.configured}
            />
            <button
              className="btn btn--primary"
              type="submit"
              disabled={ask.isPending || !draft.trim() || !status.data?.configured}
            >
              <Icon name="arrowRight" size={15} />
            </button>
          </form>
        </Card>
      )}
    </div>
  );
}

function TurnView({ turn, engineLabel }: { turn: Turn; engineLabel: string }) {
  if (turn.role === "user") {
    return (
      <div className="chat__msg chat__msg--user">
        <div className="chat__body">{turn.text}</div>
      </div>
    );
  }
  if (turn.role === "error") {
    return (
      <div className="chat__msg chat__msg--genie">
        <div className="chat__role">{engineLabel}</div>
        <div className="chat__body callout callout--bad" style={{ padding: "8px 10px" }}>
          <Icon name="alert" size={13} /> {turn.text}
        </div>
      </div>
    );
  }

  const a = turn.answer;
  return (
    <div className="chat__msg chat__msg--genie">
      <div className="chat__role">{engineLabel}</div>
      <div className="chat__body stack" style={{ gap: 10 }}>
        {a.error && (
          <div className="callout callout--bad" style={{ padding: "8px 10px" }}>
            <Icon name="alert" size={13} /> {a.error}
          </div>
        )}
        {a.text && <div style={{ whiteSpace: "pre-wrap" }}>{a.text}</div>}
        {a.rows.length > 0 && <ResultTable columns={a.columns} rows={a.rows} />}
        {(a.row_count != null || a.truncated) && (
          <div className="muted text-xs">
            {a.row_count ?? a.rows.length} row{(a.row_count ?? a.rows.length) === 1 ? "" : "s"}
            {a.truncated && ` · showing first ${a.rows.length}`}
          </div>
        )}
        {a.sql && (
          <details className="chat__sql">
            <summary>SQL</summary>
            <pre className="loop-prompt">{a.sql}</pre>
          </details>
        )}
        {!a.text && !a.rows.length && !a.sql && !a.error && (
          <div className="muted">No answer returned.</div>
        )}
      </div>
    </div>
  );
}

function ResultTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  return (
    <div className="dm-table__scroll">
      <table className="dm-table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {r.map((cell, j) => (
                <td key={j} className="mono text-xs">
                  {cell == null ? <span className="muted">null</span> : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
