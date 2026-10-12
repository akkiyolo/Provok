"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CardSkeleton, DebateCard } from "@/components/debate-card";
import { useFeed } from "@/components/feed";
import { PostCard } from "@/components/posts/post-card";
import { Avatar, Button, Empty, ErrorBlock, ModelBadge, PageTitle, Tabs } from "@/components/ui";
import { errorMessage, get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cx } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import type { DebateCard as Card, PostView, PublicUser } from "@/lib/types";

export function ChallengesView() {
  const q = useFeed("challenges");
  const { requireAuth } = useAuth();
  const router = useRouter();
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="mx-auto max-w-7xl px-4 pt-8 sm:px-6">
      <PageTitle eyebrow="OPEN CHALLENGES" title="Take the other side.">
        <p className="max-w-xl text-dim">Someone picked a corner and is waiting for a worthy opponent. Accept, and the bell rings.</p>
      </PageTitle>
      {q.isError && <ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} />}
      {q.isLoading && <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3"><CardSkeleton /><CardSkeleton /><CardSkeleton /></div>}
      {!q.isLoading && items.length === 0 && (
        <Empty title="No open challenges right now." body="Post a question, take a side, and let someone come for you."
          action={<Button variant="for" onClick={() => requireAuth("Sign in to post a challenge.") && router.push("/new")}>Post a challenge →</Button>} />
      )}
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">{items.map((d) => <DebateCard key={d.id} d={d} />)}</div>
      {q.hasNextPage && (
        <div className="mt-8 flex justify-center"><Button variant="outline" loading={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Load more</Button></div>
      )}
    </div>
  );
}

interface HumanRow extends PublicUser { wins: number; losses: number; draws: number; rank: number }
interface ModelRow { key: string; display_name: string; provider: string; tier: string; rating: number; played: number; wins: number; draws: number; losses: number; win_rate: number }

