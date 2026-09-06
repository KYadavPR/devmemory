import { useState } from "react";
import { Link } from "react-router-dom";
import { useVersions } from "@/api/client";
import { Async } from "@/components/Async";
import { PageHead, StatusBadge, Card } from "@/components/primitives";
import { MetricChip } from "@/components/bits";
import { Icon } from "@/components/Icon";
import { absTime, relativeTime, shortSha, vlabel } from "@/lib/format";
import { statusTone } from "@/lib/status";
import type { VersionListItem } from "@/api/types";

type StatusFilter = "all" | "adverse" | "success";

export function Timeline() {
  const query = useVersions(500);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [feature, setFeature] = useState<string>("all");

  return (
    <>
      <PageHead
        title="Timeline"
        subtitle="Every development version, newest first — intent, outcome, and what moved."
      />
      <Async query={query} isEmpty={(d) => d.length === 0} empty={<EmptyTimeline />}>
        {(versions) => {
          const features = Array.from(
            new Set(versions.map((v) => v.feature).filter(Boolean) as string[]),
          ).sort();

          const filtered = versions
            .filter((v) => {
              if (status === "adverse") return v.status === "REGRESSION" || v.status === "ERROR";
              if (status === "success") return v.status === "SUCCESS";
              return true;
            })
            .filter((v) => feature === "all" || v.feature === feature)
            .slice()
            .reverse();

          return (
            <>
              <div className="row row--wrap" style={{ marginBottom: 16, gap: 8 }}>
                <Segmented
                  value={status}
                  onChange={setStatus}
                  options={[
                    ["all", `All ${versions.length}`],
                    ["adverse", "Regressions"],
                    ["success", "Successes"],
                  ]}
                />
                {features.length > 0 && (
                  <select className="input" style={{ width: "auto" }} value={feature} onChange={(e) => setFeature(e.target.value)}>
                    <option value="all">All features</option>
                    {features.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {filtered.length === 0 ? (
                <Card pad>
                  <div className="muted">No versions match this filter.</div>
                </Card>
              ) : (
                <Card flush>
                  <div className="tl">
                    {filtered.map((v) => (
                      <TimelineItem key={v.version_id} v={v} />
                    ))}
                  </div>
                </Card>
              )}
            </>
          );
        }}
      </Async>
    </>
  );
}

function TimelineItem({ v }: { v: VersionListItem }) {
  const tone = statusTone(v.status);
  const metrics = Object.entries(v.metrics ?? {});
  return (
    <div className={`tl__item tl__item--${tone}`}>
      <div className="tl__dot" />
      <div className="tl__body">
        <div className="row row--wrap" style={{ gap: 8 }}>
          <Link className="link" to={`/version/${v.version_id}`} style={{ fontWeight: 640 }}>
            {vlabel(v.version_id)}
          </Link>
          <StatusBadge status={v.status} />
          {v.checkpoint_id ? (
            <span className="pill">◈ {v.checkpoint_id.slice(0, 10)}</span>
          ) : (
            <span className="badge badge--neutral">
              <span className="badge__dot" />
              no checkpoint
            </span>
          )}
          <span className="pill">
            <Icon name="commit" size={11} />
            {shortSha(v.git_commit)}
          </span>
          <span className="spacer" />
          <span className="muted text-xs" title={absTime(v.committed_at)}>
            {relativeTime(v.committed_at)}
          </span>
        </div>
        <div className="tl__intent">{v.intent ?? "—"}</div>
        <div className="tl__sub">
          {v.agent && <span>{v.agent}</span>}
          {v.model && <span>{v.model}</span>}
          {v.feature && <span>{v.feature}</span>}
          <span>
            <span className="plus">+{v.lines_added}</span>{" "}
            <span className="minus">−{v.lines_removed}</span> · {v.files_changed} file
            {v.files_changed === 1 ? "" : "s"}
          </span>
          {v.tests_passed != null && (
            <span>
              {v.tests_passed} passed{v.tests_failed ? ` / ${v.tests_failed} failed` : ""}
            </span>
          )}
        </div>
        {metrics.length > 0 && (
          <div className="row row--wrap" style={{ gap: 6, marginTop: 8 }}>
            {metrics.map(([k, val]) => (
              <MetricChip key={k} name={k} value={val} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: [T, string][];
}) {
  return (
    <div className="segmented">
      {options.map(([val, label]) => (
        <button
          key={val}
          className={`segmented__btn${value === val ? " segmented__btn--active" : ""}`}
          onClick={() => onChange(val)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function EmptyTimeline() {
  return (
    <Card pad>
      <div className="state">
        <Icon name="timeline" size={40} className="state__icon" />
        <div className="state__title">No versions yet</div>
        <div className="state__sub">
          Make a commit, then run <code>devmemory checkpoint</code>.
        </div>
      </div>
    </Card>
  );
}
