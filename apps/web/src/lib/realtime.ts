"use client";

// Arena realtime channel. The server is authoritative: socket events are hints that
// trigger a REST refetch of the debate, plus ephemeral streams (typing, reactions,
// captions, viewer counts). Missing an event is never fatal.

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

import { getAccessToken, post } from "./api";
import { useAuth } from "./auth";
import type { Position } from "./types";

export interface Reaction {
  id: number;
  emoji: string;
  position: Position | null;
}

interface ChannelState {
  connected: boolean;
  viewers: number | null;
  typing: Partial<Record<Position, string>>;
  captions: Partial<Record<Position, string>>;
  speakers: Position[] | null;
}

export function wsBase(): string {
  const env = process.env.NEXT_PUBLIC_WS_URL;
  if (env) return env.replace(/\/$/, "");
  if (typeof window === "undefined") return "";
  const { protocol, hostname } = window.location;
  return hostname === "localhost" || hostname === "127.0.0.1"
    ? "ws://localhost:8000"
    : `${protocol === "https:" ? "wss" : "ws"}://${window.location.host}`;
}

export async function wsTicket(): Promise<string | null> {
  if (!getAccessToken()) return null;
  try {
    return (await post<{ ticket: string }>("/auth/ws-ticket")).ticket;
  } catch {
    return null;
  }
}

export function useDebateChannel(debateId: string, onReaction?: (r: Reaction) => void) {
  const qc = useQueryClient();
  const { status } = useAuth();
  const [state, setState] = useState<ChannelState>({
    connected: false, viewers: null, typing: {}, captions: {}, speakers: null,
  });
  const wsRef = useRef<WebSocket | null>(null);
  const reactionId = useRef(0);
  const emitReaction = useEffectEvent((r: Reaction) => onReaction?.(r));

  useEffect(() => {
    if (status === "loading") return;
    let closed = false;
    let attempt = 0;
    let pingTimer: ReturnType<typeof setInterval> | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let invalidateTimer: ReturnType<typeof setTimeout> | null = null;

    const refetch = () => {
      if (invalidateTimer) clearTimeout(invalidateTimer);
      invalidateTimer = setTimeout(() => {
        void qc.invalidateQueries({ queryKey: ["debate", debateId] });
      }, 120);
    };

    const connect = async () => {
      const ticket = await wsTicket();
      if (closed) return;
      const url = `${wsBase()}/ws/debates/${debateId}${ticket ? `?ticket=${encodeURIComponent(ticket)}` : ""}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attempt = 0;
        setState((s) => ({ ...s, connected: true }));
        refetch(); // resync after (re)connect
        pingTimer = setInterval(() => ws.readyState === 1 && ws.send(JSON.stringify({ type: "ping" })), 25_000);
      };
      ws.onmessage = (ev) => {
        let msg: { type: string; data: Record<string, unknown> };
        try {
          msg = JSON.parse(ev.data as string);
        } catch {
          return;
        }
        const d = msg.data ?? {};
        switch (msg.type) {
          case "state_changed":
          case "ledger_updated":
          case "vote_closed":
            refetch();
            if (msg.type === "state_changed") setState((s) => ({ ...s, typing: {} }));
            break;
          case "verdict_ready":
            refetch();
            void qc.invalidateQueries({ queryKey: ["verdict", debateId] });
            break;
          case "viewers":
            setState((s) => ({ ...s, viewers: Number(d.count ?? 0) }));
            break;
          case "typing_start":
            setState((s) => ({ ...s, typing: { ...s.typing, [d.position as Position]: "" } }));
            break;
          case "typing":
            setState((s) => {
              const p = d.position as Position;
              return { ...s, typing: { ...s.typing, [p]: (s.typing[p] ?? "") + String(d.delta ?? "") } };
            });
            break;
          case "typing_end":
            break; // keep text until the state refetch lands, to avoid a flash
          case "caption":
            setState((s) => ({ ...s, captions: { ...s.captions, [d.position as Position]: String(d.text ?? "") } }));
            break;
          case "video_turn":
            setState((s) => ({ ...s, speakers: (d.speakers as Position[]) ?? null }));
            break;
          case "reaction":
            reactionId.current += 1;
            emitReaction({ id: reactionId.current, emoji: String(d.emoji), position: (d.position as Position) ?? null });
            break;
          case "notification":
            void qc.invalidateQueries({ queryKey: ["notifications"] });
            break;
        }
      };
      ws.onclose = () => {
        if (pingTimer) clearInterval(pingTimer);
        setState((s) => ({ ...s, connected: false }));
        if (closed) return;
        attempt += 1;
        const delay = Math.min(30_000, 500 * 2 ** attempt) * (0.7 + Math.random() * 0.6);
        retryTimer = setTimeout(() => void connect(), delay);
      };
      ws.onerror = () => ws.close();
    };

    void connect();
    const onVisible = () => document.visibilityState === "visible" && refetch();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      closed = true;
      document.removeEventListener("visibilitychange", onVisible);
      if (pingTimer) clearInterval(pingTimer);
      if (retryTimer) clearTimeout(retryTimer);
      if (invalidateTimer) clearTimeout(invalidateTimer);
      wsRef.current?.close();
    };
  }, [debateId, qc, status]);

  const sendReaction = useCallback((emoji: string, position: Position | null) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "reaction", emoji, position }));
  }, []);

  return { ...state, sendReaction };
}
