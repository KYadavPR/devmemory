import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useCompare, useVersions } from "@/api/client";
import { Async } from "@/components/Async";
import { Card, PageHead, StatTile, StatusBadge, EmptyState, Skeleton } from "@/components/primitives";
import { DiffView } from "@/components/DiffView";
import { Icon } from "@/components/Icon";
import { signed, vlabel } from "@/lib/format";

export function Compare() {
  const { pair } = useParams<{ pair: string }>();
  const navigate = useNavigate();
  const versionsQ = useVersions(500);

  const [a, b] = (pair ?? "").split("...");
  const [from, setFrom] = useState(a ?? "");
  const [to, setTo] = useState(b ?? "");

  useEffect(() => {
    const [pa, pb] = (pair ?? "").split("...");
    setFrom(pa ?? "");
    setTo(pb ?? "");
  }, [pair]);

  useEffect(() => {
    if (from && to) navigate(`/compare/${from}...${to}`, { replace: true });
  }, [from, to, navigate]);

  // seed sensible defaults once versions arrive and nothing is in the URL
  useEffect(() => {
    const list = versionsQ.data;
    if (!list || list.length < 2 || pair) return;
    setFrom((f) => f || list[list.length - 2].version_id);
    setTo((t) => t || list[list.length - 1].version_id);
  }, [versionsQ.data, pair]);

  const cmp = useCompare(from || undefined, to || undefined);

  return (
    <>
      <PageHead
        title="Compare versions"
        subtitle="What actually changed between two development states — files, metrics, tests, diff."
      />

      <Async query={versionsQ} isEmpty={(d) => d.length < 2} empty={<EmptyState title="Need at least two versions to compare" />}>
        {(versions) => {
          const opts = versions.map((v) => (
            <option key={v.version_id} value={v.version_id}>
              {vlabel(v.version_id)} — {(v.intent ?? "").slice(0, 60)}
            </option>
          ));
          return (
            <Card pad style={{ marginBottom: 16 }}>
              <div className="row row--wrap" style={{ gap: 12 }}>
                <select className="input" style={{ flex: 1, minWidth: 200 }} value={from} onChange={(e) => setFrom(e.target.value)}>
                  <option value="">from…</option>
                  {opts}
                </select>
                <Icon name="arrowRight" size={16} />
                <select className="input" style={{ flex: 1, minWidth: 200 }} value={to} onChange={(e) => setTo(e.target.value)}>
                  <option value="">to…</option>
                  {opts}
                </select>
              </div>
            </Card>
          );
        }}
      </Async>

      {!from || !to ? null : from === to ? (
        <EmptyState title="Pick two different versions" />
      ) : (
        <Async query={cmp} skeleton={<Skeleton h={200} r="var(--r-3)" />}>
          {(c) => (
            <div className="stack">
              <div className="grid grid--3">
                <StatTile
                  label="Lines"
                  value={
                    <span className="mono">
                      <span className="plus">+{c.stat.additions}</span>{" "}
                      <span className="minus">−{c.stat.deletions}</span>
                    </span>
                  }
                  sub={`${c.stat.files_changed} file${c.stat.files_changed === 1 ? "" : "s"}`}
                />
                <StatTile
                  label="Status"
                  value={
                    <span className="row" style={{ gap: 6 }}>
                      <StatusBadge status={c.status_from} />
                      <Icon name="arrowRight" size={13} />
                      <StatusBadge status={c.status_to} />
                    </span>
                  }
                />
                <StatTile
                  label="Tests"
                  value={
                    c.test_changes && c.test_changes.passed != null ? (
                      <span className="mono">
                        {signed(c.test_changes.passed)} passed
                      </span>
                    ) : (
                      "—"
                    )
                  }
                  sub={
                    c.test_changes && c.test_changes.failed != null
                      ? `${signed(c.test_changes.failed)} failed`
                      : ""
                  }
                />
              </div>

              {c.metric_changes.length > 0 && (
                <Card title="Metric changes" pad>
                  <div className="stack" style={{ gap: 0 }}>
                    {c.metric_changes.map((m) => (
                      <div key={m.name} className="metric-row">
                        <span>{m.name}</span>
                        <span className="mono tnum">
                          {m.before ?? "—"} <span className="muted">→</span> {m.after ?? "—"}
                          {m.delta != null && (
                            <span className={m.delta <= 0 ? "plus" : "minus"} style={{ marginLeft: 8 }}>
                              ({signed(m.delta, 2)})
                            </span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              <Card title="Files" flush>
                {c.files.length === 0 ? (
                  <div className="card--pad muted">No file changes.</div>
                ) : (
                  <div className="files" style={{ padding: "12px 18px" }}>
                    {c.files.map((f) => (
                      <div key={f.path} className="files__row">
                        <span className={`files__mark files__mark--${f.change_type}`}>
                          {f.change_type[0].toUpperCase()}
                        </span>
                        <span className="mono truncate">{f.path}</span>
                        <span className="spacer" />
                        <span className="mono text-xs">
                          <span className="plus">+{f.additions}</span>{" "}
                          <span className="minus">−{f.deletions}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              {c.diff_text && (
                <Card title="Diff" flush>
                  <DiffView raw={c.diff_text} />
                </Card>
              )}
            </div>
          )}
        </Async>
      )}
    </>
  );
}
