"use client";

import { useSyncExternalStore } from "react";

import type { PostView } from "@/lib/types";

/** The global compose sheet: opened from the + button, Reply and Quote anywhere in the app. */
export interface ComposeState {
  open: boolean;
  replyTo?: PostView;
  quote?: PostView;
}

let state: ComposeState = { open: false };
const listeners = new Set<() => void>();
const CLOSED: ComposeState = { open: false };

function set(next: ComposeState) {
  state = next;
  listeners.forEach((l) => l());
}

export const openCompose = (opts: Omit<ComposeState, "open"> = {}) => set({ open: true, ...opts });
export const closeCompose = () => set(CLOSED);

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export const useCompose = () => useSyncExternalStore(subscribe, () => state, () => CLOSED);
