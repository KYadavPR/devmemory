import type { VersionStatus } from "@/api/types";

export type Tone = "ok" | "bad" | "warn" | "info" | "neutral" | "accent";

const STATUS_TONE: Record<string, Tone> = {
  SUCCESS: "ok",
  COMPLETE: "ok",
  PASS: "ok",
  REGRESSION: "bad",
  ERROR: "bad",
  FAILED: "bad",
  PARTIAL_SUCCESS: "warn",
  NEEDS_REVIEW: "warn",
  PARTIAL: "warn",
  IN_PROGRESS: "info",
  NOT_STARTED: "neutral",
};

export const statusTone = (s: string | null | undefined): Tone =>
  (s && STATUS_TONE[s.toUpperCase()]) || "neutral";

const STATUS_LABEL: Record<string, string> = {
  SUCCESS: "Success",
  PARTIAL_SUCCESS: "Partial",
  REGRESSION: "Regression",
  ERROR: "Error",
  NEEDS_REVIEW: "Needs review",
  IN_PROGRESS: "In progress",
  COMPLETE: "Complete",
  NOT_STARTED: "Not started",
};

export const statusLabel = (s: string | null | undefined): string =>
  (s && STATUS_LABEL[s.toUpperCase()]) || s || "—";

export const isAdverse = (s: VersionStatus | string | null | undefined): boolean =>
  s === "REGRESSION" || s === "ERROR";

export const severityTone = (sev: string): Tone => {
  const s = sev.toUpperCase();
  if (s === "HIGH") return "bad";
  if (s === "MEDIUM") return "warn";
  return "neutral";
};

export const riskTone = (risk: string | null | undefined): Tone => {
  switch ((risk || "").toLowerCase()) {
    case "high":
      return "bad";
    case "medium":
      return "warn";
    case "low":
      return "ok";
    default:
      return "neutral";
  }
};

// verdict from /api/agent/check
export const verdictTone = (verdict: string): Tone => {
  const v = verdict.toLowerCase();
  if (v.includes("high") || v.includes("stop") || v.includes("danger")) return "bad";
  if (v.includes("caution") || v.includes("review") || v.includes("medium")) return "warn";
  if (v.includes("clear") || v.includes("low") || v.includes("safe")) return "ok";
  return "info";
};

export const metricTrend = (
  before: number | null,
  after: number | null,
  direction: string,
): "up" | "down" | "flat" => {
  if (before == null || after == null || before === after) return "flat";
  const better =
    direction === "lower_is_better" ? after < before : direction === "higher_is_better" ? after > before : null;
  if (better == null) return "flat";
  return better ? "up" : "down";
};
