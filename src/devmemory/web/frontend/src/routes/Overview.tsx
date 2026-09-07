import { Link } from "react-router-dom";
import type { ReactNode } from "react";
import { useAnalytics, useFeatures, useProject, useVersions } from "@/api/client";
import type { AnalyticsSummary, ProjectSummary, VersionListItem } from "@/api/types";
import { Async } from "@/components/Async";
import { EmptyState, Skeleton } from "@/components/primitives";
import { Sparkline } from "@/components/Sparkline";
import { Icon } from "@/components/Icon";
import { featureName, shortSha, vlabel } from "@/lib/format";
import { isAdverse, statusTone } from "@/lib/status";

/** Columns for the version stream — shared by the header and every row. */
const STREAM_COLS = "40px minmax(0,1fr) 62px 62px 82px";

export function Overview() {
  const project = useProject();
  const versions = useVersions(500);
  const features = useFeatures();
  const analytics = useAnalytics();

  return (
    <Async
      query={project}
      skeleton={<Skeleton h={160} r="var(--r-3)" />}
      isEmpty={(p) => p.version_count === 0}
      empty={
        <EmptyState
          icon="sparkles"
          title="No development versions yet"
          sub={
            <>
              Run <code>devmemory backfill</code> to import your git history, or{" "}
              <code>devmemory checkpoint</code> after your next meaningful commit.
            </>
          }
        />
      }
    >
      {(p) => (
        <>
          {/* masthead */}
          <div className="page-head__row">
            <div style={{ minWidth: 0 }}>
              <h1 className="h-page">{p.name}</h1>
              <div className="mono text-xs muted" style={{ marginTop: 5 }}>
                {p.branch && <>{p.branch} · </>}
                {shortSha(p.head_sha)}
                {p.head_subject ? ` · ${p.head_subject}` : ""}
              </div>
            </div>
            <Link className="btn" to="/tasks">
              <Icon name="plus" size={13} /> New task
            </Link>
          </div>

          <div style={{ marginTop: 20 }}>
            <KpiStrip project={p} analytics={analytics.data} />
          </div>

          {/* the one-sentence read of the project */}
          <p className="lead" style={{ margin: "26px 0 0" }}>
            <Lead project={p} analytics={analytics.data} />
          </p>

          {analytics.data?.failed_approaches.map((fa, i) => (
            <div key={i} className="rule rule--bad" style={{ marginTop: 26 }}>
              <div className="rule__label">Repeated failure · {fa.occurrences}×</div>
              <div className="rule__body">
                <span className="mono text-xs">{fa.signature.join(", ")}</span> regressed in{" "}
                {fa.version_ids.map((v, j) => (
                  <span key={v}>
                    {j > 0 && (j === fa.version_ids.length - 1 ? " and " : ", ")}
                    <Link className="link" to={`/version/${v}`}>
                      {vlabel(v)}
                    </Link>
                  </span>
                ))}
                . Read both before editing that area again.
              </div>
            </div>
          ))}

          <div className="split" style={{ marginTop: 34 }}>
            {/* version stream */}
            <section>
              <div className="section-head">
                <div className="h-section">Version stream</div>
                <Link className="link text-sm" to="/timeline">
                  timeline →
                </Link>
              </div>

              <Async
                query={versions}
                isEmpty={(d) => d.length === 0}
                empty={<div className="muted text-sm">No versions.</div>}
              >
                {(vs) => <VersionStream versions={vs} />}
              </Async>

              {analytics.data && analytics.data.trend.length > 1 && (
                <MetricTrend trend={analytics.data.trend} />
              )}
            </section>

            {/* rail */}
            <aside className="rail">
              <section>
                <div className="section-head">
                  <div className="h-section">Feature health</div>
                  <Link className="link text-sm" to="/features">
                    all →
                  </Link>
                </div>
                <Async
                  query={features}
                  isEmpty={(d) => d.length === 0}
                  empty={<div className="muted text-sm">No features tracked.</div>}
                >
                  {(fs) => (
                    <div className="stack" style={{ gap: 13 }}>
                      {fs.map((f) => (
                        <Link
                          key={f.feature_id}
                          className="fbar"
                          to={`/feature/${encodeURIComponent(featureName(f.feature_id))}`}
                        >
                          <div className="fbar__top">
                            <span className="fbar__name truncate">{f.name}</span>
                            <span className={`fbar__state fbar__state--${statusTone(f.status)}`}>
                              {f.history.some((h) => isAdverse(h.status)) ? "AT RISK" : "HEALTHY"}
                            </span>
                          </div>
                          <div className="fbar__segs">
                            {f.history.map((h) => (
                              <span
                                key={h.version_id}
                                className={`fbar__seg fbar__seg--${statusTone(h.status)}`}
                              />
                            ))}
                          </div>
                        </Link>
                      ))}
                    </div>
                  )}
                </Async>
              </section>

              <hr className="sep sep--tight" style={{ margin: 0 }} />

              <div className="card card--pad">
                <div className="h-section" style={{ marginBottom: 8 }}>
                  Next
                </div>
                <div className="text-sm secondary" style={{ lineHeight: 1.6 }}>
                  <NextStep project={p} />
                </div>
              </div>
            </aside>
          </div>
        </>
      )}
    </Async>
  );
}

