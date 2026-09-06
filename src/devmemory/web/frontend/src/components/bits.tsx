import { Link } from "react-router-dom";
import type { VersionListItem } from "@/api/types";
import { StatusBadge } from "./primitives";
import { Icon } from "./Icon";
import { relativeTime, shortSha, vlabel } from "@/lib/format";

export function MetricChip({ name, value }: { name: string; value: number | string | null }) {
  return (
    <span className="pill">
      {name}
      <b style={{ color: "var(--text)" }}>{value ?? "—"}</b>
    </span>
  );
}

/** compact row used in lists across Overview / Timeline / Search */
export function VersionRow({ v }: { v: VersionListItem }) {
  const metrics = Object.entries(v.metrics ?? {}).slice(0, 2);
  return (
    <Link className="vrow" to={`/version/${v.version_id}`}>
      <span className="vrow__id">{vlabel(v.version_id)}</span>
      <StatusBadge status={v.status} />
      <span className="vrow__main">
        <span className="vrow__intent truncate">{v.intent ?? "—"}</span>
        <span className="vrow__meta">
          {v.feature && <span>{v.feature}</span>}
          {v.agent && <span>{v.agent}</span>}
          <span className="plus">+{v.lines_added}</span>
          <span className="minus">−{v.lines_removed}</span>
          {metrics.map(([k, val]) => (
            <span key={k} className="mono">
              {k} {val}
            </span>
          ))}
          {v.committed_at && <span>{relativeTime(v.committed_at)}</span>}
        </span>
      </span>
      <span className="pill vrow__sha">
        <Icon name="commit" size={11} />
        {shortSha(v.git_commit)}
      </span>
    </Link>
  );
}

/** tiny status dot used in strips / sparklines */
export function StatusDot({ status, size = 9 }: { status: string; size?: number }) {
  const tone =
    status === "SUCCESS" || status === "COMPLETE"
      ? "var(--ok)"
      : status === "REGRESSION" || status === "ERROR"
        ? "var(--bad)"
        : status === "PARTIAL_SUCCESS" || status === "NEEDS_REVIEW"
          ? "var(--warn)"
          : "var(--text-muted)";
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: "50%",
        background: tone,
        display: "inline-block",
        flex: "none",
      }}
    />
  );
}
