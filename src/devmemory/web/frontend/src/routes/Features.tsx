import { Link } from "react-router-dom";
import { useFeatures } from "@/api/client";
import { Async } from "@/components/Async";
import { PageHead, StatusBadge, EmptyState } from "@/components/primitives";
import { StatusDot } from "@/components/bits";
import { featureName, vlabel } from "@/lib/format";

export function Features() {
  const query = useFeatures();
  return (
    <>
      <PageHead title="Features" subtitle="How each feature area evolved across versions." />
      <Async
        query={query}
        isEmpty={(d) => d.length === 0}
        empty={
          <EmptyState
            icon="features"
            title="No features tracked yet"
            sub={
              <>
                Tag a checkpoint with <code>devmemory checkpoint --feature &lt;name&gt;</code>.
              </>
            }
          />
        }
      >
        {(features) => (
          <div className="grid grid--2">
            {features.map((f) => {
              const metrics = Object.entries(f.latest_metrics);
              const regressions = f.history.filter(
                (h) => h.status === "REGRESSION" || h.status === "ERROR",
              ).length;
              return (
                <Link
                  key={f.feature_id}
                  to={`/feature/${encodeURIComponent(featureName(f.feature_id))}`}
                  className="feat-card card card--pad"
                >
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <b style={{ fontSize: "0.9375rem" }}>{f.name}</b>
                    <StatusBadge status={f.status} />
                  </div>
                  <div className="muted text-sm" style={{ margin: "6px 0 10px" }}>
                    {f.version_count} version{f.version_count === 1 ? "" : "s"}
                    {regressions > 0 && ` · ${regressions} regression${regressions === 1 ? "" : "s"}`}
                    {metrics.length > 0 &&
                      ` · ${metrics.map(([k, v]) => `${k} ${v}`).join(", ")}`}
                  </div>
                  <div className="feat-card__track">
                    {f.history.map((h) => (
                      <span key={h.version_id} className="feat-card__node" title={`${vlabel(h.version_id)} · ${h.status}`}>
                        <StatusDot status={h.status} size={10} />
                        <span className="feat-card__vid">{vlabel(h.version_id)}</span>
                      </span>
                    ))}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </Async>
    </>
  );
}
