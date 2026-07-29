export interface ApiErrorShape {
  status: number;
  message: string;
  code?: string;
  requestId?: string;
  details?: unknown;
}

export class ApiRequestError extends Error implements ApiErrorShape {
  status: number;
  code?: string;
  requestId?: string;
  details?: unknown;

  constructor(error: ApiErrorShape) {
    super(error.message);
    this.name = "ApiRequestError";
    this.status = error.status;
    this.code = error.code;
    this.requestId = error.requestId;
    this.details = error.details;
  }
}

export interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  requestId?: string;
}

const explicitBaseUrl = process.env.NEXT_PUBLIC_REPOPILOT_API_URL?.replace(/\/$/, "");
const csrfCookieName =
  process.env.NEXT_PUBLIC_REPOPILOT_CSRF_COOKIE_NAME || "repopilot_csrf";

export function apiUrl(path: string) {
  return buildUrl(path);
}

function makeRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }

  return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function buildUrl(path: string) {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return explicitBaseUrl ? `${explicitBaseUrl}${normalizedPath}` : normalizedPath;
}

function isJsonResponse(response: Response) {
  return response.headers.get("content-type")?.includes("application/json") ?? false;
}

async function parseResponse(response: Response) {
  if (response.status === 204) {
    return null;
  }

  if (isJsonResponse(response)) {
    return response.json();
  }

  const text = await response.text();
  return text.length > 0 ? text : null;
}

function messageFromDetails(details: unknown, fallback: string) {
  if (typeof details === "string") {
    return details;
  }

  if (
    details &&
    typeof details === "object" &&
    "detail" in details &&
    typeof (details as { detail?: unknown }).detail === "string"
  ) {
    return (details as { detail: string }).detail;
  }
  if (
    details &&
    typeof details === "object" &&
    "detail" in details &&
    typeof (details as { detail?: unknown }).detail === "object"
  ) {
    const detail = (details as { detail: { error?: { message?: unknown } } }).detail;
    if (detail?.error && typeof detail.error.message === "string") {
      return detail.error.message;
    }
  }

  return fallback;
}

export async function apiRequest<T>(
  path: string,
  options: ApiRequestOptions = {},
): Promise<T> {
  const { body, requestId: providedRequestId, ...requestOptions } = options;
  const requestId = providedRequestId ?? makeRequestId();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Request-ID", requestId);

  const init: RequestInit = {
    ...requestOptions,
    credentials: "include",
    headers,
  };

  const method = (requestOptions.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = readCookie(csrfCookieName);
    if (csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }

  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path), init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }

    throw new ApiRequestError({
      status: 0,
      message:
        typeof navigator !== "undefined" && !navigator.onLine
          ? "Browser is offline."
          : "RepoPilot backend is unreachable.",
      code: "network_error",
      requestId,
      details: error,
    });
  }

  const parsed = await parseResponse(response);
  if (!response.ok) {
    throw new ApiRequestError({
      status: response.status,
      message: messageFromDetails(parsed, response.statusText || "Request failed"),
      code: response.headers.get("X-Error-Code") ?? undefined,
      requestId: response.headers.get("X-Request-ID") ?? requestId,
      details: parsed,
    });
  }

  return parsed as T;
}

function readCookie(name: string) {
  if (typeof document === "undefined") {
    return null;
  }
  const prefix = `${encodeURIComponent(name)}=`;
  const value = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(prefix));
  return value ? decodeURIComponent(value.slice(prefix.length)) : null;
}

export function isApiError(error: unknown): error is ApiRequestError {
  return error instanceof ApiRequestError;
}
