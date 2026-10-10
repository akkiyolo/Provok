// Browser + server fetch client for the Provok API.
//
// In the browser every call goes to same-origin `/api/v1/*` (rewritten by Next to the
// FastAPI service), so the refresh-token cookie is first-party and never exposed to JS.
// The short-lived access token lives only in memory.

import type { TokenResponse } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const isServer = typeof window === "undefined";
const SERVER_BASE = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

function base(): string {
  return isServer ? `${SERVER_BASE}/api/v1` : "/api/v1";
}

let accessToken: string | null = null;
let refreshInFlight: Promise<TokenResponse | null> | null = null;
type TokenListener = (t: TokenResponse | null) => void;
const listeners = new Set<TokenListener>();

export function setAccessToken(token: string | null) {
  accessToken = token;
}
export function getAccessToken() {
  return accessToken;
}
export function onTokenChange(fn: TokenListener) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Exchange the httpOnly refresh cookie for a new access token. Single-flight across callers. */
export function refreshSession(): Promise<TokenResponse | null> {
  if (isServer) return Promise.resolve(null);
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${base()}/auth/refresh`, { method: "POST", credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok || r.status === 204) return null; // 204: signed out
        return (await r.json()) as TokenResponse;
      })
      .catch(() => null)
      .then((t) => {
        accessToken = t?.access_token ?? null;
        listeners.forEach((l) => l(t));
        return t;
      })
      .finally(() => {
        refreshInFlight = null;
      });
  }
  return refreshInFlight;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData;
  signal?: AbortSignal;
  /** Server-side only: Next fetch cache hints. */
  next?: { revalidate?: number | false; tags?: string[] };
}

async function parseError(res: Response): Promise<ApiError> {
  let payload: { error?: { code?: string; message?: string; details?: Record<string, unknown> } } = {};
  try {
    payload = await res.json();
  } catch {
    /* non-JSON error (proxy, gateway) */
  }
  const err = payload.error ?? {};
  const fallback =
    res.status === 429
      ? "You're going a little fast. Try again in a moment."
      : res.status >= 500
        ? "Something went wrong on our side. Please try again."
        : "Request failed.";
  return new ApiError(err.message ?? fallback, res.status, err.code ?? `http_${res.status}`, err.details ?? {});
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const doFetch = () => {
    const headers: Record<string, string> = {};
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
    let body: BodyInit | undefined;
    if (opts.form) body = opts.form;
    else if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.body);
    }
    return fetch(`${base()}${path}`, {
      method: opts.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: opts.signal,
      credentials: "same-origin",
      ...(isServer && opts.next ? { next: opts.next } : {}),
    });
  };

  let res: Response;
  try {
    res = await doFetch();
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError("You appear to be offline. Check your connection.", 0, "network_error");
  }
  if (res.status === 401 && !isServer && accessToken && !path.startsWith("/auth/")) {
    const refreshed = await refreshSession();
    if (refreshed) res = await doFetch();
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const get = <T,>(path: string, opts?: RequestOptions) => api<T>(path, { ...opts, method: "GET" });
export const post = <T,>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body ?? {} });
export const patch = <T,>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body });
export const put = <T,>(path: string, body: unknown) => api<T>(path, { method: "PUT", body });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}
