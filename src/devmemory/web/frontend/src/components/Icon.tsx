import type { SVGProps } from "react";

// Stroke-based 24px icon set. `d` paths only; consistent 2px stroke.
const PATHS = {
  overview: "M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z",
  timeline: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3.5 2",
  features: "M12 3 2 8l10 5 10-5zM2 13l10 5 10-5M2 8v5m20-5v5",
  compare: "M9 4v16M15 4v16M4 8l3-3 3 3M20 16l-3 3-3-3",
  memory:
    "M9 4a5 5 0 0 0-5 5v6a5 5 0 0 0 5 5h1V4zM15 4a5 5 0 0 1 5 5v6a5 5 0 0 1-5 5h-1V4zM7 9h.01M7 13h.01M17 9h-.01M17 13h-.01",
  intelligence: "M4 4v15a1 1 0 0 0 1 1h15M8 15l3-4 3 2 4-6",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-3.5-3.5",
  shield: "M12 3 5 6v6c0 4.4 3 7.6 7 9 4-1.4 7-4.6 7-9V6zM9.5 12l1.8 1.8 3.7-3.8",
  sun: "M12 5a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z",
  monitor: "M3 5h18v11H3zM8 21h8M12 16v5",
  command: "M9 9V6a3 3 0 1 0-3 3zM15 9h3a3 3 0 1 0-3-3zM15 15v3a3 3 0 1 0 3-3zM9 15H6a3 3 0 1 0 3 3zM9 9h6v6H9z",
  arrowRight: "M5 12h14M13 6l6 6-6 6",
  chevronRight: "M9 6l6 6-6 6",
  chevronDown: "M6 9l6 6 6-6",
  external: "M14 5h5v5M19 5l-8 8M18 14v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h5",
  check: "M5 13l4 4L19 7",
  x: "M6 6l12 12M18 6 6 18",
  alert: "M12 3 2 20h20zM12 9v5M12 17h.01",
  commit: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM3 12h5M16 12h5",
  plus: "M12 5v14M5 12h14",
  minus: "M5 12h14",
  sparkles: "M12 3l1.8 4.7L18.5 9.5 13.8 11.3 12 16l-1.8-4.7L5.5 9.5l4.7-1.8zM19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z",
  flame: "M12 3s5 4 5 9a5 5 0 0 1-10 0c0-1.5.6-2.8 1.4-3.8C8.8 9.6 9 11 10.5 11c0-2 1.5-4.5 1.5-8z",
  target: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z",
  history: "M3 12a9 9 0 1 0 3-6.7M3 4v4h4M12 8v4l3 2",
  layers: "M12 3 2 8l10 5 10-5zM2 13l10 5 10-5",
  file: "M13 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8zM13 3v5h5",
  filter: "M4 5h16l-6 8v6l-4-2v-4z",
  inbox: "M3 13h5l1 3h6l1-3h5M4 13 6 5h12l2 8v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z",
  copy: "M9 9h10v10H9zM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1",
  refresh: "M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5",
} as const;

export type IconName = keyof typeof PATHS;

interface Props extends Omit<SVGProps<SVGSVGElement>, "name"> {
  name: IconName;
  size?: number;
}

export function Icon({ name, size = 16, ...rest }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
