"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

import { DebateCard } from "@/components/debate-card";
import { InfiniteSentinel } from "@/components/feed";
import { Composer } from "@/components/posts/composer";
import { openCompose } from "@/components/posts/compose-store";
import { PostCard, PostSkeleton } from "@/components/posts/post-card";
import { Button, Empty, ErrorBlock, PageTitle, Tabs } from "@/components/ui";
import { ApiError, errorMessage, get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DailyDebate, DebateCard as Card, Page, PostView, Trend } from "@/lib/types";

/** Every post list lives under the ["posts", ...] query key, so a new post or deletion refreshes them all. */
export function usePosts(key: string[], path: string, enabled = true) {
  return useInfiniteQuery({
    queryKey: ["posts", ...key],
    queryFn: ({ pageParam, signal }) => {
      const sep = path.includes("?") ? "&" : "?";
      return get<Page<PostView> & { blocked?: boolean }>(`${path}${pageParam ? `${sep}cursor=${encodeURIComponent(pageParam)}` : ""}`, { signal });
    },
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled,
  });
}

export function PostList({ q, empty }: { q: ReturnType<typeof usePosts>; empty: React.ReactNode }) {
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  if (q.isError) return <div className="p-4"><ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} /></div>;
  if (q.isLoading) return <>{[0, 1, 2, 3].map((i) => <PostSkeleton key={i} />)}</>;
  if (items.length === 0) return <div className="p-4">{empty}</div>;
  return (
    <>
      {items.map((p) => <PostCard key={p.feed_id} p={p} />)}
      <InfiniteSentinel onVisible={() => q.fetchNextPage()} disabled={!q.hasNextPage || q.isFetchingNextPage} />
      {q.isFetchingNextPage && <PostSkeleton />}
    </>
  );
}

function Trends() {
  const q = useQuery({ queryKey: ["trends"], queryFn: () => get<{ items: Trend[] }>("/trends"), staleTime: 60_000 });
  return (
    <section aria-labelledby="trends-heading" className="rounded-3xl border border-line bg-surface p-5">
      <h2 id="trends-heading" className="font-display mb-3 text-xl font-bold">Trending</h2>
      {q.data?.items.length ? (
        <ol className="flex flex-col gap-3">
          {q.data.items.map((t, i) => (
            <li key={t.tag}>
              <Link href={`/tag/${encodeURIComponent(t.tag)}`} className="block hover:opacity-80">
                <span className="font-mono text-[11px] text-faint">{i + 1} · TRENDING</span>
                <span className="block font-semibold">#{t.tag}</span>
                <span className="text-[12px] text-faint">{t.people} people posting</span>
              </Link>
            </li>
          ))}
        </ol>
      ) : <p className="text-sm text-dim">Nothing trending yet. Start one with a #hashtag.</p>}
      <Link href="/" className="mt-4 block border-t border-line pt-3 text-sm font-semibold hover:underline">Live debates in the Arena →</Link>
    </section>
  );
}

/** Today's question from @provok: vote in the poll, watch the AI debate, or take a side yourself. */
export function DailyDebateCard() {
  const q = useQuery({ queryKey: ["posts", "daily"], queryFn: () => get<{ daily: DailyDebate | null }>("/daily"), staleTime: 60_000 });
  const d = q.data?.daily;
  if (!d?.post) return null;
  return (
    <section aria-labelledby="daily-heading" className="stage-duel grain border-b border-line">
      <div className="px-4 pt-4 sm:px-5">
        <p id="daily-heading" className="font-mono text-[11px] font-bold tracking-[0.2em] text-faint">TODAY&apos;S DEBATE</p>
        <p className="font-display mt-1 text-[clamp(1.4rem,4vw,1.9rem)] font-extrabold leading-tight">{d.question}</p>
        {d.debate && (
          <Link href={`/d/${d.debate.id}`} className="mt-2 inline-block text-sm font-semibold hover:underline">Watch the AI debate it live →</Link>
        )}
      </div>
      <PostCard p={d.post} />
    </section>
  );
}

/** "N new posts" on the Following timeline: polls for newer posts and shows them on tap. */
function NewPostsBanner({ newest }: { newest: string | undefined }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["feed-new", newest],
    queryFn: () => get<{ count: number }>(`/feed/new?since=${encodeURIComponent(newest!)}`),
    enabled: !!newest,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });
  const n = q.data?.count ?? 0;
  if (!n) return null;
  return (
    <div className="sticky top-[7.5rem] z-10 flex justify-center sm:top-[8.5rem]">
      <button type="button" onClick={() => { window.scrollTo({ top: 0, behavior: "smooth" }); void qc.invalidateQueries({ queryKey: ["posts", "feed", "following"] }); }}
        className="my-2 rounded-full bg-text px-4 py-1.5 text-[13px] font-semibold text-bg shadow-xl">
        ↑ {n} new post{n === 1 ? "" : "s"}
      </button>
    </div>
  );
}

type HomeTab = "for_you" | "following";

