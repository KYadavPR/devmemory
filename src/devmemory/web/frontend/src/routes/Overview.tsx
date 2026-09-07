import { Link } from "react-router-dom";
import { useAnalytics, useFeatures, useProject, useVersions } from "@/api/client";
import { Async } from "@/components/Async";
import { Card, PageHead, StatTile, StatusBadge, EmptyState, Skeleton } from "@/components/primitives";
import { Sparkline } from "@/components/Sparkline";
import { VersionRow, StatusDot } from "@/components/bits";
import { Icon } from "@/components/Icon";
import { featureName, pct, shortSha, vlabel } from "@/lib/format";
import { statusTone } from "@/lib/status";

export function Overview() {
  const project = useProject();
  const versions = useVersions(500);
  const features = useFeatures();
  const analytics = useAnalytics();

  return (
    <>
      <Async
        query={project}
        skeleton={<Skeleton h={120} r="var(--r-3)" />}
        isEmpty={(p) => p.version_count === 0}
        empty={
          <EmptyState
            icon="sparkles"
            title="No development versions yet"
            sub={
              <>
                Run <code>devmemory checkpoint</code> after your next meaningful commit, or seed the
                demo with <code>python examples/demo/seed.py</code>.
              </>
            }
          />
        }
      >
        {(p) => (
          <>
            <PageHead
              title={p.name}
              subtitle={
                <>
                  {p.branch && (
                    <>
                      <span className="mono">{p.branch}</span> ·{" "}
                    </>
                  )}
                  <span className="mono">{shortSha(p.head_sha)}</span>
                  {p.head_subject ? ` · ${p.head_subject}` : ""}
                </>
              }
            />

            {/* headline stats */}
            <div className="grid grid--4" style={{ marginBottom: 16 }}>
              <StatTile
                label="Versions"
                value={p.version_count}
                sub={p.latest_version_id ? `latest ${vlabel(p.latest_version_id)}` : "none yet"}
                icon="commit"
              />
              <StatTile
                label="Latest result"
                value={<StatusBadge status={p.latest_status} />}
                sub={p.latest_intent ?? ""}
              />
              {analytics.data && (
                <StatTile
                  label="Success rate"
                  value={pct(analytics.data.success_rate, 0)}
                  sub={`${analytics.data.regression_count} regression${analytics.data.regression_count === 1 ? "" : "s"}`}
                  tone={analytics.data.success_rate >= 80 ? "ok" : analytics.data.success_rate >= 50 ? "warn" : "bad"}
                  icon="target"
                />
              )}
              <StatTile
                label="Working tree"
                value={p.working_tree_clean ? "clean" : "dirty"}
                sub={p.head_has_version ? "HEAD is recorded" : "HEAD not checkpointed"}
                tone={p.head_has_version ? "ok" : "warn"}
              />
            </div>

            {!p.head_has_version && p.head_sha && (
              <Card className="callout callout--warn" pad>
                <div className="row" style={{ gap: 10 }}>
                  <Icon name="alert" size={18} />
                  <div>
                    <b>HEAD ({shortSha(p.head_sha)}) isn't recorded yet.</b>{" "}
                    <span className="secondary">
                      Run <code>devmemory checkpoint</code> to capture this change.
                    </span>
                  </div>
                </div>
              </Card>
            )}

            {/* repeated-failure callout */}
            {analytics.data && analytics.data.failed_approaches.length > 0 && (
              <Card className="callout callout--bad" title="Repeated failed approach" pad>
                <div className="stack" style={{ gap: 10 }}>
                  {analytics.data.failed_approaches.map((fa, i) => (
                    <div key={i} className="row row--wrap" style={{ gap: 10 }}>
                      <span className="badge badge--bad">
                        <span className="badge__dot" />
                        {fa.occurrences}× failed
                      </span>
                      <span className="mono text-sm truncate">{fa.signature.join(", ")}</span>
                      {fa.example_intent && (
                        <span className="muted text-sm truncate">“{fa.example_intent}”</span>
                      )}
                      <span className="spacer" />
                      <span className="row" style={{ gap: 6 }}>
                        {fa.version_ids.map((v) => (
                          <Link key={v} className="link" to={`/version/${v}`}>
                            {vlabel(v)}
                          </Link>
                        ))}
                      </span>
                    </div>
                  ))}
                  <div className="muted text-xs">
                    The same file signature regressed more than once. Read these before touching that
                    area again.
                  </div>
                </div>
              </Card>
            )}

            {/* health strip */}
            {analytics.data && analytics.data.trend.length > 1 && (
              <Card title="Version health" pad>
                <HealthStrip trend={analytics.data.trend} />
              </Card>
            )}

            {/* two columns */}
            <div className="grid grid--2" style={{ marginTop: 16, alignItems: "start" }}>
              <Card
                title="Recent versions"
                flush
                action={
                  <Link className="link text-sm" to="/timeline">
                    View all
                  </Link>
                }
              >
                <Async query={versions} isEmpty={(d) => d.length === 0} empty={<div className="card--pad muted">No versions.</div>}>
                  {(vs) => (
                    <div>
                      {vs
                        .slice()
                        .reverse()
                        .slice(0, 7)
                        .map((v, i) => (
                          <VersionRow key={v.version_id} v={v} index={i} />
                        ))}
                    </div>
                  )}
                </Async>
              </Card>

              <Card
                title="Feature health"
                flush
                action={
                  <Link className="link text-sm" to="/features">
                    View all
                  </Link>
                }
              >
                <Async query={features} isEmpty={(d) => d.length === 0} empty={<div className="card--pad muted">No features tracked.</div>}>
                  {(fs) => (
                    <div>
                      {fs.map((f) => (
                        <Link
                          key={f.feature_id}
                          className="frow"
                          to={`/feature/${encodeURIComponent(featureName(f.feature_id))}`}
                        >
                          <span className="frow__name truncate">{f.name}</span>
                          <span className="frow__dots">
                            {f.history.map((h) => (
                              <StatusDot key={h.version_id} status={h.status} />
                            ))}
                          </span>
                          <StatusBadge status={f.status} />
                        </Link>
                      ))}
                    </div>
                  )}
                </Async>
              </Card>
            </div>
          </>
        )}
      </Async>
    </>
  );
}

function HealthStrip({
  trend,
}: {
  trend: { version_id: string; status: string; key_metric: number | null; test_pass_rate: number | null }[];
}) {
  const usesMetric = trend.some((t) => t.key_metric != null);
  return (
    <div className="health-strip">
      <div className="health-strip__dots">
        {trend.map((t) => (
          <Link
            key={t.version_id}
            to={`/version/${t.version_id}`}
            title={`${vlabel(t.version_id)} · ${t.status}`}
            className={`health-strip__dot health-strip__dot--${statusTone(t.status)}`}
          >
            {vlabel(t.version_id)}
          </Link>
        ))}
      </div>
      <div className="health-strip__spark">
        <div className="muted text-xs" style={{ marginBottom: 2 }}>
          {usesMetric ? "key metric" : "test pass rate"}
        </div>
        <Sparkline
          points={trend.map((t) => ({
            value: usesMetric ? t.key_metric : t.test_pass_rate,
            label: `${vlabel(t.version_id)}: ${usesMetric ? t.key_metric : t.test_pass_rate}`,
            adverse: t.status === "REGRESSION" || t.status === "ERROR",
          }))}
          width={520}
          height={64}
        />
      </div>
    </div>
  );
}
