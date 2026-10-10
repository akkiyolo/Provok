"use client";

import Link from "next/link";
import { useState } from "react";

import { Button, Field, Sheet } from "@/components/ui";
import { ApiError, errorMessage } from "@/lib/api";
import { track } from "@/lib/analytics";
import { useAuth } from "@/lib/auth";
import { useMeta } from "@/lib/meta";

export function GoogleButton({ next }: { next?: string }) {
  const meta = useMeta();
  if (meta && !meta.features.google_login) return null;
  const href = `/api/v1/auth/google/start${next ? `?next=${encodeURIComponent(next)}` : ""}`;
  return (
    <a href={href} className="flex h-12 items-center justify-center gap-3 rounded-full border border-line-strong bg-surface font-semibold transition hover:bg-surface-2">
      <svg viewBox="0 0 48 48" className="size-5" aria-hidden>
        <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.3-.1-2.4-.4-3.5z" />
        <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
        <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
        <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.3-.1-2.4-.4-3.5z" />
      </svg>
      Continue with Google
    </a>
  );
}

function Divider() {
  return (
    <div className="my-1 flex items-center gap-3 text-[12px] text-faint">
      <span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" />
    </div>
  );
}

export function LoginForm({ onDone, next }: { onDone?: () => void; next?: string }) {
  const { login } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(identifier.trim(), password);
      onDone?.();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <GoogleButton next={next} />
      <Divider />
      <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
        <Field label="Email or username" autoComplete="username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} required />
        <Field label="Password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <Button type="submit" size="lg" loading={busy} disabled={!identifier || !password}>Sign in</Button>
        <Link href="/forgot-password" className="text-center text-sm text-dim underline-offset-4 hover:underline">Forgot your password?</Link>
      </form>
    </div>
  );
}

export function SignupForm({ onDone, next }: { onDone?: () => void; next?: string }) {
  const { register } = useAuth();
  const [form, setForm] = useState({ email: "", username: "", password: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: k === "username" ? e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") : e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErrors({});
    track("signup_started", { method: "password" });
    try {
      await register({ ...form, display_name: form.username });
      onDone?.();
    } catch (err) {
      if (err instanceof ApiError) {
        const field = err.code.includes("username") ? "username" : err.code.includes("email") ? "email" :
          err.code.includes("password") ? "password" : "form";
        setErrors({ [field]: err.message });
      } else setErrors({ form: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <GoogleButton next={next} />
      <Divider />
      <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
        <Field label="Email" type="email" autoComplete="email" value={form.email} onChange={set("email")} error={errors.email} required />
        <Field label="Username" autoComplete="username" value={form.username} onChange={set("username")} error={errors.username}
          hint="3–20 characters. This is how the arena will know you." maxLength={20} required />
        <Field label="Password" type="password" autoComplete="new-password" value={form.password} onChange={set("password")}
          error={errors.password} hint="At least 8 characters." required />
        {errors.form && <p role="alert" className="text-sm text-danger">{errors.form}</p>}
        <Button type="submit" size="lg" variant="for" loading={busy} disabled={!form.email || !form.username || form.password.length < 8}>
          Create account
        </Button>
        <p className="text-center text-[12px] leading-relaxed text-faint">
          By joining you agree to our <Link href="/terms" className="underline">Terms</Link> and{" "}
          <Link href="/privacy" className="underline">Privacy Policy</Link>.
        </p>
      </form>
    </div>
  );
}

/** The sign-in sheet that appears at the moment an action needs an account (vote, debate, report). */
export function AuthGateSheet() {
  const { gate } = useAuth();
  const [mode, setMode] = useState<"signup" | "login">("signup");
  const next = typeof window !== "undefined" ? window.location.pathname : "/";
  return (
    <Sheet open={gate.open} onClose={gate.close} title={mode === "signup" ? "Join the arena" : "Welcome back"}>
      {gate.reason && <p className="-mt-2 mb-4 text-sm text-dim">{gate.reason}</p>}
      {mode === "signup" ? <SignupForm onDone={gate.close} next={next} /> : <LoginForm onDone={gate.close} next={next} />}
      <p className="mt-5 text-center text-sm text-dim">
        {mode === "signup" ? "Already have an account? " : "New to Provok? "}
        <button className="font-semibold text-text underline underline-offset-4" onClick={() => setMode(mode === "signup" ? "login" : "signup")}>
          {mode === "signup" ? "Sign in" : "Create one"}
        </button>
      </p>
    </Sheet>
  );
}
