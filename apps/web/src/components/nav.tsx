"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { useUnreadMessages } from "@/components/messages";
import { openCompose } from "@/components/posts/compose-store";
import { Avatar, Button, Sheet } from "@/components/ui";
import { get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cx } from "@/lib/format";
import type { NotificationItem } from "@/lib/types";

export function Logo({ className }: { className?: string }) {
  return (
    <Link href="/" aria-label="Provok home" className={cx("font-display text-[22px] font-extrabold leading-none tracking-[-0.06em]", className)}>
      PROV<span className="text-for">O</span>K
    </Link>
  );
}

function useUnread() {
  const { status } = useAuth();
  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => get<{ items: NotificationItem[]; unread: number }>("/notifications?limit=20"),
    enabled: status === "authed",
    refetchInterval: 60_000,
  });
  return data?.unread ?? 0;
}

export function ThemeToggle() {
  const toggle = () => {
    const el = document.documentElement;
    const next = el.dataset.theme === "light" ? "dark" : "light";
    el.dataset.theme = next;
    try {
      localStorage.setItem("provok:theme", next);
    } catch {
      /* ignore */
    }
  };
  return (
    <button onClick={toggle} aria-label="Toggle light and dark theme" className="grid size-9 place-items-center rounded-full text-dim transition hover:bg-surface-2 hover:text-text">
      <svg viewBox="0 0 20 20" className="size-[18px]" fill="currentColor" aria-hidden>
        <path d="M10 2a8 8 0 1 0 0 16V2z" />
        <path d="M10 2a8 8 0 0 1 0 16" fill="none" stroke="currentColor" strokeWidth="1.6" />
      </svg>
    </button>
  );
}