/* --- the numbers --------------------------------------------------------- */

function KpiStrip({
  project: p,
  analytics: a,
}: {
  project: ProjectSummary;
  analytics: AnalyticsSummary | undefined;
}) {
  const landed = a ? Math.round((a.success_rate / 100) * a.version_count) : null;
  const regressionHome = a ? dominantFeature(a) : null;
  return (
    <div className="kpi-strip">
      <div className="kpi">
        <div className="kpi__label">Versions</div>
        <div className="kpi__value">{p.version_count}</div>
        <div className="kpi__sub">
          {p.latest_version_id ? (
            <>
              latest <span className="mono">{vlabel(p.latest_version_id)}</span>
            </>
          ) : (
            "none yet"
          )}
        </div>
      </div>
      <div className="kpi">
        <div className="kpi__label">Landed clean</div>
        <div className="kpi__value" style={{ color: a && a.success_rate >= 50 ? "var(--ok)" : "var(--warn)" }}>
          {a ? `${Math.round(a.success_rate)}%` : "—"}
        </div>
        <div className="kpi__sub">{a ? `${landed} of ${a.version_count}` : ""}</div>
      </div>
      <div className="kpi">
        <div className="kpi__label">Regressions</div>
        <div
          className="kpi__value"
          style={{ color: a && a.regression_count > 0 ? "var(--bad)" : "var(--ok)" }}
        >
          {a ? a.regression_count : "—"}
        </div>
        <div className="kpi__sub">
          {a && a.regression_count > 0
            ? regressionHome
              ? `${a.regression_count === 2 ? "both" : "all"} in ${regressionHome}`
              : "across features"
            : "none recorded"}
        </div>
      </div>
      <div className="kpi">
        <div className="kpi__label">Working tree</div>
        <div
          className="kpi__value kpi__value--word"
          style={{ color: p.working_tree_clean ? "var(--ok)" : "var(--warn)" }}
        >
          {p.working_tree_clean ? "clean" : "dirty"}
        </div>
        <div className="kpi__sub">{p.head_has_version ? "HEAD recorded" : "HEAD not recorded"}</div>
      </div>
    </div>
  );
}

/** The feature that owns every regression, if exactly one does. */
function dominantFeature(a: AnalyticsSummary): string | null {
  const withRegressions = a.features.filter((f) => f.regressions > 0);
  return withRegressions.length === 1 ? withRegressions[0].feature : null;
}

const WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const word = (n: number): string => (n <= 10 ? WORDS[n] : String(n));

/**
 * A sentence built from the same numbers the strip shows — what a person would
 * say about this project if you asked them where to look.
 */
