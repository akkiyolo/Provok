"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { DebateCard } from "@/components/debate-card";
import { DailyDebateCard } from "@/components/posts/feeds";
import { PostCard, PostSkeleton } from "@/components/posts/post-card";
import { VerifiedBadge } from "@/components/posts/post-extras";
import { useToast } from "@/components/toast";
import { Avatar, Button, ErrorBlock } from "@/components/ui";
import { del, errorMessage, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DebateCard as Card, PostView, Suggestion, Trend } from "@/lib/types";

export function FollowButton({ username, initial = false }: { username: string; initial?: boolean }) {
  const { requireAuth } = useAuth();
  const toast = useToast();
  const [following, setFollowing] = useState(initial);
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    if (!requireAuth("Sign in to follow people.")) return;
    setBusy(true);
    try {
      if (following) await del(`/users/${username}/follow`);
      else await post(`/users/${username}/follow`);
      setFollowing(!following);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button size="sm" variant={following ? "outline" : "primary"} loading={busy} onClick={toggle} aria-label={`${following ? "Unfollow" : "Follow"} @${username}`}>
      {following ? "Following" : "Follow"}
    </Button>
  );
}

export function WhoToFollow({ people }: { people: Suggestion[] }) {
  if (!people.length) return null;
  return (
    <ul className="flex flex-col gap-1">
      {people.map((s) => (
        <li key={s.user.username} className="flex items-center gap-3 rounded-2xl px-2 py-2 hover:bg-surface-2/60">
          <Link href={`/u/${s.user.username}`} className="flex min-w-0 flex-1 items-center gap-3">
            <Avatar user={s.user} size={40} />
            <span className="min-w-0">
              <span className="block truncate font-semibold">{s.user.display_name}{s.user.verified && <VerifiedBadge />}</span>
              <span className="block truncate text-[12.5px] text-faint">@{s.user.username} · {s.reason}</span>
            </span>
          </Link>
          <FollowButton username={s.user.username} />
        </li>
      ))}
    </ul>
  );
}

interface Explore {
  trends: Trend[];
  top_posts: PostView[];
  people: Suggestion[];
  live_debates: Card[];
}

const heading = "mb-3 font-mono text-[11px] font-bold tracking-[0.18em] text-faint";

export function ExploreView() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const ex = useQuery({ queryKey: ["posts", "explore"], queryFn: () => get<Explore>("/explore"), staleTime: 30_000 });
  return (
    <div className="mx-auto grid max-w-6xl gap-6 px-4 pt-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0">
        <h1 className="sr-only">Explore</h1>
        <form role="search" onSubmit={(e) => { e.preventDefault(); if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`); }}>
          <label htmlFor="explore-search" className="sr-only">Search Provok</label>
          <input id="explore-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search posts, debates, people…"
            className="h-12 w-full rounded-full border border-line bg-surface px-5 text-[15px] outline-none placeholder:text-faint focus:border-text/50" />
        </form>
        <div className="mt-5 overflow-hidden border-line sm:rounded-3xl sm:border"><DailyDebateCard /></div>
        {ex.isError && <div className="mt-5"><ErrorBlock message={errorMessage(ex.error)} retry={() => ex.refetch()} /></div>}
        {ex.data?.live_debates.length ? (
          <section className="mt-8">
            <h2 className={`${heading} flex items-center justify-between`}>LIVE IN THE ARENA <Link href="/" className="font-sans text-[13px] font-semibold tracking-normal text-text hover:underline">All debates →</Link></h2>
            <div className="grid gap-4 sm:grid-cols-2">{ex.data.live_debates.map((d) => <DebateCard key={d.id} d={d} />)}</div>
          </section>
        ) : null}
        <section className="mt-8">
          <h2 className={heading}>TOP POSTS TODAY</h2>
          <div className="-mx-4 border-line sm:mx-0 sm:rounded-3xl sm:border">
            {ex.isLoading ? [0, 1, 2].map((i) => <PostSkeleton key={i} />)
              : ex.data?.top_posts.length ? ex.data.top_posts.map((p) => <PostCard key={p.feed_id} p={p} />)
                : <p className="p-6 text-center text-sm text-dim">No posts yet today.</p>}
          </div>
        </section>
      </div>
      <aside className="flex flex-col gap-6">
        <section className="rounded-3xl border border-line bg-surface p-4">
          <h2 className="font-display mb-2 px-2 text-xl font-bold">Who to follow</h2>
          {ex.data ? <WhoToFollow people={ex.data.people} /> : <div className="skeleton h-40" />}
        </section>
        <section className="rounded-3xl border border-line bg-surface p-5">
          <h2 className="font-display mb-3 text-xl font-bold">Trending</h2>
          {ex.data?.trends.length ? (
            <ol className="flex flex-col gap-3">
              {ex.data.trends.map((t) => (
                <li key={t.tag}>
                  <Link href={`/tag/${encodeURIComponent(t.tag)}`} className="block hover:opacity-80">
                    <span className="block font-semibold">#{t.tag}</span>
                    <span className="text-[12px] text-faint">{t.people} people posting</span>
                  </Link>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-dim">Nothing trending yet.</p>}
          <Link href="/leaderboard" className="mt-4 block border-t border-line pt-3 text-sm font-semibold hover:underline">Leaderboard: the best debaters →</Link>
        </section>
      </aside>
    </div>
  );
}
