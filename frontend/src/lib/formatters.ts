// Module purpose: Provide reusable formatters frontend utilities.

import type { TaskResponse } from "@/types/api";

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const compactFormatter = new Intl.NumberFormat(undefined, {
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Purpose: Handle repository full name for this frontend module. */
export function repositoryFullName(task: Pick<TaskResponse, "repository">) {
  return `${task.repository.owner}/${task.repository.repo}`;
}

/** Purpose: Format date time for this frontend workflow. */
export function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return "—";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return dateFormatter.format(date);
}

/** Purpose: Format duration for this frontend workflow. */
export function formatDuration(startedAt?: string | null, endedAt?: string | null) {
  if (!startedAt) {
    return "—";
  }

  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) {
    return "—";
  }

  const seconds = Math.floor((end - start) / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

/** Purpose: Format number for this frontend workflow. */
export function formatNumber(value: unknown) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }

  return compactFormatter.format(value);
}

/** Purpose: Format status for this frontend workflow. */
export function formatStatus(value: string) {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

/** Purpose: Handle short sha for this frontend module. */
export function shortSha(value: string | null | undefined) {
  return value ? value.slice(0, 12) : "—";
}

/** Purpose: Handle metric value for this frontend module. */
export function metricValue(metrics: Record<string, unknown> | null | undefined, path: string[]) {
  let current: unknown = metrics;
  for (const key of path) {
    if (!current || typeof current !== "object" || !(key in current)) {
      return undefined;
    }
    current = (current as Record<string, unknown>)[key];
  }

  return current;
}
