import type { ReactNode } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { EmptyState, SkeletonRows } from "./primitives";

interface Props<T> {
  query: UseQueryResult<T>;
  /** custom skeleton; defaults to a few rows */
  skeleton?: ReactNode;
  /** treat this as "empty" and show the empty state instead of children */
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}

export function Async<T>({ query, skeleton, isEmpty, empty, children }: Props<T>) {
  if (query.isLoading) return <>{skeleton ?? <SkeletonRows />}</>;
  if (query.isError) {
    return (
      <EmptyState
        icon="alert"
        title="Couldn't load this"
        sub={(query.error as Error)?.message ?? "Request failed"}
      >
        <button className="btn" onClick={() => query.refetch()}>
          Retry
        </button>
      </EmptyState>
    );
  }
  const data = query.data as T;
  if (data === undefined) return <>{skeleton ?? <SkeletonRows />}</>;
  if (isEmpty?.(data)) return <>{empty ?? <EmptyState title="Nothing yet" />}</>;
  return <>{children(data)}</>;
}
