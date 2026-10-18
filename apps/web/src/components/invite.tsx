"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { useToast } from "@/components/toast";
import { Avatar, Button, ErrorBlock, PageTitle, Spinner } from "@/components/ui";
import { errorMessage, get } from "@/lib/api";
import { track } from "@/lib/analytics";
import { useAuth } from "@/lib/auth";
import { timeAgo } from "@/lib/format";

interface ReferralSummary {
  enabled: boolean;
  code: string;
  link: string;
  inviter_credits: number;
  invitee_credits: number;
  max_rewards: number;
  rewarded: number;
  invited: { username: string; display_name: string; avatar_url: string | null; joined_at: string; verified: boolean }[];
}

interface Inviter {
  username: string;
  display_name: string;
  avatar_url: string | null;
  invitee_credits: number;
}

const credits = (n: number) => `${n} free credit${n === 1 ? "" : "s"}`;

// The invite cookie is set by /r/<code>; read it without a hydration mismatch (null on the server and first paint).
const noSubscribe = () => () => {};
function readRefCookie(): string | null {
  const m = document.cookie.match(/(?:^|;\s*)provok_ref=([a-z0-9]{8})/);
  return m ? m[1] : null;
}
function useRefCode(): string | null {
  return useSyncExternalStore(noSubscribe, readRefCookie, () => null);
}

/** "Akshat invited you" for signed-out visitors who arrived through an invite link. */
export function InviteBanner() {
  const { status } = useAuth();
  const code = useRefCode();
  const [hidden, setHidden] = useState(false);
  const q = useQuery({
    queryKey: ["referral-inviter", code],
    queryFn: () => get<Inviter>(`/referrals/${code}`),
    enabled: !!code && status === "anon",
    staleTime: Infinity,
  });
  if (hidden || status !== "anon" || !q.data) return null;
  const who = q.data;
  return (
    <div role="status" className="border-b border-for/30 bg-for-soft">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-2 text-[13px] sm:px-6">
        <span className="flex min-w-0 flex-1 basis-64 items-start gap-2.5">
          <span className="mt-px shrink-0"><Avatar user={who} size={22} /></span>
          <span><b>{who.display_name}</b> invited you to Provok. Sign up and confirm your email to get {credits(who.invitee_credits)} for AI debates.</span>
        </span>
        <Link href="/signup" className="font-semibold underline underline-offset-4" onClick={() => track("invite_banner_signup")}>Sign up</Link>
        <button onClick={() => setHidden(true)} className="ml-auto text-faint" aria-label="Dismiss">✕</button>
      </div>
    </div>
  );
}

export function InviteView() {
  const { status, requireAuth } = useAuth();
  const toast = useToast();
  const q = useQuery({ queryKey: ["referral"], queryFn: () => get<ReferralSummary>("/me/referral"), enabled: status === "authed" });
  useEffect(() => {
    if (status === "anon") requireAuth("Sign in to invite your friends.");
    if (status === "authed") track("invite_viewed");
  }, [status, requireAuth]);

  if (status !== "authed" || q.isLoading) return <div className="grid min-h-[50dvh] place-items-center"><Spinner className="size-6" /></div>;
  if (q.isError || !q.data) return <div className="mx-auto max-w-2xl px-4 py-16"><ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} /></div>;
  const r = q.data;
  const message = `Come argue with me on Provok: debate people or AI, the crowd votes and an AI judge decides. Join with my link and get ${credits(r.invitee_credits)}:`;
  const left = Math.max(0, r.max_rewards - r.rewarded);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(r.link);
      toast("Invite link copied.", "success");
      track("invite_shared", { via: "copy" });
    } catch {
      toast(r.link, "info");
    }
  };
  const nativeShare = async () => {
    try {
      await navigator.share({ title: "Join me on Provok", text: message, url: r.link });
      track("invite_shared", { via: "native" });
    } catch (e) {
      if ((e as Error).name !== "AbortError") await copy();
    }
  };

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-4 pb-20 pt-8 sm:px-6">
      <PageTitle eyebrow="INVITE" title="Bring a sparring partner." />

      <section className="stage grain rounded-3xl border border-line p-6">
        <p className="text-[15px] text-dim">
          When a friend joins with your link and confirms their email, <b className="text-text">you get {credits(r.inviter_credits)}</b> and{" "}
          <b className="text-text">they get {credits(r.invitee_credits)}</b>. 1 credit = 1 AI debate.
        </p>
        <div className="mt-5 flex items-center gap-2 rounded-2xl border border-line bg-surface p-1.5 pl-4">
          <span className="min-w-0 flex-1 truncate font-mono text-[13px]">{r.link}</span>
          <Button size="sm" onClick={copy}>Copy</Button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <a className="inline-flex h-9 items-center rounded-full bg-for px-4 text-[14px] font-semibold text-[#0a0a0b]"
            href={`https://wa.me/?text=${encodeURIComponent(`${message} ${r.link}`)}`} target="_blank" rel="noopener noreferrer"
            onClick={() => track("invite_shared", { via: "whatsapp" })}>
            Send on WhatsApp
          </a>
          {typeof navigator !== "undefined" && "share" in navigator && (
            <Button size="sm" variant="outline" className="h-9" onClick={nativeShare}>More ways to share</Button>
          )}
        </div>
      </section>

      <section className="grid grid-cols-2 gap-4">
        <div className="rounded-3xl border border-line bg-surface p-5">
          <p className="font-mono text-[11px] font-bold tracking-[0.16em] text-faint">CREDITS EARNED</p>
          <p className="font-display mt-1 text-4xl font-extrabold tabular">{r.rewarded * r.inviter_credits}</p>
        </div>
        <div className="rounded-3xl border border-line bg-surface p-5">
          <p className="font-mono text-[11px] font-bold tracking-[0.16em] text-faint">REWARDS LEFT</p>
          <p className="font-display mt-1 text-4xl font-extrabold tabular">{left}<span className="text-xl text-faint">/{r.max_rewards}</span></p>
        </div>
      </section>

      <section>
        <h2 className="font-display mb-3 text-xl font-bold">Who joined</h2>
        {r.invited.length === 0 ? (
          <p className="text-sm text-dim">Nobody yet. Your first sparring partner is one WhatsApp away.</p>
        ) : (
          <ul className="divide-y divide-line rounded-3xl border border-line bg-surface">
            {r.invited.map((u) => (
              <li key={u.username} className="flex items-center gap-3 px-4 py-3 text-sm">
                <Avatar user={u} size={32} />
                <Link href={`/u/${u.username}`} className="min-w-0 flex-1 truncate font-semibold hover:underline">{u.display_name}</Link>
                <span className={u.verified ? "text-ok" : "text-faint"}>{u.verified ? "Joined" : "Waiting for email"}</span>
                <span className="w-16 text-right text-[12px] text-faint">{timeAgo(u.joined_at)}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-3 text-[12px] text-faint">Rewards are paid when your friend confirms their email, up to {r.max_rewards} friends. Inviting your own other accounts doesn&rsquo;t count.</p>
      </section>
    </div>
  );
}
