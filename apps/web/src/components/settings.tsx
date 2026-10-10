"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useToast } from "@/components/toast";
import { Avatar, Button, Field, PageTitle, Sheet, Spinner } from "@/components/ui";
import { api, errorMessage, get, patch, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Me, TokenResponse } from "@/lib/types";

function Section({ title, children, danger }: { title: string; children: React.ReactNode; danger?: boolean }) {
  return (
    <section className={`rounded-3xl border p-5 sm:p-6 ${danger ? "border-danger/40" : "border-line bg-surface"}`}>
      <h2 className="font-display mb-4 text-xl font-bold">{title}</h2>
      {children}
    </section>
  );
}

export function SettingsView() {
  const { user, status, requireAuth, setUser, acceptTokens, logout } = useAuth();
  const toast = useToast();
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({ display_name: "", username: "", bio: "" });
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [del, setDel] = useState({ password: "", confirm: "" });

  useEffect(() => {
    if (status === "anon") requireAuth("Sign in to manage your account.");
  }, [status, requireAuth]);
  useEffect(() => {
    if (user) setTimeout(() => setForm({ display_name: user.display_name, username: user.username, bio: user.bio ?? "" }), 0);
  }, [user]);

  if (!user) return <div className="grid min-h-[50dvh] place-items-center"><Spinner className="size-6" /></div>;

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 pb-20 pt-8 sm:px-6">
      <PageTitle eyebrow="SETTINGS" title="Your corner." />

      <Section title="Profile">
        <div className="mb-5 flex items-center gap-4">
          <Avatar user={user} size={72} />
          <div className="flex flex-col gap-2">
            <Button size="sm" variant="outline" loading={busy === "avatar"} onClick={() => fileRef.current?.click()}>Change photo</Button>
            <span className="text-[12px] text-faint">JPEG, PNG, WebP or GIF · up to 5 MB</span>
          </div>
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              const fd = new FormData();
              fd.append("file", f);
              void run("avatar", async () => {
                const r = await api<{ avatar_url: string }>("/me/avatar", { method: "POST", form: fd });
                setUser({ ...user, avatar_url: r.avatar_url });
                toast("Looking sharp.", "success");
              });
              e.target.value = "";
            }} />
        </div>
        <form className="flex flex-col gap-3" onSubmit={(e) => {
          e.preventDefault();
          void run("profile", async () => {
            setUser(await patch<Me>("/me", form));
            toast("Profile saved.", "success");
          });
        }}>
          <Field label="Display name" value={form.display_name} maxLength={60} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          <Field label="Username" value={form.username} maxLength={20} hint="Changing it changes your profile link."
            onChange={(e) => setForm({ ...form, username: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") })} />
          <div className="flex flex-col gap-1.5">
            <label htmlFor="bio" className="text-[13px] font-medium text-dim">Bio</label>
            <textarea id="bio" value={form.bio} maxLength={280} rows={3} onChange={(e) => setForm({ ...form, bio: e.target.value })}
              className="rounded-xl border border-line bg-surface px-3.5 py-2.5 text-[15px] outline-none focus:border-text/60" />
          </div>
          <Button type="submit" loading={busy === "profile"} className="w-fit">Save profile</Button>
        </form>
      </Section>

      <Section title={user.has_password ? "Password" : "Set a password"}>
        <form className="flex flex-col gap-3" onSubmit={(e) => {
          e.preventDefault();
          void run("password", async () => {
            const t = await post<TokenResponse>("/auth/change-password", pw);
            acceptTokens(t);
            setPw({ current_password: "", new_password: "" });
            toast("Password updated. Other devices were signed out.", "success");
          });
        }}>
          {user.has_password && <Field label="Current password" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />}
          <Field label="New password" type="password" autoComplete="new-password" value={pw.new_password} hint="At least 8 characters." onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
          <Button type="submit" loading={busy === "password"} disabled={pw.new_password.length < 8} className="w-fit">Update password</Button>
        </form>
      </Section>

      <Section title="Sessions & data">
        <div className="flex flex-wrap gap-3">
          <Button variant="outline" loading={busy === "logoutall"} onClick={() => run("logoutall", async () => {
            await post("/auth/logout-all");
            await logout();
            router.push("/login");
          })}>Sign out everywhere</Button>
          <Button variant="outline" loading={busy === "export"} onClick={() => run("export", async () => {
            const data = await get<unknown>("/me/export");
            const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
            const a = Object.assign(document.createElement("a"), { href: url, download: `provok-${user.username}.json` });
            a.click();
            URL.revokeObjectURL(url);
          })}>Download my data</Button>
        </div>
      </Section>

      <Section title="Delete account" danger>
        <p className="mb-4 text-sm text-dim">Your profile, sign-ins, follows and notifications are erased. Your past debate turns stay (debates need both sides) but are shown as &ldquo;Deleted user&rdquo;. Unused credits are forfeited.</p>
        <Button variant="danger" onClick={() => setDeleteOpen(true)}>Delete my account</Button>
      </Section>

      <Sheet open={deleteOpen} onClose={() => setDeleteOpen(false)} title="This is permanent.">
        <div className="flex flex-col gap-3">
          {user.has_password && <Field label="Password" type="password" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} />}
          <Field label='Type DELETE to confirm' value={del.confirm} onChange={(e) => setDel({ ...del, confirm: e.target.value })} />
          <Button variant="danger" loading={busy === "delete"} disabled={del.confirm !== "DELETE"} onClick={() => run("delete", async () => {
            await post("/me/delete", del);
            await logout().catch(() => undefined);
            toast("Your account has been deleted.", "info");
            router.push("/");
          })}>Delete forever</Button>
        </div>
      </Sheet>
    </div>
  );
}
