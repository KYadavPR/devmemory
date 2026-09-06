import { Link } from "react-router-dom";
import { useAnalytics } from "@/api/client";
import { Async } from "@/components/Async";
import { Card, PageHead, StatTile, Badge, EmptyState } from "@/components/primitives";
import { ChurnScatter, HBarChart, TrendChart } from "@/components/charts";
import { Icon } from "@/components/Icon";
import { pct, vlabel } from "@/lib/format";
import { severityTone } from "@/lib/status";

export function Intelligence() {
  const query = useAnalytics();

  return (
    <>
      <Async query={query}>
        {(a) => {
          const usesMetric = a.trend.some((t) => t.key_metric != null);
          return (
            <>
              <PageHead
                title="Development intelligence"
                subtitle={
                  <>
                    {a.version_count} versions · {a.regression_count} regressions ·{" "}
                    {pct(a.success_rate)} success
                  </>
                }
                actions={
                  <Badge tone={a.source === "databricks" ? "info" : "neutral"}>
                    <Icon name={a.source === "databricks" ? "external" : "history"} size={12} />
                    {a.source === "databricks" ? "Databricks" : "local"}
                  </Badge>
                }
              />

              <div className="grid grid--3" style={{ marginBottom: 16 }}>
                <StatTile
                  label="Success rate"
                  value={pct(a.success_rate)}
                  sub={`${a.version_count} versions`}
                  tone={a.success_rate >= 80 ? "ok" : a.success_rate >= 50 ? "warn" : "bad"}
                />
                <StatTile label="Regressions" value={a.regression_count} sub="flagged" tone={a.regression_count ? "warn" : "ok"} />
                <StatTile label="Features" value={a.features.length} sub="tracked" />
              </div>

              {a.failed_approaches.length > 0 && (
                <Card className="callout callout--bad" title="Repeatedly-failed approaches" pad>
                  <div className="stack" style={{ gap: 8 }}>
                    {a.failed_approaches.map((f, i) => (
                      <div key={i} className="row row--wrap" style={{ gap: 10 }}>
                        <Badge tone="bad">{f.occurrences}×</Badge>
                        <span className="mono text-sm truncate">{f.signature.join(", ")}</span>
                        {f.example_intent && (
                          <span className="muted text-sm truncate">“{f.example_intent}”</span>
                        )}
                        <span className="spacer" />
                        {f.version_ids.map((v) => (
                          <Link key={v} className="link" to={`/version/${v}`}>
                            {vlabel(v)}
                          </Link>
                        ))}
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              <div className="grid grid--2" style={{ alignItems: "start", marginTop: 16 }}>
                <Card title={usesMetric ? "Key metric over versions" : "Test pass rate over versions"} pad>
                  {a.trend.length > 1 ? (
                    <TrendChart
                      data={a.trend.map((t) => ({
                        label: vlabel(t.version_id),
                        value: usesMetric ? t.key_metric : t.test_pass_rate,
                        adverse: t.status === "REGRESSION" || t.status === "ERROR",
                        sub: t.status,
                      }))}
                    />
                  ) : (
                    <EmptyState title="Not enough versions to trend" />
                  )}
                </Card>

                <Card title="Feature success rate" pad>
                  {a.features.length ? (
                    <HBarChart
                      unit="%"
                      data={a.features.map((f) => ({
                        label: f.feature,
                        value: Math.round(f.success_rate),
                        sub: `${f.successes}/${f.attempts} attempts · ${f.regressions} regressions`,
                        tone:
                          f.success_rate >= 80
                            ? "var(--ok)"
                            : f.success_rate >= 50
                              ? "var(--warn)"
                              : "var(--bad)",
                      }))}
                    />
                  ) : (
                    <EmptyState title="No features" />
                  )}
                </Card>

                <Card title="File churn vs. adverse changes" pad>
                  {a.file_churn.length ? (
                    <ChurnScatter
                      data={a.file_churn.map((f) => ({
                        x: f.changes,
                        y: f.adverse_changes,
                        label: f.path,
                      }))}
                    />
                  ) : (
                    <EmptyState title="No churn data" />
                  )}
                </Card>

                <Card title="Agent effectiveness" flush>
                  <div className="dm-table__scroll">
                    <table className="dm-table">
                      <thead>
                        <tr>
                          <th>agent</th>
                          <th className="r">versions</th>
                          <th className="r">success</th>
                          <th className="r">tok/success</th>
                        </tr>
                      </thead>
                      <tbody>
                        {a.agents.map((g) => (
                          <tr key={g.agent}>
                            <td>{g.agent}</td>
                            <td className="r">{g.versions}</td>
                            <td className="r">{pct(g.success_rate)}</td>
                            <td className="r">
                              {g.tokens_per_success ? `${(g.tokens_per_success / 1000).toFixed(0)}k` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>

              <Card title="Regression leaderboard" flush style={{ marginTop: 16 }}>
                {a.regressions.length === 0 ? (
                  <div className="card--pad muted">No regressions recorded.</div>
                ) : (
                  <div className="dm-table__scroll">
                    <table className="dm-table">
                      <thead>
                        <tr>
                          <th>version</th>
                          <th>severity</th>
                          <th>feature</th>
                          <th>detail</th>
                        </tr>
                      </thead>
                      <tbody>
                        {a.regressions.map((r) => (
                          <tr key={r.version_id}>
                            <td>
                              <Link className="link" to={`/version/${r.version_id}`}>
                                {vlabel(r.version_id)}
                              </Link>
                            </td>
                            <td>
                              <Badge tone={severityTone(r.severity)}>{r.severity}</Badge>
                            </td>
                            <td className="muted">{r.feature ?? "—"}</td>
                            <td className="text-sm">{r.detail}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <p className="muted text-xs" style={{ marginTop: 16 }}>
                {a.source === "databricks"
                  ? "Live from Databricks Delta tables."
                  : "Computed locally from the SQLite store. Set DATABRICKS_* and databricks.enabled to publish and query these in Databricks."}
              </p>
            </>
          );
        }}
      </Async>
    </>
  );
}
