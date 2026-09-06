import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { statusLabel, statusTone, type Tone } from "@/lib/status";

/* ---- Badge -------------------------------------------------------------- */

export function Badge({
  tone = "neutral",
  dot = true,
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  children: ReactNode;
}) {
  return (
    <span className={`badge badge--${tone}`}>
      {dot && <span className="badge__dot" />}
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  return (
    <Badge tone={statusTone(status)}>{statusLabel(status)}</Badge>
  );
}

/* ---- Card -------------------------------------------------------------- */

export function Card({
  title,
  action,
  pad = false,
  flush = false,
  className = "",
  style,
  children,
}: {
  title?: ReactNode;
  action?: ReactNode;
  pad?: boolean;
  flush?: boolean;
  className?: string;
  style?: React.CSSProperties;
  children: ReactNode;
}) {
  return (
    <section className={`card ${className}`} style={style}>
      {title && (
        <header className="card__head">
          <span className="h-section">{title}</span>
          {action}
        </header>
      )}
      {pad ? (
        <div className="card--pad">{children}</div>
      ) : flush ? (
        children
      ) : (
        <div className="card__body">{children}</div>
      )}
    </section>
  );
}

/* ---- StatTile -------------------------------------------------------- */

export function StatTile({
  label,
  value,
  sub,
  tone,
  icon,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  icon?: IconName;
}) {
  return (
    <div className="stat-tile card">
      <div className="stat-tile__label">
        {icon && <Icon name={icon} size={13} />}
        {label}
      </div>
      <div className={`stat-tile__value${tone ? ` stat-tile__value--${tone}` : ""}`}>{value}</div>
      {sub && <div className="stat-tile__sub">{sub}</div>}
    </div>
  );
}

/* ---- EmptyState ---------------------------------------------------- */

export function EmptyState({
  icon = "inbox",
  title,
  sub,
  children,
}: {
  icon?: IconName;
  title: string;
  sub?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="state">
      <Icon name={icon} size={40} className="state__icon" />
      <div className="state__title">{title}</div>
      {sub && <div className="state__sub">{sub}</div>}
      {children && <div style={{ marginTop: 16 }}>{children}</div>}
    </div>
  );
}

/* ---- Skeleton ---------------------------------------------------- */

export function Skeleton({
  h = 16,
  w = "100%",
  r,
  style,
}: {
  h?: number | string;
  w?: number | string;
  r?: number | string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className="skeleton"
      style={{ height: h, width: w, borderRadius: r ?? "var(--r-1)", ...style }}
    />
  );
}

export function SkeletonRows({ rows = 4, gap = 12 }: { rows?: number; gap?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap }}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} h={44} />
      ))}
    </div>
  );
}

/* ---- Pill ------------------------------------------------------- */

export function Sha({ sha, prefix }: { sha: string | null | undefined; prefix?: string }) {
  if (!sha) return <span className="muted">—</span>;
  return (
    <span className="pill">
      {prefix}
      {String(sha).slice(0, 8)}
    </span>
  );
}

/* ---- PageHead ------------------------------------------------- */

export function PageHead({
  title,
  subtitle,
  actions,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="page-head">
      <div className="page-head__row">
        <div style={{ minWidth: 0 }}>
          <h1 className="h-page">{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {actions && <div className="row row--wrap">{actions}</div>}
      </div>
    </div>
  );
}

/* ---- DeltaText ---------------------------------------------- */

export function Delta({
  before,
  after,
  trend,
  unit,
}: {
  before: number | null;
  after: number | null;
  trend: "up" | "down" | "flat";
  unit?: string | null;
}) {
  const cls = trend === "up" ? "plus" : trend === "down" ? "minus" : "muted";
  return (
    <span className="mono tnum" style={{ fontSize: "0.8125rem" }}>
      {before != null && (
        <>
          <span className="muted">{before}</span>
          <span className="muted" style={{ margin: "0 5px" }}>
            →
          </span>
        </>
      )}
      <span className={cls}>
        {after ?? "—"}
        {unit ? ` ${unit}` : ""}
      </span>
    </span>
  );
}
