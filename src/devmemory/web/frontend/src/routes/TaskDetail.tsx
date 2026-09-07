import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  useTaskState,
  useTaskSnapshots,
  refreshTask,
  completeTask,
  reportIssue,
  resolveIssue,
  setRequirement,
} from "@/api/client";
import { Async } from "@/components/Async";
import { Badge, Card } from "@/components/primitives";
import { Icon } from "@/components/Icon";
import { statusTone, statusLabel, type Tone } from "@/lib/status";
import { shortSha, relativeTime } from "@/lib/format";

/** Tone → the CSS custom property that carries its colour. */
const toneVar = (t: Tone): string =>
  t === "ok" ? "ok" : t === "bad" ? "bad" : t === "warn" ? "warn" : "text";
import {
  m,
  AnimatePresence,
  useReducedMotion,
  spring,
  Pressable,
  DrawCheck,
} from "@/lib/motion";
import type { NormalizedState, RequirementStatus, SnapshotSummary } from "@/api/types";

const REQ_CYCLE: RequirementStatus[] = ["INCOMPLETE", "PARTIAL", "COMPLETE"];

export function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const state = useTaskState(id);
  const snapshots = useTaskSnapshots(id);

  const apply = (data: NormalizedState) => {
    qc.setQueryData(["task-state", id], data);
    qc.invalidateQueries({ queryKey: ["task-snapshots", id] });
    qc.invalidateQueries({ queryKey: ["tasks"] });
  };

  const refresh = useMutation({ mutationFn: () => refreshTask(id!), onSuccess: apply });
  const complete = useMutation({ mutationFn: () => completeTask(id!), onSuccess: apply });
  const setReq = useMutation({
    mutationFn: (v: { req: string; status: string }) => setRequirement(id!, v.req, v.status, "set from dashboard"),
    onSuccess: apply,
  });
  const addIssue = useMutation({
    mutationFn: (v: { description: string; blocking: boolean }) => reportIssue(id!, v.description, v.blocking),
    onSuccess: apply,
  });
  const dropIssue = useMutation({
    mutationFn: (issueId: number) => resolveIssue(id!, issueId),
    onSuccess: apply,
  });

  const busy =
    refresh.isPending ||
    complete.isPending ||
    setReq.isPending ||
    addIssue.isPending ||
    dropIssue.isPending;

  // --- auto-loop: keep refreshing and suggesting the next prompt -----------
  const LOOP_MS = 9000;
  const isTerminal = (st?: string) => st === "READY" || st === "BLOCKED";
  const [auto, setAuto] = useState(() => {
    try {
      return localStorage.getItem(`loop-auto:${id}`) === "1";
    } catch {
      return false;
    }
  });
  const [guardTrip, setGuardTrip] = useState<string | null>(null);
  const prevFindings = useRef<number | null>(null);
  const worseStreak = useRef(0);

  const setMode = (on: boolean) => {
    setAuto(on);
    setGuardTrip(null);
    worseStreak.current = 0;
    try {
      localStorage.setItem(`loop-auto:${id}`, on ? "1" : "0");
    } catch {
      /* ignore */
    }
  };

  const status = state.data?.overall_status;
  const findingsCount = state.data?.findings.length ?? 0;

  // Direction guard: two consecutive refreshes with more findings => stop.
  useEffect(() => {
    if (!state.data) return;
    const prev = prevFindings.current;
    if (prev != null && findingsCount > prev) {
      worseStreak.current += 1;
      if (worseStreak.current >= 2 && auto) {
        setMode(false);
        setGuardTrip(
          "Findings grew on two refreshes in a row — auto-loop paused. Check the direction before resuming.",
        );
      }
    } else if (prev != null) {
      worseStreak.current = 0;
    }
    prevFindings.current = findingsCount;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.dataUpdatedAt]);

  // The loop.
  useEffect(() => {
    if (!auto || !id || !status) return;
    if (isTerminal(status)) {
      setMode(false);
      return;
    }
    const t = setInterval(() => {
      if (!refresh.isPending && !complete.isPending) refresh.mutate();
    }, LOOP_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, id, status, refresh.isPending, complete.isPending]);

  return (
    <Async query={state}>
      {(s) => (
        <>
          <div className="page-head__row" style={{ alignItems: "flex-start" }}>
            <div style={{ minWidth: 0 }}>
              <div className="crumb">
                <Link to="/tasks">Tasks</Link> / <span className="mono">{s.task.id}</span>
              </div>
              <div className="row" style={{ gap: 10 }}>
                <span className="mono" style={{ fontSize: "1rem", fontWeight: 600 }}>
                  {s.task.id}
                </span>
                <Badge tone={statusTone(s.overall_status)}>{statusLabel(s.overall_status)}</Badge>
              </div>
              <div className="h-doc" style={{ marginTop: 8, fontSize: "1.2rem" }}>
                {s.task.goal}
              </div>
            </div>
            <div className="row" style={{ gap: 8, flex: "none" }}>
              <Pressable
                className={`btn${auto ? " btn--primary" : ""}`}
                onClick={() => setMode(!auto)}
                title="Auto: re-run refresh on an interval and keep the loop prompt current. Stops on READY / BLOCKED or if findings regress."
              >
                <Icon name={auto ? "refresh" : "target"} size={14} />
                Auto-loop {auto ? "on" : "off"}
              </Pressable>
              <Pressable className="btn" disabled={busy} onClick={() => refresh.mutate()}>
                <RefreshGlyph spinning={refresh.isPending} />
                Refresh
              </Pressable>
              <Pressable
                className="btn btn--primary"
                disabled={busy}
                onClick={() => complete.mutate()}
                title="Runs a full re-check; only reports READY if the evidence supports it"
              >
                <Icon name="check" size={14} />
                Evaluate completion
              </Pressable>
            </div>
          </div>

          <StatusBanner s={s} />

          <LoopPrompt s={s} auto={auto} guardTrip={guardTrip} refreshing={refresh.isPending} />

          <div className="kpi-strip" style={{ marginTop: 22 }}>
            <div className="kpi">
              <div className="kpi__label">Requirements</div>
              <div className="kpi__value">
                {s.requirements.filter((r) => r.status === "COMPLETE").length} / {s.requirements.length}
              </div>
              <div className="kpi__sub">
                {s.requirements.length === 0
                  ? "none defined"
                  : s.requirements.every((r) => r.status === "COMPLETE")
                    ? "all complete"
                    : "not all met"}
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Tests</div>
              <div
                className="kpi__value"
                style={{ color: `var(--${toneVar(statusTone(s.tests.status))})` }}
              >
                {s.tests.status === "NOT_RUN" ? "—" : `${s.tests.passed} pass`}
              </div>
              <div className="kpi__sub">
                {s.tests.status === "NOT_RUN"
                  ? "not run"
                  : `${s.tests.failed} failed · ${statusLabel(s.tests.status)}`}
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Working tree</div>
              <div
                className="kpi__value kpi__value--word"
                style={{ color: s.git.working_tree_clean ? "var(--ok)" : "var(--warn)" }}
              >
                {s.git.working_tree_clean ? "clean" : "dirty"}
              </div>
              <div className="kpi__sub mono">
                {s.git.files_changed} files · +{s.git.lines_added}/−{s.git.lines_deleted}
              </div>
            </div>
            <div className="kpi">
              <div className="kpi__label">Impact</div>
              <div className="kpi__value">
                {s.impact.available ? `${s.impact.affected_files} files` : "—"}
              </div>
              <div className="kpi__sub">
                {s.impact.available
                  ? `${s.impact.affected_tests} tests · entire graph`
                  : (s.impact.reason ?? "")}
              </div>
            </div>
          </div>

          <div className="split split--wide-rail" style={{ marginTop: 30 }}>
            <div className="stack" style={{ gap: 26 }}>
              <section>
                <div className="h-section" style={{ marginBottom: 12 }}>
                  Requirements
                </div>
                {s.requirements.length === 0 && <p className="muted text-sm">No requirements.</p>}
                <div className="stack" style={{ gap: 0 }}>
                  {s.requirements.map((r) => (
                    <div key={r.id} className="req-row">
                      <Pressable
                        className={`req-row__status badge badge--${statusTone(r.status)}`}
                        disabled={busy}
                        title="Cycle INCOMPLETE → PARTIAL → COMPLETE"
                        onClick={() => {
                          const next = REQ_CYCLE[(REQ_CYCLE.indexOf(r.status) + 1) % REQ_CYCLE.length];
                          setReq.mutate({ req: r.id, status: next });
                        }}
                      >
                        <AnimatePresence mode="wait" initial={false}>
                          <m.span
                            key={r.status}
                            style={{ display: "inline-block" }}
                            initial={{ y: 7, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            exit={{ y: -7, opacity: 0 }}
                            transition={spring.snappy}
                          >
                            {statusLabel(r.status)}
                          </m.span>
                        </AnimatePresence>
                      </Pressable>
                      <div style={{ minWidth: 0 }}>
                        <div>
                          <span className="mono muted">{r.id}</span> {r.description}
                        </div>
                        {r.reason && <div className="muted text-xs">{r.reason}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {s.recommended_focus.length > 0 && (
                <div className="rule rule--accent">
                  <div className="rule__label">Recommended focus</div>
                  <ul className="rec-list" style={{ marginTop: 4 }}>
                    {s.recommended_focus.map((f, i) => (
                      <li key={i}>
                        <Icon name="arrowRight" size={13} /> {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {s.findings.length > 0 && s.overall_status !== "READY" && (
                <div className="rule rule--warn">
                  <div className="rule__label">Findings</div>
                  <ul className="warn-list" style={{ marginTop: 4 }}>
                    {s.findings.map((f, i) => (
                      <li key={i}>
                        <Icon name="alert" size={13} /> {f}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="rail">
              <Card title="Git & checkpoint" pad>
                <dl className="kv">
                  <dt>branch</dt>
                  <dd className="mono">{s.git.branch}</dd>
                  <dt>commit</dt>
                  <dd>
                    <span className="mono">{shortSha(s.git.commit_sha)}</span>
                    {s.git.commit_subject && <span className="muted"> {s.git.commit_subject}</span>}
                  </dd>
                  <dt>checkpoint</dt>
                  <dd className="mono">
                    {s.checkpoint.current_id ? (
                      shortSha(s.checkpoint.current_id, 12)
                    ) : (
                      <span className="muted">none</span>
                    )}
                  </dd>
                  {s.checkpoint.session_id && (
                    <>
                      <dt>session</dt>
                      <dd className="mono">{shortSha(s.checkpoint.session_id, 12)}</dd>
                    </>
                  )}
                  {s.tests.command && (
                    <>
                      <dt>tests</dt>
                      <dd className="mono text-xs">{s.tests.command}</dd>
                    </>
                  )}
                </dl>
              </Card>

              <Issues
                s={s}
                busy={busy}
                onAdd={(description, blocking) => addIssue.mutate({ description, blocking })}
                onResolve={(issueId) => dropIssue.mutate(issueId)}
              />
            </div>
          </div>

          <hr className="sep" />

          <section>
            <div className="h-section" style={{ marginBottom: 14 }}>
              State timeline
            </div>
            <Async
              query={snapshots}
              isEmpty={(rows) => rows.length === 0}
              empty={<p className="muted text-sm">No snapshots yet.</p>}
            >
              {(rows) => <Timeline rows={rows} />}
            </Async>
          </section>
        </>
      )}
    </Async>
  );
}

function buildLoopPrompt(s: NormalizedState): string {
  const lines: string[] = [
    `Continue task ${s.task.id}: ${s.task.goal}`,
    `State right now: ${s.overall_status}.`,
  ];
  if (s.recommended_focus.length) {
    lines.push("", "Do next:");
    s.recommended_focus.forEach((f) => lines.push(`- ${f}`));
  }
  const open = s.requirements.filter((r) => r.status !== "COMPLETE");
  if (open.length) {
    lines.push("", "Requirements not yet met:");
    open.forEach((r) => lines.push(`- ${r.id}: ${r.description}${r.reason ? ` (${r.reason})` : ""}`));
  }
  if (s.findings.length) {
    lines.push("", "Findings from the last state refresh:");
    s.findings.forEach((f) => lines.push(`- ${f}`));
  }
  lines.push("", "When done: commit with a clear message, then the loop re-checks.");
  return lines.join("\n");
}

function LoopPrompt({
  s,
  auto,
  guardTrip,
  refreshing,
}: {
  s: NormalizedState;
  auto: boolean;
  guardTrip: string | null;
  refreshing: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const terminal = s.overall_status === "READY" || s.overall_status === "BLOCKED";
  const prompt = buildLoopPrompt(s);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked */
    }
  };

  return (
    <Card
      title="Loop prompt"
      action={
        <Badge tone={auto ? "ok" : "neutral"}>
          {auto ? (refreshing ? "auto · refreshing" : "auto") : "manual"}
        </Badge>
      }
      pad
      style={{ marginTop: 22 }}
    >
      {guardTrip && (
        <p className="callout callout--warn" style={{ padding: "8px 10px", marginTop: 0 }}>
          <Icon name="alert" size={13} /> {guardTrip}
        </p>
      )}
      {terminal ? (
        <p className="muted text-sm" style={{ margin: 0 }}>
          {s.overall_status === "READY"
            ? "Task is READY — nothing to send back."
            : "Task is BLOCKED — a human decision is needed before the loop continues."}
        </p>
      ) : (
        <>
          <pre className="loop-prompt">{prompt}</pre>
          <div className="row" style={{ gap: 8, marginTop: 10, flexWrap: "wrap" }}>
            <button className="btn" onClick={copy}>
              <Icon name="copy" size={14} /> {copied ? "Copied" : "Copy for IDE"}
            </button>
            {auto && (
              <span className="text-xs muted">
                auto-refreshing every 9s — stops on READY / BLOCKED, or if findings regress
              </span>
            )}
          </div>
        </>
      )}
    </Card>
  );
}

function RefreshGlyph({ spinning }: { spinning: boolean }) {
  const reduce = useReducedMotion();
  return (
    <span style={{ position: "relative", width: 14, height: 14, display: "inline-flex" }}>
      <m.span
        style={{ display: "inline-flex" }}
        animate={spinning && !reduce ? { rotate: 360 } : { rotate: 0 }}
        transition={
          spinning && !reduce
            ? { duration: 0.9, repeat: Infinity, ease: "linear" }
            : { type: "spring", stiffness: 300, damping: 20 }
        }
      >
        <Icon name="refresh" size={14} />
      </m.span>
      {spinning && !reduce && (
        <m.span
          style={{
            position: "absolute",
            inset: -4,
            borderRadius: "50%",
            border: "1.5px solid currentColor",
          }}
          initial={{ opacity: 0.5, scale: 0.7 }}
          animate={{ opacity: 0, scale: 1.4 }}
          transition={{ duration: 1, repeat: Infinity, ease: "easeOut" }}
        />
      )}
    </span>
  );
}

function StatusBanner({ s }: { s: NormalizedState }) {
  const reduce = useReducedMotion();
  const tone = statusTone(s.overall_status);
  const msg: Record<string, string> = {
    READY: "Requirements satisfied, tests pass, working tree clean. Safe to stop.",
    NEEDS_WORK: "There is concrete unfinished work — see the focus list.",
    BLOCKED: "Cannot safely continue. A human or external decision is needed.",
    IN_PROGRESS: "Actively being worked on. No completion evaluation yet.",
  };
  const isReady = s.overall_status === "READY";
  return (
    <div style={{ marginTop: 22, overflow: "hidden" }}>
      <AnimatePresence mode="wait" initial={false}>
        <m.div
          key={s.overall_status}
          initial={reduce ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduce ? { opacity: 0 } : { opacity: 0, y: -8 }}
          transition={isReady ? spring.bouncy : spring.gentle}
        >
          {/* the read of the task, in the same voice as the rest of the app */}
          <p className="lead lead--sm" style={{ margin: 0 }}>
            {msg[s.overall_status] ?? statusLabel(s.overall_status)}
          </p>
          <div
            className={`rule rule--${tone === "ok" ? "ok" : tone === "bad" ? "bad" : tone === "warn" ? "warn" : "accent"} row`}
            style={{ gap: 9, marginTop: 14, fontSize: "0.8125rem", color: "var(--text-strong)" }}
          >
            {isReady ? (
              <DrawCheck size={15} />
            ) : (
              <Icon name={tone === "bad" ? "alert" : "target"} size={15} />
            )}
            <span
              style={{
                fontWeight: 600,
                color: `var(--${tone === "ok" ? "ok" : tone === "bad" ? "bad" : tone === "warn" ? "warn" : "accent-text"})`,
              }}
            >
              {statusLabel(s.overall_status).toUpperCase()}
            </span>
            {s.refreshed_at && (
              <span className="muted">· refreshed {relativeTime(s.refreshed_at)}</span>
            )}
          </div>
        </m.div>
      </AnimatePresence>
    </div>
  );
}

function Issues({
  s,
  busy,
  onAdd,
  onResolve,
}: {
  s: NormalizedState;
  busy: boolean;
  onAdd: (d: string, blocking: boolean) => void;
  onResolve: (id: number) => void;
}) {
  const [draft, setDraft] = useState("");
  const [blocking, setBlocking] = useState(false);
  return (
    <Card title={`Unresolved · ${s.unresolved.length}`} pad>
      {s.unresolved.length === 0 && <p className="muted">Nothing open.</p>}
      <div className="stack" style={{ gap: 8 }}>
        {s.unresolved.map((i) => (
          <div key={i.id} className="row" style={{ gap: 8, alignItems: "flex-start" }}>
            <Badge tone={i.blocking ? "bad" : "neutral"} dot={false}>
              {i.blocking ? "blocking" : i.kind}
            </Badge>
            <span style={{ flex: 1, minWidth: 0 }}>{i.description}</span>
            {i.id != null && i.kind === "agent" && (
              <button className="btn btn--sm" disabled={busy} onClick={() => onResolve(i.id!)}>
                resolve
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="row" style={{ gap: 6, marginTop: 12 }}>
        <input
          className="input"
          placeholder="Describe a blocker or open question"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <label className="row text-xs muted" style={{ gap: 4, whiteSpace: "nowrap" }}>
          <input type="checkbox" checked={blocking} onChange={(e) => setBlocking(e.target.checked)} />
          blocking
        </label>
        <button
          className="btn"
          disabled={busy || !draft.trim()}
          onClick={() => {
            onAdd(draft.trim(), blocking);
            setDraft("");
            setBlocking(false);
          }}
        >
          Add
        </button>
      </div>
    </Card>
  );
}

function Timeline({ rows }: { rows: SnapshotSummary[] }) {
  const reduce = useReducedMotion();
  // newest first, so a fresh snapshot slides in at the top and nudges the rest down
  const ordered = [...rows].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
  const total = ordered.length;
  return (
    <div className="tl">
      <AnimatePresence initial={false}>
        {ordered.map((r, i) => {
          const tone: Tone = statusTone(r.overall_status);
          return (
            <m.div
              key={r.id ?? `i${i}`}
              className={`tl__item tl__item--${tone}`}
              initial={reduce ? false : { opacity: 0, x: 18 }}
              animate={{ opacity: 1, x: 0 }}
              exit={reduce ? { opacity: 0 } : { opacity: 0, x: 18 }}
              transition={spring.gentle}
            >
              <div className="tl__dot" />
              <div style={{ minWidth: 0 }}>
                <div className="row" style={{ gap: 8 }}>
                  <span className="muted mono text-xs">#{total - i}</span>
                  <Badge tone={tone}>{statusLabel(r.overall_status)}</Badge>
                  <span className="muted text-xs">{relativeTime(r.created_at)}</span>
                </div>
                <div className="tl__sub">
                  <span className="mono">{shortSha(r.commit_sha)}</span>
                  <span>
                    tests {r.tests_passed}/{r.tests_failed}
                  </span>
                  <span>
                    reqs {r.requirements_complete}/{r.requirements_total}
                  </span>
                  {r.checkpoint_id && (
                    <span className="mono">ckpt {shortSha(r.checkpoint_id, 8)}</span>
                  )}
                </div>
              </div>
            </m.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
