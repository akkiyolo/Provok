// Server-only helpers for metadata and OG images (public, unauthenticated reads).
import "server-only";

import type { DebateView } from "./types";

const API = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

export async function fetchDebatePublic(id: string): Promise<DebateView | null> {
  if (!/^[0-9a-f-]{36}$/i.test(id)) return null;
  try {
    const res = await fetch(`${API}/api/v1/debates/${id}`, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(4000) });
    if (!res.ok) return null;
    return (await res.json()) as DebateView;
  } catch {
    return null;
  }
}

export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
