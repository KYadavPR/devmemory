import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  useTrace,
  useVersion,
  useVersionAttempts,
  useVersionDiff,
  useVersionImpact,
} from "@/api/client";
import { Async } from "@/components/Async";
import { Card, PageHead, StatusBadge, Badge, Sha, Skeleton } from "@/components/primitives";
import { DiffView } from "@/components/DiffView";
import { AttemptCard } from "@/components/AttemptCard";
import { Icon } from "@/components/Icon";
import { absTime, featureName, shortSha, vlabel } from "@/lib/format";
import { metricTrend, riskTone } from "@/lib/status";
import type { ChangedEntity, DevelopmentVersion, TraceNode } from "@/api/types";

const SECTIONS = [
  ["trace", "Trace"],
  ["changes", "Changes"],
  ["risk", "Risk"],
  ["analysis", "Analysis"],
  ["diff", "Diff"],
] as const;

export function VersionDetail() {
  const { id } = useParams<{ id: string }>();
  const version = useVersion(id);
  const trace = useTrace(id);
  const attempts = useVersionAttempts(id);
  const impact = useVersionImpact(id);
  const diff = useVersionDiff(id);

  const [activeSection, setActiveSection] = useState<string>("trace");

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActiveSection(e.target.id);
        }
      },
      { rootMargin: "-80px 0px -70% 0px" },
    );
    SECTIONS.forEach(([s]) => {
      const el = document.getElementById(s);
      if (el) obs.observe(el);
    });
    return () => obs.disconnect();
  }, [version.data, diff.data]);

  return (
    <Async query={version} skeleton={<Skeleton h={140} r="var(--r-3)" />}>
      {(v) => {
        const hasRisk =
          (attempts.data?.length ?? 0) > 0 ||
          (impact.data?.entities.length ?? 0) > 0 ||
          v.regressions.length > 0;
        return (
          <>
            <PageHead
              title={
                <span className="row" style={{ gap: 10 }}>
                  {vlabel(v.version_id)}
                  <StatusBadge status={v.status} />
                </span>
              }
              subtitle={v.intent ?? "No recorded intent"}
              actions={
                <Link className="btn btn--sm" to={`/compare/${v.version_id}...${v.version_id}`}>
                  <Icon name="compare" size={14} /> Compare
                </Link>
              }
            />

            <nav className="subnav">
              {SECTIONS.filter(([s]) => (s === "risk" ? hasRisk : s === "diff" ? diff.data : true)).map(
                ([s, label]) => (
                  <a
                    key={s}
                    href={`#${s}`}
                    className={`subnav__link${activeSection === s ? " subnav__link--active" : ""}`}
                  >
                    {label}
                  </a>
                ),
              )}
            </nav>

            <section id="trace" className="stack scroll-mt">
              <div className="grid grid--2" style={{ alignItems: "start" }}>
                <Card title="Development trace" pad>
                  <Async query={trace} skeleton={<Skeleton h={200} />}>
                    {(t) => (
                      <div className="trace">
                        {t.nodes.map((n) => (
                          <TraceRow key={n.key} node={n} />
                        ))}
                      </div>
                    )}
                  </Async>
                </Card>

                <div className="stack">
                  <RecordCard v={v} />
                  {v.primary_checkpoint && <CheckpointCard cp={v.primary_checkpoint} />}
                  {v.metrics.length > 0 && (
                    <Card title="Metrics" pad>
                      <div className="stack" style={{ gap: 0 }}>
                        {v.metrics.map((m) => {
                          const trend = metricTrend(m.before, m.after, m.direction);
                          return (
                            <div key={m.name} className="metric-row">
                              <span>{m.name}</span>
                              <span className="mono tnum">
                                {m.before != null && (
                                  <span className="muted">{m.before} → </span>
                                )}
                                <span className={trend === "up" ? "plus" : trend === "down" ? "minus" : ""}>
                                  {m.after ?? "—"}
                                  {m.unit ? ` ${m.unit}` : ""}
                                </span>
                              </span>
                            </div>
                          );
                        })}
                      </div>
                    </Card>
                  )}
                </div>
              </div>
            </section>

            <section id="changes" className="stack scroll-mt" style={{ marginTop: 20 }}>
              <Card
                title={`Files changed · ${v.files_changed}`}
                action={
                  <span className="mono text-xs">
                    <span className="plus">+{v.lines_added}</span>{" "}
                    <span className="minus">−{v.lines_removed}</span>
                  </span>
                }
                pad
              >
                {v.changed_files.length === 0 ? (
                  <div className="muted">No file changes recorded.</div>
                ) : (
                  <div className="files">
                    {v.changed_files.map((f) => (
                      <div key={f.path} className="files__row">
                        <span className={`files__mark files__mark--${f.change_type}`}>
                          {f.change_type[0].toUpperCase()}
                        </span>
                        <span className="mono truncate">{f.path}</span>
                        <span className="spacer" />
                        {f.binary ? (
                          <span className="muted text-xs">binary</span>
                        ) : (
                          <span className="mono text-xs">
                            <span className="plus">+{f.additions}</span>{" "}
                            <span className="minus">−{f.deletions}</span>
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </section>

            {hasRisk && (
              <section id="risk" className="stack scroll-mt" style={{ marginTop: 20 }}>
                {v.regressions.length > 0 && (
                  <Card className="callout callout--bad" title="Regressions" pad>
                    <div className="stack" style={{ gap: 8 }}>
                      {v.regressions.map((r, i) => (
                        <div key={i} className="row row--wrap" style={{ gap: 8 }}>
                          <Badge tone={r.severity === "HIGH" ? "bad" : r.severity === "MEDIUM" ? "warn" : "neutral"}>
                            {r.severity}
                          </Badge>
                          <span className="text-sm">{r.detail}</span>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}

                {(attempts.data?.length ?? 0) > 0 && (
                  <Card className="callout callout--warn" title="Previous attempts touching this area" pad>
                    <div className="stack" style={{ gap: 10 }}>
                      {attempts.data!.map((a) => (
                        <AttemptCard key={a.version_id} a={a} />
                      ))}
                    </div>
                  </Card>
                )}

                {impact.data && impact.data.entities.length > 0 && (
                  <Card
                    title="Change impact"
                    action={
                      <span className="muted text-xs">
                        entire graph · {impact.data.entities.length} entities
                      </span>
                    }
                    flush
                  >
                    <ImpactTable entities={impact.data.entities} />
                  </Card>
                )}
              </section>
            )}

            <section id="analysis" className="scroll-mt" style={{ marginTop: 20 }}>
              {v.analysis && v.analysis.summary ? (
                <Card
                  title="Analysis"
                  action={
                    <span className="row" style={{ gap: 6 }}>
                      {v.analysis.risk && (
                        <Badge tone={riskTone(v.analysis.risk)}>{v.analysis.risk} risk</Badge>
                      )}
                      <span className="muted text-xs">{v.analysis.provider}</span>
                    </span>
                  }
                  pad
                >
                  <p style={{ fontSize: "0.9375rem" }}>{v.analysis.summary}</p>
                  {v.analysis.reasoning && (
                    <p className="secondary text-sm" style={{ marginTop: 8 }}>
                      {v.analysis.reasoning}
                    </p>
                  )}
                  {v.analysis.recommendation && (
                    <p style={{ marginTop: 10 }}>
                      <b>Recommendation:</b> {v.analysis.recommendation}
                    </p>
                  )}
                  {v.analysis.warnings.length > 0 && (
                    <ul className="warn-list">
                      {v.analysis.warnings.map((w, i) => (
                        <li key={i}>
                          <Icon name="alert" size={13} /> {w}
                        </li>
                      ))}
                    </ul>
                  )}
                  <p className="muted text-xs" style={{ marginTop: 10 }}>
                    Interpretation only — never overrides the Git, test, or metric facts above.
                  </p>
                </Card>
              ) : (
                <Card title="Analysis" pad>
                  <div className="muted text-sm">
                    No analysis stored. Run <code>devmemory analyze {v.version_id}</code>.
                  </div>
                </Card>
              )}
            </section>

            {diff.data && (
              <section id="diff" className="scroll-mt" style={{ marginTop: 20 }}>
                <Card
                  title={
                    <>
                      Diff · {shortSha(v.parent_commit)} → {shortSha(v.git_commit)}
                    </>
                  }
                  flush
                >
                  <DiffView raw={diff.data} />
                </Card>
              </section>
            )}
          </>
        );
      }}
    </Async>
  );
}

function TraceRow({ node }: { node: TraceNode }) {
  const tone = node.status
    ? node.status === "pass"
      ? "ok"
      : node.status === "down" || node.status === "regression" || node.status === "fail"
        ? "bad"
        : node.status === "missing"
          ? "neutral"
          : "warn"
    : null;
  return (
    <div className={`trace__node trace__node--${node.source}`}>
      <div className="trace__label">{node.label}</div>
      <div>
        <div className="trace__value">
          {node.value}
          {tone && (
            <span className={`badge badge--${tone}`} style={{ marginLeft: 8 }}>
              <span className="badge__dot" />
              {node.status}
            </span>
          )}
        </div>
        {node.detail && <div className="trace__detail">{node.detail}</div>}
      </div>
    </div>
  );
}

function RecordCard({ v }: { v: DevelopmentVersion }) {
  return (
    <Card title="Record" pad>
      <dl className="kv">
        <dt>status</dt>
        <dd>
          <StatusBadge status={v.status} />
        </dd>
        <dt>agent</dt>
        <dd>
          {v.agent ?? "—"}
          {v.model && <span className="muted"> ({v.model})</span>}
        </dd>
        <dt>commit</dt>
        <dd>
          <Sha sha={v.git_commit} /> <span className="muted">parent {shortSha(v.parent_commit)}</span>
        </dd>
        <dt>branch</dt>
        <dd>{v.branch ?? "—"}</dd>
        <dt>feature</dt>
        <dd>
          {v.feature_id ? (
            <Link className="link" to={`/feature/${encodeURIComponent(featureName(v.feature_id))}`}>
              {featureName(v.feature_id)}
            </Link>
          ) : (
            "—"
          )}
        </dd>
        <dt>changes</dt>
        <dd>
          {v.files_changed} files · <span className="plus">+{v.lines_added}</span>{" "}
          <span className="minus">−{v.lines_removed}</span>
        </dd>
        {v.tests && v.tests.command && (
          <>
            <dt>tests</dt>
            <dd>
              {v.tests.passed} passed / {v.tests.failed} failed / {v.tests.skipped} skipped
            </dd>
          </>
        )}
        {v.committed_at && (
          <>
            <dt>committed</dt>
            <dd className="muted">{absTime(v.committed_at)}</dd>
          </>
        )}
      </dl>
    </Card>
  );
}

function CheckpointCard({ cp }: { cp: NonNullable<DevelopmentVersion["primary_checkpoint"]> }) {
  return (
    <Card title="Entire checkpoint" pad>
      <dl className="kv">
        <dt>checkpoint</dt>
        <dd>
          <span className="pill">{cp.checkpoint_id.slice(0, 16)}</span>
        </dd>
        <dt>association</dt>
        <dd>
          <Badge tone="info">{cp.association_method}</Badge>{" "}
          {cp.association_confidence != null && (
            <span className="muted">{cp.association_confidence.toFixed(2)}</span>
          )}
        </dd>
        {cp.agent && (
          <>
            <dt>agent</dt>
            <dd>
              {cp.agent}
              {cp.model ? ` · ${cp.model}` : ""}
            </dd>
          </>
        )}
        {cp.tokens?.total ? (
          <>
            <dt>tokens</dt>
            <dd>{(cp.tokens.total / 1000).toFixed(1)}k</dd>
          </>
        ) : null}
      </dl>
    </Card>
  );
}

function ImpactTable({ entities }: { entities: ChangedEntity[] }) {
  const rows = entities.slice().sort((a, b) => b.dependents_count - a.dependents_count).slice(0, 40);
  return (
    <div className="dm-table__scroll">
      <table className="dm-table">
        <thead>
          <tr>
            <th>change</th>
            <th>entity</th>
            <th>file</th>
            <th className="r">deps</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e, i) => (
            <tr key={i}>
              <td>
                <Badge
                  tone={
                    e.change_type === "removed" || e.change_type === "signature_changed"
                      ? "bad"
                      : e.change_type === "added"
                        ? "ok"
                        : "neutral"
                  }
                >
                  {e.change_type}
                </Badge>
              </td>
              <td>
                {e.kind} <b>{e.name}</b>
              </td>
              <td className="muted mono text-xs">{e.path}</td>
              <td className="r">{e.dependents_count || ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
