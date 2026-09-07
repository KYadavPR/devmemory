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
import { Card, StatusBadge, Badge, Sha, Skeleton } from "@/components/primitives";
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
            <div className="page-head__row" style={{ alignItems: "flex-start" }}>
              <div style={{ minWidth: 0 }}>
                <div className="crumb">
                  <Link to="/timeline">Timeline</Link> / <span className="mono">{v.version_id}</span>
                </div>
                <div className="row" style={{ gap: 10 }}>
                  <span className="mono" style={{ fontSize: "1.05rem", fontWeight: 600 }}>
                    {vlabel(v.version_id)}
                  </span>
                  <StatusBadge status={v.status} />
                </div>
                <div className="h-doc" style={{ marginTop: 9 }}>
                  {v.intent ?? "No recorded intent"}
                </div>
              </div>
              <Link className="btn btn--sm" to={`/compare/${v.version_id}...${v.version_id}`}>
                <Icon name="compare" size={14} /> Compare
              </Link>
            </div>

            <p className="lead lead--sm secondary" style={{ margin: "12px 0 0" }}>
              <VersionLead v={v} attempts={attempts.data?.length ?? 0} />
            </p>

            <nav className="subnav">
              {SECTIONS.filter(([s]) => (s === "risk" ? hasRisk : s === "diff" ? diff.data : true)).map(
                ([s, label]) => (
                  <a
                    key={s}
                    href={`#${s}`}
                    className={`subnav__link${activeSection === s ? " subnav__link--active" : ""}`}
                    onClick={(e) => {
                      // The app is hash-routed, so a bare "#section" href would
                      // be read as a route change and land on NotFound. Scroll
                      // the section into view ourselves instead.
                      e.preventDefault();
                      document.getElementById(s)?.scrollIntoView({ behavior: "smooth" });
                      setActiveSection(s);
                    }}
                  >
                    {label}
                  </a>
                ),
              )}
            </nav>

            <section id="trace" className="scroll-mt" style={{ marginTop: 24 }}>
              <div className="split" style={{ ["--rail-w" as string]: "300px" }}>
                <div>
                  <div className="h-section" style={{ marginBottom: 14 }}>
                    Development trace
                  </div>
                  <Async query={trace} skeleton={<Skeleton h={200} />}>
                    {(t) => (
                      <div className="trace">
                        {t.nodes.map((n) => (
                          <TraceRow key={n.key} node={n} />
                        ))}
                      </div>
                    )}
                  </Async>
                </div>

                <div className="rail">
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

            <hr className="sep" />

            <section id="changes" className="scroll-mt">
              <div className="section-head">
                <div className="h-section">Files changed · {v.files_changed}</div>
                <span className="mono text-xs">
                  <span className="plus">+{v.lines_added}</span>{" "}
                  <span className="minus">−{v.lines_removed}</span>
                </span>
              </div>
              {v.changed_files.length === 0 ? (
                <div className="muted text-sm">No file changes recorded.</div>
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
            </section>

            {hasRisk && (
              <>
                <hr className="sep" />
                <section id="risk" className="scroll-mt">
                  <div className="h-section" style={{ marginBottom: 14 }}>
                    Risk
                  </div>

                  <div className="stack" style={{ gap: 18 }}>
                    {v.regressions.map((r, i) => (
                      <div key={i} className="rule rule--bad">
                        <div className="rule__label">Regression</div>
                        <div className="rule__body">
                          {r.detail} · <b>{r.severity}</b>
                        </div>
                      </div>
                    ))}

                    {(attempts.data?.length ?? 0) > 0 && (
                      <div className="rule rule--warn">
                        <div className="rule__label">Previous attempts touching this area</div>
                        <div className="stack" style={{ gap: 8, marginTop: 6 }}>
                          {attempts.data!.map((a) => (
                            <AttemptCard key={a.version_id} a={a} />
                          ))}
                        </div>
                      </div>
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
                  </div>
                </section>
              </>
            )}

            <hr className="sep" />

            <section id="analysis" className="scroll-mt">
              <div className="section-head">
                <div className="h-section">Analysis</div>
                {v.analysis && v.analysis.summary && (
                  <span className="row" style={{ gap: 6 }}>
                    {v.analysis.risk && (
                      <Badge tone={riskTone(v.analysis.risk)}>
                        {v.analysis.risk} risk · {v.analysis.provider}
                      </Badge>
                    )}
                  </span>
                )}
              </div>
              {v.analysis && v.analysis.summary ? (
                <>
                  <p style={{ fontSize: "0.9rem", lineHeight: 1.6, maxWidth: "70ch" }}>
                    {v.analysis.summary}
                  </p>
                  {v.analysis.reasoning && (
                    <p className="secondary text-sm" style={{ marginTop: 10, maxWidth: "70ch" }}>
                      {v.analysis.reasoning}
                    </p>
                  )}
                  {v.analysis.recommendation && (
                    <p style={{ marginTop: 10, maxWidth: "70ch", fontSize: "0.85rem" }}>
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
                  <p className="muted text-xs" style={{ marginTop: 12 }}>
                    Interpretation only — never overrides the Git, test, or metric facts above.
                  </p>
                </>
              ) : (
                <div className="muted text-sm">
                  No analysis stored. Run <code>devmemory analyze {v.version_id}</code>.
                </div>
              )}
            </section>

            {diff.data && (
              <>
                <hr className="sep" />
                <section id="diff" className="scroll-mt">
                  <div className="h-section" style={{ marginBottom: 12 }}>
                    Diff · <span className="mono">{shortSha(v.parent_commit)}</span> →{" "}
                    <span className="mono">{shortSha(v.git_commit)}</span>
                  </div>
                  <Card flush>
                    <DiffView raw={diff.data} />
                  </Card>
                </section>
              </>
            )}
          </>
        );
      }}
    </Async>
  );
}

/**
 * A one-sentence read of the version, assembled from the recorded facts only —
 * tests, metric movement, regressions, prior attempts. No interpretation; the
 * Analysis section below is where that lives.
 */
function VersionLead({ v, attempts }: { v: DevelopmentVersion; attempts: number }) {
  const tests = v.tests && v.tests.total > 0 ? v.tests : null;
  const testClause = tests
    ? tests.failed > 0
      ? `${tests.failed} of ${tests.passed + tests.failed} tests fail`
      : `all ${tests.passed} tests pass`
    : null;

  const moved = v.metrics.find((m) => m.before != null && m.after != null && m.before !== m.after);
  const movedPct =
    moved && moved.before ? ((moved.after! - moved.before) / Math.abs(moved.before)) * 100 : null;

  const worst = v.regressions[0];

  return (
    <>
      {testClause ? cap(testClause) : "No test results were recorded"}
      {moved && (
        <>
          {" and "}
          <span className="mono" style={{ fontSize: "0.8em" }}>
            {moved.name}
          </span>{" "}
          went {moved.before} → {moved.after}
          {movedPct != null && ` (${movedPct > 0 ? "+" : ""}${movedPct.toFixed(1)}%)`}
        </>
      )}
      {worst ? (
        <>
          {" — recorded as a "}
          <b>{worst.severity.toLowerCase()}</b> regression.
        </>
      ) : (
        "."
      )}
      {attempts > 0 && (
        <>
          {" "}
          {attempts} earlier attempt{attempts === 1 ? "" : "s"} in this area also went wrong.
        </>
      )}
    </>
  );
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

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
