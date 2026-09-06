import { useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";

/** Track an element's pixel width; re-renders on resize. */
function useElementWidth(fallback = 560): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setW(Math.max(240, el.clientWidth));
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/* ============================================================================
   Hand-rolled SVG charts. No chart library — full theme-token control, no
   animation quirks, tiny footprint. Follows the dataviz mark specs: 2px lines,
   >=8px markers, recessive grid, direct hover tooltips, one axis.
   ========================================================================= */

function useHover<T>() {
  const [hover, setHover] = useState<{ x: number; y: number; datum: T } | null>(null);
  return { hover, setHover };
}

function Tooltip({ x, y, children }: { x: number; y: number; children: ReactNode }) {
  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: "translate(-50%, calc(-100% - 10px))",
        background: "var(--bg-elevated)",
        border: "1px solid var(--border-strong)",
        borderRadius: "var(--r-2)",
        padding: "7px 10px",
        boxShadow: "var(--shadow-md)",
        fontSize: "0.75rem",
        lineHeight: 1.5,
        pointerEvents: "none",
        whiteSpace: "nowrap",
        zIndex: 5,
      }}
    >
      {children}
    </div>
  );
}

const PLOT = { top: 12, right: 16, bottom: 26, left: 40 };

function niceStep(range: number, count: number): number {
  const raw = range / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  return [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10;
}

function niceTicks(max: number, count = 4): number[] {
  const step = niceStep(max, count);
  const ticks: number[] = [];
  for (let t = 0; t <= max + step / 2; t += step) ticks.push(Math.round(t * 100) / 100);
  return ticks;
}

/** ticks covering [min,max], not forced through zero — for metrics like latency. */
function rangeTicks(min: number, max: number, count = 4): { lo: number; hi: number; ticks: number[] } {
  if (min === max) return { lo: min - 1, hi: max + 1, ticks: [min] };
  const step = niceStep(max - min, count);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let t = lo; t <= hi + step / 2; t += step) ticks.push(Math.round(t * 100) / 100);
  return { lo, hi, ticks };
}

/* -- line trend ---------------------------------------------------------- */

export interface TrendDatum {
  label: string;
  value: number | null;
  adverse: boolean;
  sub?: string;
}

export function TrendChart({ data, unit, height = 220 }: { data: TrendDatum[]; unit?: string; height?: number }) {
  const [wrapRef, w] = useElementWidth();
  const { hover, setHover } = useHover<TrendDatum>();
  const clipId = useId();

  const vals = data.map((d) => d.value).filter((v): v is number => v != null);
  const { lo, hi, ticks } = rangeTicks(vals.length ? Math.min(...vals) : 0, vals.length ? Math.max(...vals) : 1);

  const iw = w - PLOT.left - PLOT.right;
  const ih = height - PLOT.top - PLOT.bottom;
  const px = (i: number) => PLOT.left + (data.length <= 1 ? iw / 2 : (i / (data.length - 1)) * iw);
  const py = (v: number) => PLOT.top + ih - ((v - lo) / (hi - lo || 1)) * ih;

  const segs: string[] = [];
  let cur: string[] = [];
  data.forEach((d, i) => {
    if (d.value == null) {
      if (cur.length) segs.push(cur.join(" "));
      cur = [];
    } else {
      cur.push(`${cur.length ? "L" : "M"}${px(i).toFixed(1)},${py(d.value).toFixed(1)}`);
    }
  });
  if (cur.length) segs.push(cur.join(" "));

  return (
    <div ref={wrapRef} style={{ position: "relative", width: "100%" }}>
      <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} role="img">
        <defs>
          <clipPath id={clipId}>
            <rect x={PLOT.left} y={PLOT.top} width={iw} height={ih} />
          </clipPath>
        </defs>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={PLOT.left} x2={w - PLOT.right} y1={py(t)} y2={py(t)} stroke="var(--border)" />
            <text x={PLOT.left - 8} y={py(t)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill="var(--text-muted)">
              {t}
            </text>
          </g>
        ))}
        {data.map((d, i) => (
          <text key={i} x={px(i)} y={height - 8} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
            {d.label}
          </text>
        ))}
        <g clipPath={`url(#${clipId})`}>
          {segs.map((s, i) => (
            <path key={i} d={s} fill="none" stroke="var(--series-1)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
          ))}
        </g>
        {data.map((d, i) =>
          d.value == null ? null : (
            <circle
              key={i}
              cx={px(i)}
              cy={py(d.value)}
              r={d.adverse ? 5 : 4}
              fill={d.adverse ? "var(--bad)" : "var(--series-1)"}
              stroke="var(--bg-elevated)"
              strokeWidth={2}
            />
          ),
        )}
        {/* hover hit targets */}
        {data.map((d, i) =>
          d.value == null ? null : (
            <rect
              key={i}
              x={px(i) - iw / data.length / 2}
              y={PLOT.top}
              width={iw / data.length}
              height={ih}
              fill="transparent"
              onMouseEnter={() => setHover({ x: px(i), y: py(d.value!), datum: d })}
              onMouseLeave={() => setHover(null)}
            />
          ),
        )}
      </svg>
      {hover && (
        <Tooltip x={hover.x} y={hover.y}>
          <b>{hover.datum.label}</b>
          {hover.datum.sub && <div className="muted">{hover.datum.sub}</div>}
          <div>
            {hover.datum.value}
            {unit ? ` ${unit}` : ""}
          </div>
        </Tooltip>
      )}
    </div>
  );
}

