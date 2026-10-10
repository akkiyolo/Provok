"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { LoginForm, SignupForm } from "@/components/auth-forms";
import { useToast } from "@/components/toast";
import { Button, Field, Spinner } from "@/components/ui";
import { errorMessage, post, refreshSession } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Me } from "@/lib/types";

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

const GOOGLE_ERRORS: Record<string, string> = {
  google: "Google sign-in didn't complete. Please try again.",
  account_banned: "This account has been suspended.",
  signups_closed: "Sign-ups are paused right now. Please try again soon.",
};

function Shell({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="stage-duel grain flex min-h-[calc(100dvh-64px)] items-start justify-center px-4 py-10 sm:items-center">
      <div className="w-full max-w-md rounded-[2rem] border border-line bg-surface/80 p-6 backdrop-blur sm:p-8">
        <h1 className="font-display text-[2.1rem] font-extrabold leading-none">{title}</h1>
        {sub && <p className="mt-2 text-sm text-dim">{sub}</p>}
        <div className="mt-6">{children}</div>
      </div>
    </div>
  );
}

export function AuthPage({ mode }: { mode: "login" | "signup" }) {
  const params = useSearchParams();
  const router = useRouter();
  const { status } = useAuth();
  const next = safeNext(params.get("next"));
  const err = params.get("error");
  useEffect(() => {
    if (status === "authed") router.replace(next);
  }, [status, next, router]);
  return (
    <Shell title={mode === "login" ? "Welcome back." : "Join the arena."}
      sub={mode === "login" ? "Sign in to debate, vote and climb the leaderboard." : "Free account. Your first 3 AI debates are on us."}>
      {err && <p role="alert" className="mb-4 rounded-xl border border-danger/40 bg-danger/10 px-3 py-2 text-sm">{GOOGLE_ERRORS[err] ?? GOOGLE_ERRORS.google}</p>}
      {mode === "login" ? <LoginForm next={next} onDone={() => router.replace(next)} /> : <SignupForm next={next} onDone={() => router.replace(next)} />}
      <p className="mt-6 text-center text-sm text-dim">
        {mode === "login" ? "New here? " : "Already have an account? "}
        <Link href={`/${mode === "login" ? "signup" : "login"}${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-semibold text-text underline underline-offset-4">
          {mode === "login" ? "Create an account" : "Sign in"}
        </Link>
      </p>
    </Shell>
  );
}

export function OAuthCallback() {
  const params = useSearchParams();
  const router = useRouter();
  const next = safeNext(params.get("next"));
  useEffect(() => {
    void refreshSession().then((t) => router.replace(t ? next : "/login?error=google"));
  }, [next, router]);
  return <div className="grid min-h-[60dvh] place-items-center"><Spinner className="size-8" /></div>;
}

export function VerifyEmail() {
  const params = useSearchParams();
  const token = params.get("token");
  const { acceptTokens, setUser, status } = useAuth();
  const [state, setState] = useState<"working" | "ok" | "error">(token ? "working" : "error");
  const [message, setMessage] = useState(token ? "" : "This link is missing its token.");
  const ran = useRef(false);
  useEffect(() => {
    if (!token || ran.current) return;
    ran.current = true;
    post<{ ok: boolean; user: Me }>("/auth/verify-email", { token })
      .then((r) => {
        setState("ok");
        if (status === "authed") setUser(r.user);
      })
      .catch((e) => {
        setState("error");
        setMessage(errorMessage(e));
      });
  }, [token, status, setUser, acceptTokens]);
  return (
    <Shell title={state === "ok" ? "You're verified." : state === "error" ? "Link didn't work." : "Confirming…"}
      sub={state === "ok" ? "You can now debate, vote and buy credits." : message}>
      {state === "working" ? <Spinner className="size-6" /> : (
        <Button href={state === "ok" ? "/" : "/settings"} variant={state === "ok" ? "for" : "outline"} className="w-full">
          {state === "ok" ? "Enter the arena →" : "Request a new link"}
        </Button>
      )}
    </Shell>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await post("/auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Shell title="Forgot it?" sub={sent ? "If an account exists for that email, a reset link is on its way. It expires in 30 minutes." : "We'll email you a link to choose a new password."}>
      {!sent ? (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <Field label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <Button type="submit" size="lg" loading={busy} disabled={!email}>Send reset link</Button>
        </form>
      ) : <Button href="/login" variant="outline" className="w-full">Back to sign in</Button>}
    </Shell>
  );
}

export function ResetPassword() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await post("/auth/reset-password", { token, password });
      toast("Password updated. Sign in with your new password.", "success");
      router.replace("/login");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Shell title="New password." sub="You'll be signed out of every other device.">
      <form onSubmit={submit} className="flex flex-col gap-3">
        <Field label="New password" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)}
          error={error} hint="At least 8 characters." required />
        <Button type="submit" size="lg" loading={busy} disabled={password.length < 8 || !token}>Update password</Button>
      </form>
    </Shell>
  );
}

/** Slim, dismissible banner nudging unverified users to confirm their email. */
export function VerifyBanner() {
  const { user } = useAuth();
  const toast = useToast();
  const [hidden, setHidden] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!user || user.email_verified || hidden) return null;
  const resend = async () => {
    setBusy(true);
    try {
      await post("/auth/resend-verification");
      toast(`Sent! Check ${user.email}.`, "success");
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div role="status" className="border-b border-win/30 bg-win/10">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-2 text-[13px] sm:px-6">
        <span>Confirm your email to debate and vote — we sent a link to <b>{user.email}</b>.</span>
        <button onClick={resend} disabled={busy} className="font-semibold underline underline-offset-4">{busy ? "Sending…" : "Resend"}</button>
        <button onClick={() => setHidden(true)} className="ml-auto text-faint" aria-label="Dismiss">✕</button>
      </div>
    </div>
  );
}
