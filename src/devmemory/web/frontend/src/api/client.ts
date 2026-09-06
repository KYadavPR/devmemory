import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import type {
  AnalyticsSummary,
  ChangeGuidance,
  ComparisonResponse,
  DevelopmentTrace,
  DevelopmentVersion,
  FeatureDetail,
  GraphImpact,
  PreviousAttempt,
  ProjectBrief,
  ProjectSummary,
  SearchResponse,
  VersionListItem,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, { headers: { accept: "application/json" } });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body || res.statusText);
  }
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, text || res.statusText);
  }
  return res.json() as Promise<T>;
}

type QOpts<T> = Omit<UseQueryOptions<T, Error>, "queryKey" | "queryFn">;

export const useProject = (opts?: QOpts<ProjectSummary>) =>
  useQuery({ queryKey: ["project"], queryFn: () => apiGet<ProjectSummary>("/project"), ...opts });

export const useVersions = (limit = 500, opts?: QOpts<VersionListItem[]>) =>
  useQuery({
    queryKey: ["versions", limit],
    queryFn: () => apiGet<VersionListItem[]>(`/versions?limit=${limit}`),
    ...opts,
  });

export const useVersion = (ref: string | undefined, opts?: QOpts<DevelopmentVersion>) =>
  useQuery({
    queryKey: ["version", ref],
    queryFn: () => apiGet<DevelopmentVersion>(`/versions/${ref}`),
    enabled: !!ref,
    ...opts,
  });

export const useTrace = (ref: string | undefined, opts?: QOpts<DevelopmentTrace>) =>
  useQuery({
    queryKey: ["trace", ref],
    queryFn: () => apiGet<DevelopmentTrace>(`/versions/${ref}/trace`),
    enabled: !!ref,
    ...opts,
  });

export const useVersionDiff = (ref: string | undefined, opts?: QOpts<string>) =>
  useQuery({
    queryKey: ["diff", ref],
    queryFn: () => apiGet<string>(`/versions/${ref}/diff`),
    enabled: !!ref,
    ...opts,
  });

export const useVersionAttempts = (ref: string | undefined, opts?: QOpts<PreviousAttempt[]>) =>
  useQuery({
    queryKey: ["version-attempts", ref],
    queryFn: () => apiGet<PreviousAttempt[]>(`/versions/${ref}/attempts`),
    enabled: !!ref,
    ...opts,
  });

export const useVersionImpact = (ref: string | undefined, opts?: QOpts<GraphImpact | null>) =>
  useQuery({
    queryKey: ["impact", ref],
    queryFn: () => apiGet<GraphImpact>(`/versions/${ref}/impact`).catch(() => null),
    enabled: !!ref,
    ...opts,
  });

export const useFeatures = (opts?: QOpts<FeatureDetail[]>) =>
  useQuery({ queryKey: ["features"], queryFn: () => apiGet<FeatureDetail[]>("/features"), ...opts });

export const useFeature = (ref: string | undefined, opts?: QOpts<FeatureDetail>) =>
  useQuery({
    queryKey: ["feature", ref],
    queryFn: () => apiGet<FeatureDetail>(`/features/${encodeURIComponent(ref!)}`),
    enabled: !!ref,
    ...opts,
  });

export const useCompare = (from: string | undefined, to: string | undefined) =>
  useQuery({
    queryKey: ["compare", from, to],
    queryFn: () =>
      apiGet<ComparisonResponse>(
        `/compare?from=${encodeURIComponent(from!)}&to=${encodeURIComponent(to!)}`,
      ),
    enabled: !!from && !!to && from !== to,
  });

export const useAnalytics = (opts?: QOpts<AnalyticsSummary>) =>
  useQuery({
    queryKey: ["analytics"],
    queryFn: () => apiGet<AnalyticsSummary>("/analytics"),
    ...opts,
  });

export const useAgentContext = (opts?: QOpts<ProjectBrief>) =>
  useQuery({
    queryKey: ["agent-context"],
    queryFn: () => apiGet<ProjectBrief>("/agent/context"),
    ...opts,
  });

export const useAttempts = (q: string, opts?: QOpts<PreviousAttempt[]>) =>
  useQuery({
    queryKey: ["attempts", q],
    queryFn: () =>
      apiGet<PreviousAttempt[]>(`/attempts?limit=50${q ? `&q=${encodeURIComponent(q)}` : ""}`),
    ...opts,
  });

export const useSearch = (q: string) =>
  useQuery({
    queryKey: ["search", q],
    queryFn: () => apiGet<SearchResponse>(`/search?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length > 0,
  });

export const checkChange = (files: string[], intent: string, feature?: string) =>
  apiPost<ChangeGuidance>("/agent/check", { files, intent: intent || null, feature: feature || null });
