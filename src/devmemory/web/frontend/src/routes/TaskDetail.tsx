import { useState } from "react";
import { useParams } from "react-router-dom";
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
import { Badge, Card, PageHead, StatTile } from "@/components/primitives";
import { Icon } from "@/components/Icon";
import { statusTone, statusLabel, type Tone } from "@/lib/status";
import { shortSha, relativeTime } from "@/lib/format";
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

  return (
    <Async query={state}>
      {(s) => (
        <>
          <PageHead
            title={
              <span className="row" style={{ gap: 10 }}>
                <span className="mono">{s.task.id}</span>
                <Badge tone={statusTone(s.overall_status)}>{statusLabel(s.overall_status)}</Badge>
              </span>
            }
            subtitle={s.task.goal}
            actions={
              <>
                <button className="btn" disabled={busy} onClick={() => refresh.mutate()}>
                  {refresh.isPending ? <span className="spinner" /> : <Icon name="refresh" size={14} />}
                  Refresh
                </button>
                <button
                  className="btn btn--primary"
                  disabled={busy}
                  onClick={() => complete.mutate()}
                  title="Runs a full re-check; only reports READY if the evidence supports it"
                >
                  <Icon name="check" size={14} />
                  Evaluate completion
                </button>
              </>
            }
          />

          <StatusBanner s={s} />

          <div className="grid grid--4" style={{ marginTop: 4 }}>
            <StatTile
              label="Requirements"
              value={`${s.requirements.filter((r) => r.status === "COMPLETE").length} / ${s.requirements.length}`}
              icon="target"
            />
            <StatTile
              label="Tests"
              value={s.tests.status === "NOT_RUN" ? "—" : `${s.tests.passed} pass`}
              sub={
                s.tests.status === "NOT_RUN"
                  ? "not run"
                  : `${s.tests.failed} failed · ${statusLabel(s.tests.status)}`
              }
              tone={statusTone(s.tests.status)}
              icon="check"
            />
            <StatTile
              label="Working tree"
              value={s.git.working_tree_clean ? "clean" : "dirty"}
              sub={`${s.git.files_changed} files  +${s.git.lines_added}/-${s.git.lines_deleted}`}
              tone={s.git.working_tree_clean ? "ok" : "warn"}
              icon="commit"
            />
            <StatTile
              label="Impact"
              value={s.impact.available ? `${s.impact.affected_files} files` : "—"}
              sub={s.impact.available ? `${s.impact.affected_tests} tests` : (s.impact.reason ?? "")}
              icon="layers"
            />
          </div>

          <div className="grid grid--2" style={{ alignItems: "start", marginTop: 16 }}>
            <div className="stack">
              <Card title="Requirements" pad>
                {s.requirements.length === 0 && <p className="muted">No requirements.</p>}
                <div className="stack" style={{ gap: 10 }}>
                  {s.requirements.map((r) => (
                    <div key={r.id} className="req-row">
                      <button
                        className={`req-row__status badge badge--${statusTone(r.status)}`}
                        disabled={busy}
                        title="Cycle INCOMPLETE → PARTIAL → COMPLETE"
                        onClick={() => {
                          const next = REQ_CYCLE[(REQ_CYCLE.indexOf(r.status) + 1) % REQ_CYCLE.length];
                          setReq.mutate({ req: r.id, status: next });
                        }}
                      >
                        {statusLabel(r.status)}
                      </button>
                      <div style={{ minWidth: 0 }}>
                        <div>
                          <span className="mono muted">{r.id}</span> {r.description}
                        </div>
                        {r.reason && <div className="muted text-xs">{r.reason}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </Card>

              {s.recommended_focus.length > 0 && (
                <Card title="Recommended focus" pad>
                  <ul className="rec-list">
                    {s.recommended_focus.map((f, i) => (
                      <li key={i}>
                        <Icon name="arrowRight" size={13} /> {f}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {s.findings.length > 0 && s.overall_status !== "READY" && (
                <Card title="Findings" pad>
                  <ul className="warn-list">
                    {s.findings.map((f, i) => (
                      <li key={i}>
                        <Icon name="alert" size={13} /> {f}
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
            </div>

            <div className="stack">
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

          <Card title="State timeline" pad style={{ marginTop: 16 }}>
            <Async
              query={snapshots}
              isEmpty={(rows) => rows.length === 0}
              empty={<p className="muted">No snapshots yet.</p>}
            >
              {(rows) => <Timeline rows={rows} />}
            </Async>
          </Card>
        </>
      )}
    </Async>
  );
}

function StatusBanner({ s }: { s: NormalizedState }) {
  const tone = statusTone(s.overall_status);
  const msg: Record<string, string> = {
    READY: "Requirements satisfied, tests pass, working tree clean. Safe to stop.",
    NEEDS_WORK: "There is concrete unfinished work — see the focus list.",
    BLOCKED: "Cannot safely continue. A human or external decision is needed.",
    IN_PROGRESS: "Actively being worked on. No completion evaluation yet.",
  };
  return (
    <Card
      className={`callout callout--${tone === "ok" ? "ok" : tone === "bad" ? "bad" : tone === "warn" ? "warn" : ""}`}
      pad
      style={{ marginBottom: 16 }}
    >
      <div className="row" style={{ gap: 10, alignItems: "flex-start" }}>
        <Icon name={tone === "ok" ? "check" : tone === "bad" ? "alert" : "target"} size={18} />
        <div>
          <div style={{ fontWeight: 600 }}>{statusLabel(s.overall_status)}</div>
          <div className="muted text-sm">{msg[s.overall_status]}</div>
        </div>
      </div>
    </Card>
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
  const ordered = [...rows].reverse();
  return (
    <div className="tl">
      {ordered.map((r, i) => {
        const tone: Tone = statusTone(r.overall_status);
        return (
          <div key={r.id ?? i} className={`tl__item tl__item--${tone}`}>
            <div className="tl__dot" />
            <div style={{ minWidth: 0 }}>
              <div className="row" style={{ gap: 8 }}>
                <span className="muted mono text-xs">#{i + 1}</span>
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
                {r.checkpoint_id && <span className="mono">ckpt {shortSha(r.checkpoint_id, 8)}</span>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