function Lead({
  project: p,
  analytics: a,
}: {
  project: ProjectSummary;
  analytics: AnalyticsSummary | undefined;
}): ReactNode {
  if (!a || a.version_count === 0) {
    return <>Nothing is recorded yet — the timeline fills in as you checkpoint.</>;
  }
  const landed = Math.round((a.success_rate / 100) * a.version_count);
  const tree = p.working_tree_clean ? "the tree is clean" : "the working tree is dirty";
  const home = dominantFeature(a);
  const repeat = a.failed_approaches[0];

  return (
    <>
      {cap(word(landed))} of {word(a.version_count)} change{a.version_count === 1 ? "" : "s"} landed
      clean and {tree}
      {a.regression_count === 0 ? (
        <> — nothing has regressed.</>
      ) : (
        <>
          {" — but "}
          {a.regression_count === 1 ? "the regression sits" : `${word(a.regression_count)} regressions sit`}
          {home ? (
            <>
              {" in "}
              <Link className="link" to={`/feature/${encodeURIComponent(home)}`}>
                {home}
              </Link>
            </>
          ) : (
            " across several features"
          )}
          {repeat
            ? `, and it's the same file signature ${word(repeat.occurrences)} times, so that's where to look first.`
            : "."}
        </>
      )}
    </>
  );
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function NextStep({ project: p }: { project: ProjectSummary }): ReactNode {
  if (!p.head_has_version && p.head_sha) {
    return (
      <>
        HEAD (<span className="mono">{shortSha(p.head_sha)}</span>) isn't recorded. Run{" "}
        <code>devmemory checkpoint</code> to capture it.
      </>
    );
  }
  return (
    <>
      HEAD is recorded{p.working_tree_clean ? " and the tree is clean" : ""}.{" "}
      <Link className="link" to="/tasks">
        Start a task
      </Link>{" "}
      or run <code>devmemory task new</code>.
    </>
  );
}

/* --- the stream ---------------------------------------------------------- */

/** The metric every row is measured against: the first one anybody recorded. */
function keyMetricName(versions: VersionListItem[]): string | null {
  for (const v of versions) {
    const names = Object.keys(v.metrics ?? {});
    if (names.length) return names[0];
  }
  return null;
}

function VersionStream({ versions }: { versions: VersionListItem[] }) {
  const metric = keyMetricName(versions);
  const ascending = versions.slice().sort((a, b) => a.version_number - b.version_number);
  const rows = ascending.slice().reverse().slice(0, 8);

  // deltas need the previous version's value, so index the ascending list
  const valueAt = (v: VersionListItem) => (metric ? (v.metrics?.[metric] ?? null) : null);
  const prevOf = new Map<string, number | null>();
  ascending.forEach((v, i) => prevOf.set(v.version_id, i > 0 ? valueAt(ascending[i - 1]) : null));

  return (
    <>
      <div className="stream__head" style={{ ["--stream-cols" as string]: STREAM_COLS }}>
        <span>ver</span>
        <span>intent</span>
        <span>tests</span>
        <span>{metric ? "Δ" : ""}</span>
        <span style={{ justifySelf: "end" }}>result</span>
      </div>
      {rows.map((v) => {
        const adverse = isAdverse(v.status) || v.has_regression;
        const after = valueAt(v);
        const before = prevOf.get(v.version_id) ?? null;
        const delta =
          after != null && before != null && before !== 0 ? ((after - before) / before) * 100 : null;
        return (
          <Link
            key={v.version_id}
            to={`/version/${v.version_id}`}
            className={`stream__row${adverse ? " stream__row--bad" : ""}`}
            style={{ ["--stream-cols" as string]: STREAM_COLS }}
          >
            <span className="mono text-xs" style={{ color: adverse ? "var(--bad)" : "var(--text-muted)" }}>
              {vlabel(v.version_id)}
            </span>
            <span className="truncate" title={v.intent ?? ""}>
              {v.intent ?? <span className="muted">no intent recorded</span>}
            </span>
            <span className="mono text-xs secondary">
              {v.tests_passed == null ? "—" : `${v.tests_passed}/${v.tests_failed ?? 0}`}
            </span>
            <span
              className="mono text-xs"
              style={{ color: delta == null ? "var(--text-muted)" : adverse ? "var(--bad)" : "var(--ok)" }}
              title={metric && after != null ? `${metric}: ${after}` : undefined}
            >
              {delta == null ? "—" : `${delta > 0 ? "+" : ""}${delta.toFixed(0)}%`}
            </span>
            <span
              className="stream__end"
              style={{ color: `var(--${statusTone(v.status) === "ok" ? "ok" : statusTone(v.status) === "bad" ? "bad" : statusTone(v.status) === "warn" ? "warn" : "text-muted"})` }}
            >
              {adverse ? "▲" : statusTone(v.status) === "ok" ? "●" : "○"} {resultWord(v)}
            </span>
          </Link>
        );
      })}
    </>
  );
}

function resultWord(v: VersionListItem): string {
  if (v.status === "REGRESSION" || v.has_regression) return "regressed";
  if (v.status === "ERROR") return "error";
  if (v.status === "SUCCESS") return "landed";
  if (v.status === "PARTIAL_SUCCESS") return "partial";
  if (v.status === "IN_PROGRESS") return "running";
  return "review";
}

function MetricTrend({
  trend,
}: {
  trend: { version_id: string; status: string; key_metric: number | null; test_pass_rate: number | null }[];
}) {
  const usesMetric = trend.some((t) => t.key_metric != null);
  return (
    <div style={{ marginTop: 22 }}>
      <div className="text-xs muted" style={{ marginBottom: 6 }}>
        {usesMetric ? "key metric" : "test pass rate"} · {vlabel(trend[0].version_id)} →{" "}
        {vlabel(trend[trend.length - 1].version_id)}
      </div>
      <Sparkline
        points={trend.map((t) => ({
          value: usesMetric ? t.key_metric : t.test_pass_rate,
          label: `${vlabel(t.version_id)}: ${usesMetric ? t.key_metric : t.test_pass_rate}`,
          adverse: isAdverse(t.status),
        }))}
        width={620}
        height={72}
      />
    </div>
  );
}
