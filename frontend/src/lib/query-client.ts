import { QueryClient } from "@tanstack/react-query";

export const queryKeys = {
  tasks: ["tasks"] as const,
  currentUser: ["auth", "me"] as const,
  installations: ["github", "installations"] as const,
  repositories: (search: string, page: number) =>
    ["github", "repositories", search, page] as const,
  connectedRepository: (repositoryId: string) =>
    ["github", "repository", repositoryId] as const,
  connectedIssues: (repositoryId: string, search: string, page: number) =>
    ["github", "repository", repositoryId, "issues", search, page] as const,
  task: (taskId: string) => ["task", taskId] as const,
  taskTimeline: (taskId: string) => ["task", taskId, "timeline"] as const,
  taskMetrics: (taskId: string) => ["task", taskId, "metrics"] as const,
  githubRepo: (owner: string, repo: string) => ["github", "repo", owner, repo] as const,
  githubIssues: (owner: string, repo: string, state: string) =>
    ["github", "issues", owner, repo, state] as const,
  githubIssue: (owner: string, repo: string, issueNumber: number) =>
    ["github", "issue", owner, repo, issueNumber] as const,
  plan: (planId: string) => ["plan", planId] as const,
  changeSetDiff: (changeSetId: string) => ["changeSet", changeSetId, "diff"] as const,
  executionRun: (executionRunId: string) => ["executionRun", executionRunId] as const,
  review: (reviewId: string) => ["review", reviewId] as const,
  publication: (publicationId: string) => ["publication", publicationId] as const,
  reviewPublication: (reviewId: string) => ["review", reviewId, "publication"] as const,
  health: ["health"] as const,
  readiness: ["ready"] as const,
  evaluationRun: (runId: string) => ["evaluation", runId] as const,
};

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
