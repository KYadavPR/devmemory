import { Link, useParams } from "react-router-dom";
import { useFeature } from "@/api/client";
import { Async } from "@/components/Async";
import { Card, PageHead, StatusBadge } from "@/components/primitives";
import { MetricChip } from "@/components/bits";
import { Sparkline } from "@/components/Sparkline";
import { absTime, relativeTime, vlabel } from "@/lib/format";
import { statusTone } from "@/lib/status";

export function FeatureDetail() {
  const { name } = useParams<{ name: string }>();
  const query = useFeature(name);

  return (
    <Async query={query} skeleton={<PageHead title="…" />}>
      {(f) => {
        const metricKeys = Array.from(
          new Set(f.history.flatMap((h) => Object.keys(h.metrics))),
        );
        const primary = metricKeys[0];
        return (
          <>
            <PageHead
              title={f.name}
              subtitle={
                <>
                  <StatusBadge status={f.status} /> &nbsp;· {f.version_count} version
                  {f.version_count === 1 ? "" : "s"}
                  {f.derived_from ? ` · from ${f.derived_from}` : ""}
                </>
              }
            />

            {primary && f.history.length > 1 && (
              <Card title={`${primary} across attempts`} pad>
                <Sparkline
                  points={f.history.map((h) => ({
                    value: h.metrics[primary] ?? null,
                    label: `${vlabel(h.version_id)}: ${h.metrics[primary]}`,
                    adverse: h.status === "REGRESSION" || h.status === "ERROR",
                  }))}
                  width={620}
                  height={60}
                  fill
                />
              </Card>
            )}

            <Card title="Attempts" flush style={{ marginTop: 16 }}>
              <div className="tl">
                {f.history
                  .slice()
                  .reverse()
                  .map((h) => (
                    <div key={h.version_id} className={`tl__item tl__item--${statusTone(h.status)}`}>
                      <div className="tl__dot" />
                      <div className="tl__body">
                        <div className="row row--wrap" style={{ gap: 8 }}>
                          <Link className="link" to={`/version/${h.version_id}`} style={{ fontWeight: 640 }}>
                            {vlabel(h.version_id)}
                          </Link>
                          <StatusBadge status={h.status} />
                          <span className="spacer" />
                          <span className="muted text-xs" title={absTime(h.committed_at)}>
                            {relativeTime(h.committed_at)}
                          </span>
                        </div>
                        {Object.keys(h.metrics).length > 0 && (
                          <div className="row row--wrap" style={{ gap: 6, marginTop: 6 }}>
                            {Object.entries(h.metrics).map(([k, v]) => (
                              <MetricChip key={k} name={k} value={v} />
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
              </div>
            </Card>
          </>
        );
      }}
    </Async>
  );
}