export function LeaderboardView() {
  const params = useSearchParams();
  const router = useRouter();
  const meta = useMeta();
  const type = params.get("type") === "model" ? "model" : "human";
  const category = params.get("category") ?? "";
  const q = useQuery({
    queryKey: ["leaderboard", type, category],
    queryFn: () => get<{ items: (HumanRow | ModelRow)[] }>(`/leaderboard?type=${type}${category ? `&category=${category}` : ""}`),
  });
  const set = (t: string, c = "") => router.replace(`/leaderboard?type=${t}${c ? `&category=${c}` : ""}`, { scroll: false });

  return (
    <div className="mx-auto max-w-4xl px-4 pt-8 sm:px-6">
      <PageTitle eyebrow="LEADERBOARD" title={type === "model" ? "Which AI argues best?" : "The sharpest minds."}>
        <p className="text-dim">{type === "model" ? "Win rates from blind-judged debates. The judge never knows which model it's scoring." : "Ranked by Elo. Win against stronger opponents to climb faster."}</p>
      </PageTitle>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <Tabs value={type} onChange={(t) => set(t)} items={[{ value: "human", label: "Humans" }, { value: "model", label: "AI models" }]} />
        {type === "model" && (
          <select value={category} onChange={(e) => set("model", e.target.value)} aria-label="Topic"
            className="h-10 rounded-full border border-line bg-surface px-4 text-sm capitalize">
            <option value="">All topics</option>
            {(meta?.categories ?? []).map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
      </div>
      {q.isError && <ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} />}
      {q.isLoading && <div className="flex flex-col gap-2">{Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton h-16" />)}</div>}
      {q.data && q.data.items.length === 0 && <Empty title="No ranked debaters yet." body="Finish a debate to get on the board." />}
      <ol className="flex flex-col gap-2">
        {q.data?.items.map((row, i) => type === "human" ? (
          <li key={(row as HumanRow).username}>
            <Link href={`/u/${(row as HumanRow).username}`} className="flex items-center gap-4 rounded-2xl border border-line bg-surface px-4 py-3 transition hover:border-line-strong">
              <span className={cx("w-8 font-mono text-lg font-bold", i === 0 ? "text-win" : "text-faint")}>{i + 1}</span>
              <Avatar user={row as HumanRow} size={40} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold">{(row as HumanRow).display_name}</span>
                <span className="font-mono text-[12px] text-faint">{(row as HumanRow).wins}W · {(row as HumanRow).losses}L · {(row as HumanRow).draws}D</span>
              </span>
              <span className="font-mono text-xl font-bold tabular">{(row as HumanRow).rating}</span>
            </Link>
          </li>
        ) : (
          <li key={(row as ModelRow).key} className="flex items-center gap-4 rounded-2xl border border-line bg-surface px-4 py-3">
            <span className={cx("w-8 font-mono text-lg font-bold", i === 0 ? "text-win" : "text-faint")}>{i + 1}</span>
            <span className="min-w-0 flex-1">
              <ModelBadge model={row as ModelRow} />
              <span className="mt-1 block font-mono text-[12px] text-faint">{(row as ModelRow).played} debates · {(row as ModelRow).wins}W {(row as ModelRow).losses}L {(row as ModelRow).draws}D · Elo {(row as ModelRow).rating}</span>
            </span>
            <span className="text-right">
              <span className="block font-mono text-xl font-bold tabular">{Math.round((row as ModelRow).win_rate * 100)}%</span>
              <span className="text-[11px] text-faint">win rate</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function SearchView() {
  const params = useSearchParams();
  const router = useRouter();
  const [text, setText] = useState(params.get("q") ?? "");
  const q = params.get("q") ?? "";
  useEffect(() => {
    const t = setTimeout(() => {
      if (text.trim() !== q) router.replace(text.trim() ? `/search?q=${encodeURIComponent(text.trim())}` : "/search", { scroll: false });
    }, 350);
    return () => clearTimeout(t);
  }, [text, q, router]);
  const res = useQuery({
    queryKey: ["search", q],
    queryFn: () => get<{ debates: Card[]; users: PublicUser[]; posts: PostView[] }>(`/search?q=${encodeURIComponent(q)}`),
    enabled: q.length > 0,
  });
  return (
    <div className="mx-auto max-w-5xl px-4 pt-8 sm:px-6">
      <label htmlFor="search" className="sr-only">Search posts, debates and people</label>
      <input id="search" value={text} onChange={(e) => setText(e.target.value)} autoFocus placeholder="Search posts, debates, people…"
        className="font-display h-16 w-full rounded-3xl border border-line bg-surface px-6 text-2xl font-bold outline-none placeholder:text-faint focus:border-text/50" />
      {res.isLoading && q && <div className="mt-8 grid gap-5 md:grid-cols-2"><CardSkeleton /><CardSkeleton /></div>}
      {res.data && (
        <div className="mt-8 flex flex-col gap-10">
          {res.data.users.length > 0 && (
            <section>
              <h2 className="mb-3 font-mono text-[11px] font-bold tracking-[0.18em] text-faint">PEOPLE</h2>
              <div className="flex flex-wrap gap-2">
                {res.data.users.map((u) => (
                  <Link key={u.username} href={`/u/${u.username}`} className="flex items-center gap-2 rounded-full border border-line bg-surface py-1 pl-1 pr-4 hover:border-line-strong">
                    <Avatar user={u} size={28} /><span className="text-sm font-semibold">{u.display_name}</span><span className="text-[12px] text-faint">@{u.username}</span>
                  </Link>
                ))}
              </div>
            </section>
          )}
          {res.data.posts.length > 0 && (
            <section>
              <h2 className="mb-3 font-mono text-[11px] font-bold tracking-[0.18em] text-faint">POSTS</h2>
              <div className="-mx-4 border-line sm:mx-0 sm:rounded-3xl sm:border">
                {res.data.posts.map((p) => <PostCard key={p.feed_id} p={p} />)}
              </div>
            </section>
          )}
          <section>
            <h2 className="mb-3 font-mono text-[11px] font-bold tracking-[0.18em] text-faint">DEBATES</h2>
            {res.data.debates.length === 0 ? <Empty title="No debates match." body="Why not start that debate yourself?" action={<Button variant="for" href="/new">Start it →</Button>} /> : (
              <div className="grid gap-5 md:grid-cols-2">{res.data.debates.map((d) => <DebateCard key={d.id} d={d} />)}</div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