/* -- horizontal bars --------------------------------------------------- */

export interface BarDatum {
  label: string;
  value: number;
  sub?: string;
  tone?: string;
}

export function HBarChart({ data, unit, max: maxProp }: { data: BarDatum[]; unit?: string; max?: number }) {
  const [wrapRef, w] = useElementWidth();
  const { hover, setHover } = useHover<BarDatum>();

  const labelW = 96;
  const max = maxProp ?? Math.max(...data.map((d) => d.value), 1);
  const rowH = 34;
  const height = data.length * rowH + 28;
  const trackX = labelW + 8;
  const trackW = w - trackX - 40;
  const ticks = niceTicks(max, 4);

  return (
    <div ref={wrapRef} style={{ position: "relative", width: "100%" }}>
      <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} role="img">
        {ticks.map((t) => {
          const x = trackX + (t / max) * trackW;
          return (
            <g key={t}>
              <line x1={x} x2={x} y1={4} y2={height - 22} stroke="var(--border)" />
              <text x={x} y={height - 6} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
                {t}
                {unit ?? ""}
              </text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const y = 8 + i * rowH;
          const bw = Math.max(2, (d.value / max) * trackW);
          return (
            <g
              key={d.label}
              onMouseEnter={() => setHover({ x: trackX + bw, y: y + 8, datum: d })}
              onMouseLeave={() => setHover(null)}
            >
              <text x={labelW} y={y + 11} textAnchor="end" fontSize={11} fill="var(--text-secondary)">
                {d.label.length > 14 ? d.label.slice(0, 13) + "…" : d.label}
              </text>
              <rect x={trackX} y={y} width={trackW} height={16} rx={4} fill="var(--bg-sunken)" />
              <rect x={trackX} y={y} width={bw} height={16} rx={4} fill={d.tone ?? "var(--series-1)"} />
            </g>
          );
        })}
      </svg>
      {hover && (
        <Tooltip x={hover.x} y={hover.y}>
          <b>{hover.datum.label}</b>
          <div>
            {hover.datum.value}
            {unit ?? ""}
          </div>
          {hover.datum.sub && <div className="muted">{hover.datum.sub}</div>}
        </Tooltip>
      )}
    </div>
  );
}

/* -- scatter --------------------------------------------------------- */

export interface ScatterDatum {
  x: number;
  y: number;
  label: string;
}

export function ChurnScatter({ data, height = 240 }: { data: ScatterDatum[]; height?: number }) {
  const [wrapRef, w] = useElementWidth();
  const { hover, setHover } = useHover<ScatterDatum>();

  const maxX = Math.max(...data.map((d) => d.x), 1);
  const maxY = Math.max(...data.map((d) => d.y), 1);
  const iw = w - PLOT.left - PLOT.right;
  const ih = height - PLOT.top - PLOT.bottom;
  const px = (v: number) => PLOT.left + (v / maxX) * iw;
  const py = (v: number) => PLOT.top + ih - (v / maxY) * ih;
  const xTicks = niceTicks(maxX, 4);
  const yTicks = niceTicks(maxY, 3);

  return (
    <div ref={wrapRef} style={{ position: "relative", width: "100%" }}>
      <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} role="img">
        {yTicks.map((t) => (
          <g key={"y" + t}>
            <line x1={PLOT.left} x2={w - PLOT.right} y1={py(t)} y2={py(t)} stroke="var(--border)" />
            <text x={PLOT.left - 8} y={py(t)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill="var(--text-muted)">
              {t}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={"x" + t} x={px(t)} y={height - 8} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
            {t}
          </text>
        ))}
        {data.map((d, i) => (
          <circle
            key={i}
            cx={px(d.x)}
            cy={py(d.y)}
            r={6}
            fill={d.y > 0 ? "var(--bad)" : "var(--series-1)"}
            fillOpacity={0.8}
            stroke="var(--bg-elevated)"
            strokeWidth={1.5}
            onMouseEnter={() => setHover({ x: px(d.x), y: py(d.y), datum: d })}
            onMouseLeave={() => setHover(null)}
          />
        ))}
      </svg>
      {hover && (
        <Tooltip x={hover.x} y={hover.y}>
          <b className="mono">{hover.datum.label}</b>
          <div>
            {hover.datum.x} changes · {hover.datum.y} adverse
          </div>
        </Tooltip>
      )}
    </div>
  );
}