function Bell() {
  const unread = useUnread();
  return (
    <Link href="/notifications" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`} className="relative grid size-9 place-items-center rounded-full text-dim transition hover:bg-surface-2 hover:text-text">
      <svg viewBox="0 0 20 20" className="size-[18px]" fill="currentColor" aria-hidden>
        <path d="M10 2a5 5 0 0 0-5 5v3.2L3.6 13a.8.8 0 0 0 .7 1.2h11.4a.8.8 0 0 0 .7-1.2L15 10.2V7a5 5 0 0 0-5-5zm-2 13.5a2 2 0 0 0 4 0z" />
      </svg>
      {unread > 0 && (
        <span className="absolute -right-0.5 -top-0.5 grid min-w-[18px] place-items-center rounded-full bg-live px-1 font-mono text-[10px] font-bold text-white">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </Link>
  );
}

function MessagesLink() {
  const unread = useUnreadMessages();
  return (
    <Link href="/messages" aria-label={`Messages${unread ? `, ${unread} unread` : ""}`} className="relative hidden size-9 place-items-center rounded-full text-dim transition hover:bg-surface-2 hover:text-text sm:grid">
      <svg viewBox="0 0 20 20" className="size-[18px]" fill="currentColor" aria-hidden><path d="M3 4.5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zm.6 1.6 6.4 4.6 6.4-4.6z" /></svg>
      {unread > 0 && (
        <span className="absolute -right-0.5 -top-0.5 grid min-w-[18px] place-items-center rounded-full bg-live px-1 font-mono text-[10px] font-bold text-white">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </Link>
  );
}

function AccountMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const router = useRouter();
  useEffect(() => {
    const onDoc = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  if (!user) return null;
  const item = "block rounded-xl px-3 py-2 text-sm hover:bg-surface-2";
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} className="flex items-center gap-2 rounded-full p-0.5 pr-2 hover:bg-surface-2">
        <Avatar user={user} size={32} />
        <span className="hidden font-mono text-[12px] text-dim md:inline" title="Credits">{user.credits} cr</span>
      </button>
      {open && (
        <div role="menu" className="absolute right-0 top-11 z-50 w-56 rounded-2xl border border-line bg-surface p-1.5 shadow-2xl" onClick={() => setOpen(false)}>
          <div className="px-3 py-2">
            <p className="truncate font-semibold">{user.display_name}</p>
            <p className="truncate text-[12px] text-faint">@{user.username} · {user.rating} rating</p>
          </div>
          <div className="my-1 h-px bg-line" />
          <Link role="menuitem" className={item} href={`/u/${user.username}`}>Profile</Link>
          <Link role="menuitem" className={item} href="/bookmarks">Bookmarks</Link>
          <Link role="menuitem" className={item} href="/wallet">Wallet · {user.credits} credits</Link>
          <Link role="menuitem" className={item} href="/settings">Settings</Link>
          {user.role === "admin" && <Link role="menuitem" className={item} href="/admin">Admin</Link>}
          <div className="my-1 h-px bg-line" />
          <button role="menuitem" className={cx(item, "w-full text-left text-dim")} onClick={async () => { await logout(); router.push("/"); }}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

const LINKS = [
  { href: "/home", label: "Home" },
  { href: "/explore", label: "Explore" },
  { href: "/", label: "Arena" },
  { href: "/challenges", label: "Challenges" },
  { href: "/leaderboard", label: "Leaderboard" },
];

export function TopNav() {
  const { status, requireAuth } = useAuth();
  const path = usePathname();
  const router = useRouter();
  if (path?.startsWith("/d/") && path.endsWith("/verdict")) return null; // cinematic, full-bleed
  return (
    <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4 sm:h-16 sm:px-6">
        <Logo />
        <nav className="ml-6 hidden items-center gap-1 md:flex" aria-label="Primary">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href}
              className={cx("rounded-full px-3 py-1.5 text-sm font-medium transition",
                path === l.href ? "bg-surface-2 text-text" : "text-dim hover:text-text")}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          <Link href="/search" aria-label="Search" className="grid size-9 place-items-center rounded-full text-dim hover:bg-surface-2 hover:text-text">
            <svg viewBox="0 0 20 20" className="size-[18px]" fill="currentColor" aria-hidden><path d="M8.5 3a5.5 5.5 0 1 0 3.3 9.9l3.6 3.6 1.1-1.1-3.6-3.6A5.5 5.5 0 0 0 8.5 3zm0 1.6a3.9 3.9 0 1 1 0 7.8 3.9 3.9 0 0 1 0-7.8z" /></svg>
          </Link>
          <ThemeToggle />
          {status === "authed" && <MessagesLink />}
          {status === "authed" && <Bell />}
          <span className="hidden sm:inline-flex">
            <Button size="sm" variant="primary" onClick={() => requireAuth("Sign in to post.") && openCompose()}>Post</Button>
          </span>
          <span className="hidden lg:inline-flex">
            <Button size="sm" variant="for" onClick={() => requireAuth("Sign in to start a debate.") && router.push("/new")}>
              Start a debate
            </Button>
          </span>
          {status === "authed" ? <AccountMenu /> : status === "anon" ? (
            <Button size="sm" variant="outline" href={`/login?next=${encodeURIComponent(path ?? "/")}`}>Sign in</Button>
          ) : <span className="size-8" />}
        </div>
      </div>
    </header>
  );
}

function CreateSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const option = "flex w-full items-center gap-4 rounded-2xl border border-line p-4 text-left transition hover:bg-surface-2";
  return (
    <Sheet open={open} onClose={onClose} title="Create">
      <div className="flex flex-col gap-3">
        <button className={option} onClick={() => { onClose(); openCompose(); }}>
          <span className="grid size-11 shrink-0 place-items-center rounded-full bg-text text-bg">
            <svg viewBox="0 0 20 20" className="size-5" fill="currentColor" aria-hidden><path d="M13.6 3.3a1.5 1.5 0 0 1 2.1 0l1 1a1.5 1.5 0 0 1 0 2.1L8 15.1 4 16l.9-4z" /></svg>
          </span>
          <span><span className="block font-semibold">Post</span><span className="text-sm text-dim">Share a take, a photo or a question.</span></span>
        </button>
        <button className={option} onClick={() => { onClose(); router.push("/new"); }}>
          <span className="grid size-11 shrink-0 place-items-center rounded-full bg-for text-[#0a0a0b]">
            <svg viewBox="0 0 20 20" className="size-5" fill="currentColor" aria-hidden><path d="M3 4h6v12H3zm8 0h6v12h-6z" /></svg>
          </span>
          <span><span className="block font-semibold">Debate</span><span className="text-sm text-dim">Argue it out against a person or an AI.</span></span>
        </button>
      </div>
    </Sheet>
  );
}

export function BottomNav() {
  const path = usePathname();
  const { user, requireAuth } = useAuth();
  const [creating, setCreating] = useState(false);
  if (path?.startsWith("/d/")) return null; // the arena owns the bottom of the screen
  const tab = (href: string, label: string, icon: React.ReactNode) => (
    <Link href={href} className={cx("flex flex-1 flex-col items-center gap-0.5 py-2 text-[10.5px] font-medium", path === href ? "text-text" : "text-faint")}>
      {icon}
      {label}
    </Link>
  );
  return (
    <nav aria-label="Mobile" className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t border-line bg-bg/90 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl md:hidden">
      {tab("/home", "Home", <svg viewBox="0 0 20 20" className="size-5" fill="currentColor"><path d="M10 2.5 2.5 9v8.5h5v-5h5v5h5V9z" /></svg>)}
      {tab("/explore", "Explore", <svg viewBox="0 0 20 20" className="size-5" fill="currentColor"><path d="M8.5 3a5.5 5.5 0 1 0 3.3 9.9l3.6 3.6 1.1-1.1-3.6-3.6A5.5 5.5 0 0 0 8.5 3zm0 1.6a3.9 3.9 0 1 1 0 7.8 3.9 3.9 0 0 1 0-7.8z" /></svg>)}
      <button onClick={() => requireAuth("Sign in to post or start a debate.") && setCreating(true)} aria-label="Create a post or debate" className="flex flex-1 items-center justify-center">
        <span className="grid size-11 place-items-center rounded-full bg-for text-[#0a0a0b] shadow-[0_0_24px_var(--for-glow)]">
          <svg viewBox="0 0 20 20" className="size-5" fill="currentColor"><path d="M9 4h2v5h5v2h-5v5H9v-5H4V9h5z" /></svg>
        </span>
      </button>
      {tab("/messages", "Messages", <svg viewBox="0 0 20 20" className="size-5" fill="currentColor"><path d="M3 4.5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1zm.6 1.6 6.4 4.6 6.4-4.6z" /></svg>)}
      {tab(user ? `/u/${user.username}` : "/login", user ? "You" : "Sign in",
        <svg viewBox="0 0 20 20" className="size-5" fill="currentColor"><path d="M10 10a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zm-6 7c0-3.3 2.7-5 6-5s6 1.7 6 5z" /></svg>)}
      <CreateSheet open={creating} onClose={() => setCreating(false)} />
    </nav>
  );
}

export function Footer() {
  const path = usePathname();
  if (path?.startsWith("/d/")) return null;
  return (
    <footer className="mt-20 border-t border-line pb-24 pt-10 md:pb-10">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 sm:px-6 md:flex-row md:items-center md:justify-between">
        <div>
          <Logo />
          <p className="mt-2 max-w-sm text-sm text-dim">Ask anything. Pick your corners. The crowd and an impartial AI judge decide who made the stronger case.</p>
        </div>
        <nav className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-dim" aria-label="Footer">
          <Link href="/about" className="hover:text-text">How it works</Link>
          <Link href="/terms" className="hover:text-text">Terms</Link>
          <Link href="/privacy" className="hover:text-text">Privacy</Link>
          <Link href="/refunds" className="hover:text-text">Refunds</Link>
          <Link href="/shipping" className="hover:text-text">Delivery</Link>
          <Link href="/contact" className="hover:text-text">Contact</Link>
        </nav>
      </div>
    </footer>
  );
}
