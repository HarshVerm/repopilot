import type {
  CurrentUserResponse,
  GitHubInstallationListResponse,
} from "@/types/api";
import { apiRequest, apiUrl } from "./client";

export function getCurrentUser(signal?: AbortSignal) {
  return apiRequest<CurrentUserResponse>("/api/v1/auth/me", {
    signal,
  });
}

export function githubLoginUrl(redirectTo = "/tasks") {
  return apiUrl(
    `/api/v1/auth/github/login?redirect_to=${encodeURIComponent(redirectTo)}`,
  );
}

export function logout() {
  return apiRequest<{ logged_out: boolean }>("/api/v1/auth/logout", {
    method: "POST",
  });
}

export function getGitHubSetupUrl() {
  return apiRequest<{ url: string }>(
    "/api/v1/auth/github/installations/setup",
  );
}

export function listInstallations(signal?: AbortSignal) {
  return apiRequest<GitHubInstallationListResponse>(
    "/api/v1/github/installations",
    { signal },
  );
}
