"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { DebateCard } from "@/components/debate-card";
import { PostList, usePosts } from "@/components/posts/feeds";
import { PostCard } from "@/components/posts/post-card";
import { VerifiedBadge } from "@/components/posts/post-extras";
import { useToast } from "@/components/toast";
import { Avatar, Button, Empty, ErrorBlock, PageTitle, Spinner, Tabs } from "@/components/ui";
import { ApiError, api, del, errorMessage, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { track } from "@/lib/analytics";
import { cx, timeAgo } from "@/lib/format";
import { useIsAndroidApp } from "@/lib/platform";
import type { NotificationItem, Profile, Wallet } from "@/lib/types";

// ── Profile ────────────────────────────────────────────────────────────────

type ProfileTab = "posts" | "replies" | "media" | "likes" | "debates";
const PROFILE_TABS: { value: ProfileTab; label: string }[] = [
  { value: "posts", label: "Posts" }, { value: "replies", label: "Replies" }, { value: "media", label: "Photos" },
  { value: "likes", label: "Likes" }, { value: "debates", label: "Debates" },
];

function ProfilePosts({ username, tab }: { username: string; tab: Exclude<ProfileTab, "debates"> }) {
  const q = usePosts(["user", username, tab], `/users/${encodeURIComponent(username)}/posts?tab=${tab}`);
  const empty: Record<typeof tab, string> = {
    posts: "No posts yet.", replies: "No replies yet.", media: "No photos yet.", likes: "No liked posts yet.",
  };
  return <PostList q={q} empty={<Empty title={empty[tab]} />} />;
}

export function ProfileView({ username }: { username: string }) {
  const { requireAuth } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<ProfileTab>("posts");
  const relation = useMutation({
    mutationFn: ({ kind, on }: { kind: "mute" | "block"; on: boolean }) =>
      api(`/users/${username}/${kind}`, { method: on ? "POST" : "DELETE" }),
    onSuccess: (_d, { kind, on }) => {
      toast(`${on ? (kind === "mute" ? "Muted" : "Blocked") : kind === "mute" ? "Unmuted" : "Unblocked"} @${username}.`, "success");
      void qc.invalidateQueries({ queryKey: ["profile", username] });
      void qc.invalidateQueries({ queryKey: ["posts"] });
    },
    onError: (e) => toast(errorMessage(e), "error"),
  });
  const q = useQuery({ queryKey: ["profile", username], queryFn: () => get<Profile>(`/users/${encodeURIComponent(username)}`) });
  const follow = useMutation({
    mutationFn: (following: boolean) => following ? del(`/users/${username}/follow`) : post(`/users/${username}/follow`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profile", username] }),
    onError: (e) => toast(errorMessage(e), "error"),
  });
  if (q.isError) {
    return <div className="mx-auto max-w-2xl px-4 py-16"><ErrorBlock message={q.error instanceof ApiError && q.error.status === 404 ? "No debater by that name." : errorMessage(q.error)} /></div>;
  }
  const p = q.data;
  if (!p) return <div className="mx-auto max-w-5xl px-4 py-10"><div className="skeleton h-40 w-full" /></div>;
  const total = p.wins + p.losses + p.draws;
  return (
    <div className="mx-auto max-w-5xl px-4 pt-8 sm:px-6">
      {p.banner_url && (
        // eslint-disable-next-line @next/next/no-img-element -- user-uploaded cover photo
        <img src={p.banner_url} alt="" className="mb-[-3rem] aspect-[3/1] w-full rounded-[2rem] border border-line object-cover" />
      )}
      <section className={cx("stage grain relative flex flex-col gap-6 rounded-[2rem] border border-line p-6 sm:flex-row sm:items-center sm:p-8", p.banner_url && "mx-3 sm:mx-6")}>
        <Avatar user={p} size={96} />
        <div className="flex-1">
          <h1 className="font-display text-4xl font-extrabold leading-none">{p.display_name}{p.verified && <VerifiedBadge />}</h1>
          <p className="mt-1 text-dim">@{p.username} · joined {new Date(p.created_at).toLocaleDateString(undefined, { month: "short", year: "numeric" })}</p>
          {p.bio && <p className="mt-3 max-w-lg text-[15px]">{p.bio}</p>}
          {(p.location || p.website) && (
            <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[14px] text-dim">
              {p.location && <span>📍 {p.location}</span>}
              {p.website && (
                <a href={p.website} target="_blank" rel="noopener noreferrer nofollow ugc" className="text-text underline decoration-line-strong underline-offset-2 hover:decoration-text">
                  🔗 {p.website.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
                </a>
              )}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-5 text-sm">
            <span><b className="font-mono text-lg">{p.rating}</b> <span className="text-dim">rating · #{p.rank}</span></span>
            <span><b className="font-mono text-lg">{p.wins}</b><span className="text-dim">W </span><b className="font-mono text-lg">{p.losses}</b><span className="text-dim">L </span><b className="font-mono text-lg">{p.draws}</b><span className="text-dim">D</span></span>
            {total > 0 && <span className="text-dim">{Math.round((p.wins / total) * 100)}% win rate</span>}
            <span><b className="font-mono">{p.followers}</b> <span className="text-dim">followers</span></span>
            <span><b className="font-mono">{p.following}</b> <span className="text-dim">following</span></span>
            <span><b className="font-mono">{p.posts_count}</b> <span className="text-dim">posts</span></span>
          </div>
        </div>
        {p.is_me ? <Button variant="outline" href="/settings">Edit profile</Button> : (
          <div className="flex flex-col gap-2">
            <Button variant={p.is_following ? "outline" : "primary"} loading={follow.isPending}
              onClick={() => requireAuth("Sign in to follow debaters.") && follow.mutate(p.is_following)}>
              {p.is_following ? "Following" : "Follow"}
            </Button>
            {!p.is_blocked && !p.blocks_you && (
              <Button variant="outline" onClick={() => {
                if (!requireAuth("Sign in to send messages.")) return;
                void post<{ id: string }>(`/conversations/with/${p.username}`).then((c) => router.push(`/messages/${c.id}`))
                  .catch((e) => toast(errorMessage(e), "error"));
              }}>Message</Button>
            )}
            <Button variant="for" onClick={() => {
              if (!requireAuth("Sign in to challenge someone.")) return;
              sessionStorage.setItem("provok:challenge", p.username);
              router.push(`/new?invite=${encodeURIComponent(p.username)}`);
            }}>
              Challenge
            </Button>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost" loading={relation.isPending && relation.variables?.kind === "mute"}
                onClick={() => requireAuth("Sign in first.") && relation.mutate({ kind: "mute", on: !p.is_muted })}>
                {p.is_muted ? "Unmute" : "Mute"}
              </Button>
              <Button size="sm" variant="ghost" className="text-danger" loading={relation.isPending && relation.variables?.kind === "block"}
                onClick={() => {
                  if (!requireAuth("Sign in first.")) return;
                  if (!p.is_blocked && !window.confirm(`Block @${p.username}? They won't be able to follow you or reply to your posts.`)) return;
                  relation.mutate({ kind: "block", on: !p.is_blocked });
                }}>
                {p.is_blocked ? "Unblock" : "Block"}
              </Button>
            </div>
          </div>
        )}
      </section>
      {p.blocks_you ? (
        <div className="mt-8"><Empty title={`@${p.username} blocked you.`} body="You can't see their posts or reply to them." /></div>
      ) : p.is_blocked ? (
        <div className="mt-8"><Empty title={`You blocked @${p.username}.`} body="Unblock them to see their posts again." /></div>
      ) : (
        <>
          <div className="sticky top-14 z-20 -mx-4 mt-8 bg-bg/85 px-4 py-3 backdrop-blur-xl sm:top-16 sm:mx-0 sm:px-0">
            <Tabs value={tab} onChange={setTab} items={PROFILE_TABS} className="w-fit max-w-full" />
          </div>
          {tab === "posts" && p.pinned && (
            <div className="-mx-4 mb-3 border-line sm:mx-0 sm:rounded-3xl sm:border"><PostCard p={p.pinned} showPinned /></div>
          )}
          {tab === "debates" ? (
            p.debates.length === 0 ? <Empty title="No debates yet." /> : (
              <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">{p.debates.map((d) => <DebateCard key={d.id} d={d} />)}</div>
            )
          ) : (
            <div className="-mx-4 border-line sm:mx-0 sm:rounded-3xl sm:border"><ProfilePosts key={tab} username={p.username} tab={tab} /></div>
          )}
        </>
      )}
    </div>
  );
}

// ── Wallet ─────────────────────────────────────────────────────────────────

interface RazorpayCtor {
  new (opts: Record<string, unknown>): { open: () => void; on: (ev: string, fn: (r: { error?: { description?: string } }) => void) => void };
}

function loadRazorpay(): Promise<RazorpayCtor> {
  const w = window as unknown as { Razorpay?: RazorpayCtor };
  if (w.Razorpay) return Promise.resolve(w.Razorpay);
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.async = true;
    s.onload = () => (w.Razorpay ? resolve(w.Razorpay) : reject(new Error("Razorpay failed to load")));
    s.onerror = () => reject(new Error("Couldn't reach the payment provider. Check your connection."));
    document.body.appendChild(s);
  });
}

const REASON: Record<string, string> = { purchase: "Credits purchased", debate: "AI debate", refund: "Refund", grant: "Bonus credits", adjustment: "Adjustment" };

export function WalletView() {
  const { status, requireAuth, reloadUser } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [buying, setBuying] = useState<string | null>(null);
  const inApp = useIsAndroidApp();
  const q = useQuery({ queryKey: ["wallet"], queryFn: () => get<Wallet>("/me/wallet"), enabled: status === "authed" });
  useEffect(() => {
    if (status === "anon") requireAuth("Sign in to see your wallet.");
    if (status === "authed") track("wallet_viewed");
  }, [status, requireAuth]);

  const buy = async (packId: string) => {
    setBuying(packId);
    try {
      const [Razorpay, order] = await Promise.all([
        loadRazorpay(),
        post<{ order_id: string; amount: number; currency: string; key_id: string; name: string; description: string; prefill: Record<string, string> }>("/payments/order", { pack_id: packId }),
      ]);
      track("checkout_opened", { pack: packId });
      const rzp = new Razorpay({
        key: order.key_id, amount: order.amount, currency: order.currency, name: order.name, description: order.description,
        order_id: order.order_id, prefill: order.prefill, theme: { color: "#FF5A1F" },
        handler: async (resp: Record<string, string>) => {
          try {
            await post("/payments/verify", resp);
            toast("Credits added. Go win something.", "success");
          } catch {
            toast("Payment received — your credits will appear in a moment.", "info");
          } finally {
            await Promise.all([qc.invalidateQueries({ queryKey: ["wallet"] }), reloadUser()]);
          }
        },
        modal: { ondismiss: () => setBuying(null) },
      });
      rzp.on("payment.failed", (r) => toast(r.error?.description ?? "Payment failed. You haven't been charged.", "error"));
      rzp.open();
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBuying(null);
    }
  };

  if (status !== "authed") return <div className="grid min-h-[50dvh] place-items-center"><Spinner className="size-6" /></div>;
  if (q.isError) return <div className="mx-auto max-w-2xl px-4 py-16"><ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} /></div>;
  const w = q.data;
  return (
    <div className="mx-auto max-w-4xl px-4 pt-8 sm:px-6">
      <PageTitle eyebrow="WALLET" title="Fuel for the arena." />
      {!w ? <div className="skeleton h-40" /> : (
        <>
          <section className="grid gap-4 sm:grid-cols-2">
            <div className="stage grain rounded-3xl border border-line p-6">
              <p className="font-mono text-[11px] font-bold tracking-[0.16em] text-faint">CREDITS</p>
              <p className="font-display mt-2 text-6xl font-extrabold tabular">{w.credits}</p>
              <p className="mt-2 text-sm text-dim">Standard AI debate: {w.costs.standard} credit · Flagship models: {w.costs.flagship} credits</p>
            </div>
            <div className="rounded-3xl border border-line bg-surface p-6">
              <p className="font-mono text-[11px] font-bold tracking-[0.16em] text-faint">FREE AI DEBATES</p>
              <p className="font-display mt-2 text-6xl font-extrabold tabular">{w.free_ai_debates_left}<span className="text-2xl text-faint">/{w.free_ai_debates_total}</span></p>
              <p className="mt-2 text-sm text-dim">Human vs human, watching and voting are always free.</p>
            </div>
          </section>

          {/* Google Play: no purchases (and no pointers to buying elsewhere) inside the Android app. */}
          {!inApp && (
            <>
              <h2 className="font-display mb-4 mt-10 text-2xl font-bold">Top up</h2>
              {!w.payments_enabled ? <p className="text-sm text-dim">Payments are temporarily unavailable.</p> : (
                <div className="grid gap-4 sm:grid-cols-3">
                  {w.packs.map((p, i) => (
                    <div key={p.id} className={cx("flex flex-col rounded-3xl border p-5", i === 1 ? "border-for shadow-[0_0_32px_var(--for-glow)]" : "border-line bg-surface")}>
                      {i === 1 && <span className="mb-2 w-fit rounded-full bg-for px-2 py-0.5 font-mono text-[10px] font-bold text-[#0a0a0b]">MOST POPULAR</span>}
                      <p className="font-semibold">{p.label ?? p.id}</p>
                      <p className="font-display mt-1 text-4xl font-extrabold">{p.credits} <span className="text-base font-semibold text-dim">credits</span></p>
                      <p className="mt-1 text-sm text-dim">₹{p.amount_inr} · ₹{(p.amount_inr / p.credits).toFixed(1)}/credit</p>
                      <Button className="mt-5" variant={i === 1 ? "for" : "primary"} loading={buying === p.id} disabled={!!buying} onClick={() => buy(p.id)}>
                        Buy for ₹{p.amount_inr}
                      </Button>
                    </div>
                  ))}
                </div>
              )}
              <p className="mt-3 text-[12px] text-faint">Secure checkout by Razorpay — UPI, cards, netbanking. Prices include taxes. See our <Link href="/refunds" className="underline">refund policy</Link>.</p>
            </>
          )}

          <h2 className="font-display mb-4 mt-10 text-2xl font-bold">History</h2>
          {w.history.length === 0 ? <p className="text-sm text-dim">No credit activity yet.</p> : (
            <ul className="divide-y divide-line rounded-3xl border border-line bg-surface">
              {w.history.map((h, i) => (
                <li key={i} className="flex items-center gap-4 px-5 py-3 text-sm">
                  <span className="flex-1">{REASON[h.reason] ?? h.reason}</span>
                  <span className="text-faint">{timeAgo(h.created_at)}</span>
                  <span className={cx("w-14 text-right font-mono font-bold", h.delta > 0 ? "text-ok" : "text-dim")}>{h.delta > 0 ? `+${h.delta}` : h.delta}</span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

// ── Notifications ──────────────────────────────────────────────────────────

export function NotificationsView() {
  const { status, requireAuth } = useAuth();
  const qc = useQueryClient();
  const router = useRouter();
  const q = useQuery({
    queryKey: ["notifications"],
    queryFn: () => get<{ items: NotificationItem[]; unread: number }>("/notifications?limit=50"),
    enabled: status === "authed",
  });
  useEffect(() => {
    if (status === "anon") requireAuth("Sign in to see your notifications.");
  }, [status, requireAuth]);
  const readAll = useMutation({
    mutationFn: () => post("/notifications/read", {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  return (
    <div className="mx-auto max-w-2xl px-4 pt-8 sm:px-6">
      <PageTitle eyebrow="INBOX" title="Notifications">
        {!!q.data?.unread && <div><Button size="sm" variant="outline" onClick={() => readAll.mutate()}>Mark all read</Button></div>}
      </PageTitle>
      {q.isLoading && <div className="flex flex-col gap-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16" />)}</div>}
      {q.data?.items.length === 0 && <Empty title="All quiet." body="Challenges, your-turn pings and verdicts land here." />}
      <ul className="flex flex-col gap-2">
        {q.data?.items.map((n) => (
          <li key={n.id}>
            <button onClick={() => { void post("/notifications/read", { ids: [n.id] }).then(() => qc.invalidateQueries({ queryKey: ["notifications"] })); if (n.link) router.push(n.link); }}
              className={cx("flex w-full items-start gap-3 rounded-2xl border px-4 py-3 text-left transition hover:border-line-strong", n.read ? "border-line bg-surface" : "border-for/40 bg-for-soft")}>
              {!n.read && <span className="mt-2 size-2 shrink-0 rounded-full bg-for" aria-label="Unread" />}
              <span className="flex-1">
                <span className="block font-semibold">{n.title}</span>
                {n.body && <span className="line-clamp-2 block text-sm text-dim">{n.body}</span>}
              </span>
              <span className="shrink-0 text-[12px] text-faint">{timeAgo(n.created_at)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

