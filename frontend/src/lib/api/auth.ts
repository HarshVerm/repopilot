// Module purpose: Provide typed API operations for auth.

import type {
  CurrentUserResponse,
  GitHubInstallationListResponse,
  GitHubUserAuthorizationResponse,
} from "@/types/api";
import { apiRequest, apiUrl } from "./client";

/** Purpose: Return current user for this frontend workflow. */
export function getCurrentUser(signal?: AbortSignal) {
  return apiRequest<CurrentUserResponse>("/api/v1/auth/me", {
    signal,
  });
}

/** Purpose: Handle github login url for this frontend module. */
export function githubLoginUrl(redirectTo = "/tasks") {
  return apiUrl(
    `/api/v1/auth/github/login?redirect_to=${encodeURIComponent(redirectTo)}`,
  );
}

/** Purpose: Handle logout for this frontend module. */
export function logout() {
  return apiRequest<{ logged_out: boolean }>("/api/v1/auth/logout", {
    method: "POST",
  });
}

/** Purpose: Return git hub setup url for this frontend workflow. */
export function getGitHubSetupUrl() {
  return apiRequest<{ url: string }>(
    "/api/v1/auth/github/installations/setup",
  );
}

/** Purpose: Return git hub user authorization for this frontend workflow. */
export function getGitHubUserAuthorization(signal?: AbortSignal) {
  return apiRequest<GitHubUserAuthorizationResponse>(
    "/api/v1/auth/github/user-authorization",
    { signal },
  );
}

/** Purpose: Return git hub user authorization setup url for this frontend workflow. */
export function getGitHubUserAuthorizationSetupUrl() {
  return apiRequest<{ url: string }>(
    "/api/v1/auth/github/user-authorization/setup",
  );
}

/** Purpose: List installations for this frontend workflow. */
export function listInstallations(signal?: AbortSignal) {
  return apiRequest<GitHubInstallationListResponse>(
    "/api/v1/github/installations",
    { signal },
  );
}
