/**
 * Motion primitives — a small, consistent vocabulary of tactile spring
 * animation for the dashboard. Deliberately narrow: entrance pops, press
 * squish, a drawn checkmark, staggered dots. Every consumer respects the
 * viewer's reduced-motion preference (a `<MotionConfig reducedMotion="user">`
 * wraps the app, and `useReducedMotion()` gates the discretionary bits).
 */
import type { ReactNode } from "react";
import { m, useReducedMotion, type Transition } from "motion/react";

// `m` + LazyMotion keeps the animation runtime out of the initial bundle
// (loaded once, on first use). Consumers use `m.*`, never `motion.*`.
export { m, AnimatePresence, LazyMotion, domAnimation, MotionConfig, useReducedMotion } from "motion/react";

export const spring = {
  /** quick, minimal overshoot — buttons, pills, tiles */
  snappy: { type: "spring", stiffness: 520, damping: 34, mass: 0.7 } as Transition,
  /** soft settle — banners, panels */
  gentle: { type: "spring", stiffness: 260, damping: 26 } as Transition,
  /** visible bounce — the payoff moments only (NEEDS_WORK → READY) */
  bouncy: { type: "spring", stiffness: 420, damping: 17 } as Transition,
} as const;

/** Press-squish: wrap an interactive element so it gives under the pointer. */
export function Pressable({
  children,
  className,
  disabled,
  onClick,
  title,
  as = "button",
}: {
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  onClick?: () => void;
  title?: string;
  as?: "button" | "div";
}) {
  const reduce = useReducedMotion();
  const Comp = as === "div" ? m.div : m.button;
  return (
    <Comp
      className={className}
      disabled={as === "button" ? disabled : undefined}
      onClick={onClick}
      title={title}
      whileTap={reduce || disabled ? undefined : { scale: 0.94 }}
      transition={spring.snappy}
    >
      {children}
    </Comp>
  );
}

/** Entrance pop — for a row/card appearing for the first time. */
export function Pop({
  children,
  className,
  delay = 0,
  style,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  style?: React.CSSProperties;
}) {
  const reduce = useReducedMotion();
  if (reduce) {
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  }
  return (
    <m.div
      className={className}
      style={style}
      initial={{ opacity: 0, scale: 0.97, y: 4 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ ...spring.snappy, delay }}
    >
      {children}
    </m.div>
  );
}

/** A checkmark that draws itself in. Falls back to a static tick. */
export function DrawCheck({ size = 18, color = "currentColor" }: { size?: number; color?: string }) {
  const reduce = useReducedMotion();
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <m.path
        d="M20 6 9 17l-5-5"
        stroke={color}
        strokeWidth={2.6}
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={reduce ? { pathLength: 1 } : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={reduce ? { duration: 0 } : { duration: 0.32, ease: [0.65, 0, 0.35, 1], delay: 0.08 }}
      />
    </svg>
  );
}

/** Three dots with a staggered spring bob — a "thinking" indicator with life. */
export function ThinkingDots({ color = "currentColor" }: { color?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <span className="mono">…</span>;
  return (
    <span style={{ display: "inline-flex", gap: 4, alignItems: "center", height: 12 }}>
      {[0, 1, 2].map((i) => (
        <m.span
          key={i}
          style={{ width: 5, height: 5, borderRadius: "50%", background: color, display: "block" }}
          animate={{ y: [0, -4, 0] }}
          transition={{ duration: 0.6, repeat: Infinity, ease: "easeInOut", delay: i * 0.12 }}
        />
      ))}
    </span>
  );
}
