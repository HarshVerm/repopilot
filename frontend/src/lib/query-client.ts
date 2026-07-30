// Module purpose: Provide reusable query client frontend utilities.

import { QueryClient } from "@tanstack/react-query";

export const queryKeys = {
  tasks: ["tasks"] as const,
  currentUser: ["auth", "me"] as const,
  githubUserAuthorization: ["auth", "github-user-authorization"] as const,
  installations: ["github", "installations"] as const,
  /** Build the cache key for a filtered repository page. */
  repositories: (search: string, page: number) =>
    ["github", "repositories", search, page] as const,
  /** Build the cache key for one connected repository. */
  connectedRepository: (repositoryId: string) =>
    ["github", "repository", repositoryId] as const,
  /** Build the cache key for a filtered issue page. */
  connectedIssues: (repositoryId: string, search: string, page: number) =>
    ["github", "repository", repositoryId, "issues", search, page] as const,
  /** Build the cache key for one task. */
  task: (taskId: string) => ["task", taskId] as const,
  /** Build the cache key for a task timeline. */
  taskTimeline: (taskId: string) => ["task", taskId, "timeline"] as const,
  /** Build the cache key for task metrics. */
  taskMetrics: (taskId: string) => ["task", taskId, "metrics"] as const,
  /** Build the legacy cache key for repository metadata. */
  githubRepo: (owner: string, repo: string) => ["github", "repo", owner, repo] as const,
  /** Build the legacy cache key for a repository issue list. */
  githubIssues: (owner: string, repo: string, state: string) =>
    ["github", "issues", owner, repo, state] as const,
  /** Build the legacy cache key for one GitHub issue. */
  githubIssue: (owner: string, repo: string, issueNumber: number) =>
    ["github", "issue", owner, repo, issueNumber] as const,
  /** Build the cache key for one execution plan. */
  plan: (planId: string) => ["plan", planId] as const,
  /** Build the cache key for a change-set diff. */
  changeSetDiff: (changeSetId: string) => ["changeSet", changeSetId, "diff"] as const,
  /** Build the cache key for one sandbox execution. */
  executionRun: (executionRunId: string) => ["executionRun", executionRunId] as const,
  /** Build the cache key for one final review. */
  review: (reviewId: string) => ["review", reviewId] as const,
  /** Build the cache key for one publication. */
  publication: (publicationId: string) => ["publication", publicationId] as const,
  /** Build the cache key for publication associated with a review. */
  reviewPublication: (reviewId: string) => ["review", reviewId, "publication"] as const,
  health: ["health"] as const,
  readiness: ["ready"] as const,
  /** Build the cache key for one evaluation run. */
  evaluationRun: (runId: string) => ["evaluation", runId] as const,
};

/** Purpose: Create query client for this frontend workflow. */
export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: true,
        retry: (failureCount, error) => {
          const status = typeof error === "object" && error && "status" in error
            ? Number((error as { status: number }).status)
            : 0;

          if ([401, 403, 404, 409, 429].includes(status)) {
            return false;
          }

          return failureCount < 2;
        },
      },
      mutations: {
        retry: false,
      },
    },
  });
}