export function HomeFeed() {
  const { status } = useAuth();
  const params = useSearchParams();
  const router = useRouter();
  const tab: HomeTab = params.get("tab") === "following" ? "following" : "for_you";
  const q = usePosts(["feed", tab], `/feed?tab=${tab}`, tab === "for_you" || status === "authed");
  const setTab = (t: HomeTab) => router.replace(t === "for_you" ? "/home" : "/home?tab=following", { scroll: false });

  return (
    <div className="mx-auto grid max-w-6xl gap-6 px-0 sm:px-6 lg:grid-cols-[minmax(0,1fr)_320px]">
      <section aria-labelledby="home-heading" className="min-w-0 border-line sm:rounded-3xl sm:border">
        <h1 id="home-heading" className="sr-only">Home</h1>
        <div className="sticky top-14 z-20 border-b border-line bg-bg/85 px-4 py-3 backdrop-blur-xl sm:top-16 sm:rounded-t-3xl sm:px-5">
          <Tabs value={tab} onChange={setTab} items={[{ value: "for_you", label: "For you" }, { value: "following", label: "Following" }]} className="w-fit" />
        </div>
        {tab === "for_you" && <DailyDebateCard />}
        {status === "authed" && <div className="border-b border-line px-4 py-3 sm:px-5"><Composer /></div>}
        {tab === "following" && status === "authed" && <NewPostsBanner newest={q.data?.pages[0]?.items.find((i) => !i.reposted_by)?.created_at} />}
        {tab === "following" && status === "anon" ? (
          <div className="p-4"><Empty title="Follow people to fill this." body="Sign in and follow debaters to see their posts here." action={<Button href="/login?next=/home%3Ftab%3Dfollowing">Sign in</Button>} /></div>
        ) : (
          <PostList q={q} empty={tab === "following"
            ? <Empty title="Your timeline is quiet." body="Follow people from For you, the Arena or the leaderboard, and their posts land here." action={<Button variant="outline" onClick={() => setTab("for_you")}>See what&apos;s popular</Button>} />
            : <Empty title="Be the first to post." body="Share a hot take. Someone will disagree, and then you can settle it in a debate." action={<Button onClick={() => openCompose()}>Write a post</Button>} />} />
        )}
      </section>
      <aside className="hidden lg:block"><div className="sticky top-24"><Trends /></div></aside>
    </div>
  );
}

export function TagFeed({ tag }: { tag: string }) {
  const q = usePosts(["tag", tag], `/tags/${encodeURIComponent(tag)}`);
  return (
    <div className="mx-auto max-w-2xl sm:px-6">
      <div className="px-4 pt-8 sm:px-0"><PageTitle eyebrow="HASHTAG" title={`#${tag}`} /></div>
      <div className="border-line sm:rounded-3xl sm:border">
        <PostList q={q} empty={<Empty title={`No posts with #${tag} yet.`} body="Start the conversation." action={<Button onClick={() => openCompose()}>Write a post</Button>} />} />
      </div>
    </div>
  );
}

export function BookmarksView() {
  const { status, requireAuth } = useAuth();
  const q = usePosts(["bookmarks"], "/me/bookmarks", status === "authed");
  useEffect(() => {
    if (status === "anon") requireAuth("Sign in to see your bookmarks.");
  }, [status, requireAuth]);
  return (
    <div className="mx-auto max-w-2xl sm:px-6">
      <div className="px-4 pt-8 sm:px-0"><PageTitle eyebrow="SAVED" title="Bookmarks" /></div>
      <div className="border-line sm:rounded-3xl sm:border">
        <PostList q={q} empty={<Empty title="Nothing saved yet." body="Tap the bookmark on any post to keep it here. Only you can see your bookmarks." />} />
      </div>
    </div>
  );
}

function PostDebates({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["posts", "debates", id], queryFn: () => get<{ items: Card[] }>(`/posts/${id}/debates`) });
  if (!q.data?.items.length) return null;
  return (
    <section aria-labelledby={`debates-${id}`} className="border-b border-line px-4 py-4 sm:px-5">
      <h2 id={`debates-${id}`} className="mb-3 font-mono text-[11px] font-bold tracking-[0.18em] text-faint">SETTLED IN THE ARENA</h2>
      <div className="flex flex-col gap-3">{q.data.items.map((d) => <DebateCard key={d.id} d={d} />)}</div>
    </section>
  );
}

export function PostThread({ id }: { id: string }) {
  const { status } = useAuth();
  const q = useQuery({
    queryKey: ["posts", "thread", id, status],
    queryFn: () => get<{ post: PostView; ancestors: PostView[] }>(`/posts/${id}`),
    enabled: status !== "loading",
  });
  const replies = usePosts(["replies", id], `/posts/${id}/replies`, status !== "loading");
  if (q.isError) {
    const gone = q.error instanceof ApiError && q.error.status === 404;
    return <div className="mx-auto max-w-2xl px-4 py-16">{gone ? <Empty title="This post isn't available." body="It may have been deleted, or its author blocked you." action={<Button href="/home">Back home</Button>} /> : <ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} />}</div>;
  }
  return (
    <div className="mx-auto max-w-2xl sm:px-6 sm:pt-6">
      <div className="border-line sm:rounded-3xl sm:border">
        {!q.data ? <PostSkeleton /> : (
          <>
            {q.data.ancestors.map((a) => <PostCard key={a.id} p={a} />)}
            <PostCard key={q.data.post.id} p={q.data.post} linked={false} focus />
            {q.data.post.debates > 0 && <PostDebates id={q.data.post.id} />}
            {status === "authed" && (
              <div className="border-b border-line px-4 py-3 sm:px-5">
                <Composer replyTo={q.data.post} placeholder="Post your reply" />
              </div>
            )}
            <PostList q={replies} empty={<p className="py-6 text-center text-sm text-dim">No replies yet.</p>} />
          </>
        )}
      </div>
    </div>
  );
}
