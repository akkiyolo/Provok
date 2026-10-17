"use client";

import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { api, onTokenChange, post, refreshSession, setAccessToken } from "./api";
import { forgetPushDevice, syncPush } from "./push";
import type { Me, TokenResponse } from "./types";

type Status = "loading" | "authed" | "anon";

interface AuthContextValue {
  user: Me | null;
  status: Status;
  login: (identifier: string, password: string) => Promise<Me>;
  register: (input: { email: string; password: string; username: string; display_name?: string; next?: string }) => Promise<Me>;
  logout: () => Promise<void>;
  acceptTokens: (t: TokenResponse) => void;
  setUser: (u: Me) => void;
  reloadUser: () => Promise<void>;
  /** Open the sign-in sheet when an action needs an account. Returns true if already signed in. */
  requireAuth: (reason?: string) => boolean;
  gate: { open: boolean; reason: string | null; close: () => void };
}

type Methods = Omit<AuthContextValue, "user" | "status">;
const AuthContext = createContext<Methods | null>(null);

// Auth state lives in a tiny external store read through useSyncExternalStore. During hydration React
// always uses the server snapshot ("loading"), so a Suspense boundary that hydrates *after* the session
// check has finished still matches the server HTML (no hydration mismatch, no full client re-render).
interface AuthSnap { user: Me | null; status: Status }
const SERVER_SNAP: AuthSnap = { user: null, status: "loading" };
let snap: AuthSnap = SERVER_SNAP;
const subscribers = new Set<() => void>();
function setSnap(next: Partial<AuthSnap>) {
  snap = { ...snap, ...next };
  subscribers.forEach((fn) => fn());
}
function subscribe(fn: () => void) {
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
  };
}
const useAuthSnap = () => useSyncExternalStore(subscribe, () => snap, () => SERVER_SNAP);
const setUserState = (u: Me | null) => setSnap({ user: u });
const setStatus = (st: Status) => setSnap({ status: st });

// Once per signed-in account per page load, re-register this device for push (see syncPush).
let pushSyncedFor: string | null = null;
function syncPushOnce(userId: string) {
  if (pushSyncedFor === userId) return;
  pushSyncedFor = userId;
  void syncPush().catch(() => undefined);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [gateOpen, setGateOpen] = useState(false);
  const [gateReason, setGateReason] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const qc = useQueryClient();

  const schedule = useCallback((expiresIn: number) => {
    if (timer.current) clearTimeout(timer.current);
    // Refresh a minute before expiry; refreshSession() is single-flight across tabs' requests.
    timer.current = setTimeout(() => void refreshSession(), Math.max(10, expiresIn - 60) * 1000);
  }, []);

  const acceptTokens = useCallback(
    (t: TokenResponse) => {
      setAccessToken(t.access_token);
      setUserState(t.user);
      setStatus("authed");
      schedule(t.expires_in);
      syncPushOnce(t.user.id);
    },
    [schedule],
  );

  useEffect(() => {
    const off = onTokenChange((t) => {
      if (t) {
        setUserState(t.user);
        setStatus("authed");
        schedule(t.expires_in);
        syncPushOnce(t.user.id);
      } else {
        setUserState(null);
        setStatus("anon");
      }
    });
    void refreshSession().then((t) => {
      if (!t) setStatus("anon");
    });
    // Another tab signed in/out: re-sync.
    const onStorage = (e: StorageEvent) => {
      if (e.key === "provok:auth") void refreshSession();
    };
    window.addEventListener("storage", onStorage);
    return () => {
      off();
      window.removeEventListener("storage", onStorage);
      if (timer.current) clearTimeout(timer.current);
    };
  }, [schedule]);

  const broadcast = () => {
    try {
      localStorage.setItem("provok:auth", String(Date.now()));
    } catch {
      /* private mode */
    }
  };

  const login = useCallback(
    async (identifier: string, password: string) => {
      const t = await post<TokenResponse>("/auth/login", { identifier, password });
      acceptTokens(t);
      broadcast();
      void qc.invalidateQueries();
      return t.user;
    },
    [acceptTokens, qc],
  );

  const register = useCallback(
    async (input: { email: string; password: string; username: string; display_name?: string; next?: string }) => {
      const t = await post<TokenResponse>("/auth/register", input);
      acceptTokens(t);
      broadcast();
      return t.user;
    },
    [acceptTokens],
  );

  const logout = useCallback(async () => {
    try {
      await forgetPushDevice().catch(() => undefined);
      pushSyncedFor = null;
      await api("/auth/logout", { method: "POST" });
    } finally {
      setAccessToken(null);
      setUserState(null);
      setStatus("anon");
      if (timer.current) clearTimeout(timer.current);
      broadcast();
      qc.clear();
    }
  }, [qc]);

  const reloadUser = useCallback(async () => {
    const me = await api<Me>("/auth/me");
    setUserState(me);
  }, []);

  const requireAuth = useCallback(
    (reason?: string) => {
      if (snap.status === "authed") return true;
      setGateReason(reason ?? null);
      setGateOpen(true);
      return false;
    },
    [],
  );

  const value = useMemo<Methods>(
    () => ({
      login,
      register,
      logout,
      acceptTokens,
      setUser: setUserState,
      reloadUser,
      requireAuth,
      gate: { open: gateOpen, reason: gateReason, close: () => setGateOpen(false) },
    }),
    [login, register, logout, acceptTokens, reloadUser, requireAuth, gateOpen, gateReason],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  const { user, status } = useAuthSnap();
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return { ...ctx, user, status };
}
