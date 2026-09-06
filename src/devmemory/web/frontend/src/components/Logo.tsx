// DevMemory mark: a "memory node" — a ring with two connector nodes, echoing a
// version graph. Uses the accent token so it adapts to the theme.
export function Logo({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true" style={{ flex: "none" }}>
      <rect width="32" height="32" rx="8" fill="var(--accent)" />
      <path
        d="M10 8h5.5a8 8 0 0 1 0 16H10z"
        fill="none"
        stroke="var(--text-on-accent)"
        strokeWidth="2.5"
      />
      <circle cx="10" cy="8" r="2.4" fill="var(--text-on-accent)" />
      <circle cx="10" cy="24" r="2.4" fill="var(--text-on-accent)" />
    </svg>
  );
}
