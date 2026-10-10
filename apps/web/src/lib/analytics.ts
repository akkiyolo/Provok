"use client";

import { getAccessToken } from "./api";

function anonId(): string {
  try {
    let id = localStorage.getItem("provok:anon");
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem("provok:anon", id);
    }
    return id;
  } catch {
    return "unknown";
  }
}

/** Fire-and-forget product analytics (first-party, stored in our own DB). */
export function track(name: string, props: Record<string, string | number | boolean> = {}, debateId?: string) {
  if (typeof window === "undefined") return;
  const body = JSON.stringify({ name, props, anon_id: anonId(), debate_id: debateId ?? null });
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getAccessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  void fetch("/api/v1/events", { method: "POST", body, headers, keepalive: true }).catch(() => undefined);
}
