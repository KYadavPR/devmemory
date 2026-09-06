import { useId } from "react";

interface Point {
  value: number | null;
  label?: string;
  adverse?: boolean;
}

/** Minimal inline sparkline. Nulls break the line into segments. */
export function Sparkline({
  points,
  width = 240,
  height = 44,
  strokeVar = "--accent",
  fill = false,
}: {
  points: Point[];
  width?: number;
  height?: number;
  strokeVar?: string;
  fill?: boolean;
}) {
  const gid = useId();
  const vals = points.map((p) => p.value).filter((v): v is number => v != null);
  if (vals.length < 2) return <span className="muted text-xs">not enough data</span>;

  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const pad = 4;
  const n = points.length;

  const coords = points.map((p, i) => ({
    x: n === 1 ? width / 2 : (i / (n - 1)) * (width - pad * 2) + pad,
    y: p.value == null ? null : height - pad - ((p.value - min) / range) * (height - pad * 2),
    p,
  }));

  const segments: string[] = [];
  let cur: string[] = [];
  for (const c of coords) {
    if (c.y == null) {
      if (cur.length) segments.push(cur.join(" "));
      cur = [];
    } else {
      cur.push(`${cur.length ? "L" : "M"}${c.x.toFixed(1)},${c.y.toFixed(1)}`);
    }
  }
  if (cur.length) segments.push(cur.join(" "));

  const areaD =
    fill && segments.length === 1
      ? `${segments[0]} L${coords[coords.length - 1].x.toFixed(1)},${height} L${coords[0].x.toFixed(1)},${height} Z`
      : null;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} preserveAspectRatio="none">
      {areaD && (
        <>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={`var(${strokeVar})`} stopOpacity={0.18} />
              <stop offset="100%" stopColor={`var(${strokeVar})`} stopOpacity={0} />
            </linearGradient>
          </defs>
          <path d={areaD} fill={`url(#${gid})`} />
        </>
      )}
      {segments.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="none"
          stroke={`var(${strokeVar})`}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
      {coords.map((c, i) =>
        c.y == null ? null : (
          <circle
            key={i}
            cx={c.x}
            cy={c.y}
            r={c.p.adverse ? 3.5 : 2.5}
            fill={c.p.adverse ? "var(--bad)" : `var(${strokeVar})`}
          >
            {c.p.label && <title>{c.p.label}</title>}
          </circle>
        ),
      )}
    </svg>
  );
}
