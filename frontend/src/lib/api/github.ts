// Module purpose: Provide typed API operations for github.

import type {
  ConnectedRepositoryListResponse,
  ConnectedRepositoryResponse,
  CreateIssueRequest,
  IssueListResponse,
  IssueResponse,
  RepositoryFileListResponse,
} from "@/types/api";
import { apiRequest } from "./client";

/** Purpose: List connected repositories for this frontend workflow. */
export function listConnectedRepositories(
  options: {
    search?: string;
    page?: number;
    perPage?: number;
    includeArchived?: boolean;
    refresh?: boolean;
  } = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams();
  if (options.search) params.set("search", options.search);
  params.set("page", String(options.page ?? 1));
  params.set("per_page", String(options.perPage ?? 30));
  if (options.includeArchived) params.set("include_archived", "true");
  if (options.refresh) params.set("refresh", "true");
  return apiRequest<ConnectedRepositoryListResponse>(
    `/api/v1/github/repositories?${params.toString()}`,
    { signal },
  );
}

/** Purpose: Return connected repository for this frontend workflow. */
export function getConnectedRepository(
  repositoryId: string,
  signal?: AbortSignal,
) {
  return apiRequest<ConnectedRepositoryResponse>(
    `/api/v1/github/repositories/${repositoryId}`,
    { signal },
  );
}

/** Purpose: List connected repository issues for this frontend workflow. */
export function listConnectedRepositoryIssues(
  repositoryId: string,
  options: { search?: string; page?: number; perPage?: number } = {},
  signal?: AbortSignal,
) {
  const params = new URLSearchParams({
    state: "open",
    page: String(options.page ?? 1),
    per_page: String(options.perPage ?? 30),
  });
  if (options.search) params.set("search", options.search);
  return apiRequest<IssueListResponse>(
    `/api/v1/github/repositories/${repositoryId}/issues?${params.toString()}`,
    { signal },
  );
}

/** Purpose: Return connected repository issue for this frontend workflow. */
export function getConnectedRepositoryIssue(
  repositoryId: string,
  issueNumber: number,
  signal?: AbortSignal,
) {
  return apiRequest<IssueResponse>(
    `/api/v1/github/repositories/${repositoryId}/issues/${issueNumber}`,
    { signal },
  );
}

/** Purpose: List selectable files from a connected repository default branch. */
export function listConnectedRepositoryFiles(
  repositoryId: string,
  signal?: AbortSignal,
) {
  return apiRequest<RepositoryFileListResponse>(
    `/api/v1/github/repositories/${repositoryId}/files?limit=5000`,
    { signal },
  );
}

/** Purpose: Create an issue in a connected repository as the signed-in user. */
export function createConnectedRepositoryIssue(
  repositoryId: string,
  payload: CreateIssueRequest,
) {
  return apiRequest<IssueResponse>(
    `/api/v1/github/repositories/${repositoryId}/issues`,
    {
      method: "POST",
      body: payload,
    },
  );
}
