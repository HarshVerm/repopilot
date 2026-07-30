// Module purpose: Provide reusable errors frontend utilities.

import { isApiError } from "./api/client";

/** Purpose: Handle error title for this frontend module. */
export function errorTitle(error: unknown) {
  if (!isApiError(error)) {
    return "Something went wrong";
  }

  if (error.status === 0) return "Backend unavailable";
  if (error.status === 400 || error.status === 422) return "Validation failed";
  if (error.status === 401) return "Authentication required";
  if (error.status === 403) return "Permission denied";
  if (error.status === 404) return "Not found";
  if (error.status === 409) return "Stale state conflict";
  if (error.status === 429) return "Rate limited";
  if (error.status >= 500) return "Backend failure";

  return "Request failed";
}

/** Purpose: Handle error message for this frontend module. */
export function errorMessage(error: unknown) {
  if (isApiError(error)) {
    if (error.status === 403) {
      return error.message || "You do not have permission to perform this action.";
    }

    if (error.status === 409) {
      return error.message || "The task changed on the server. Refreshing the latest state.";
    }

    if (error.status === 429) {
      return error.message || "RepoPilot is rate-limited. Wait before retrying.";
    }

    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred.";
}
