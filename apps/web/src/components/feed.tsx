"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";

import { CardSkeleton, DebateCard } from "@/components/debate-card";
import { Button, Empty, ErrorBlock, Tabs } from "@/components/ui";
import { errorMessage, get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { DebateCard as Card, Page } from "@/lib/types";

export type FeedTab = "live" | "trending" | "ava" | "challenges";
const TABS: { value: FeedTab; label: string }[] = [
  { value: "live", label: "Live" },
  { value: "trending", label: "Trending" },
  { value: "ava", label: "AI vs AI" },
  { value: "challenges", label: "Open Challenges" },
];

export function useFeed(tab: string, category?: string) {
  return useInfiniteQuery({
    queryKey: ["feed", tab, category ?? ""],
    queryFn: ({ pageParam, signal }) =>
      get<Page<Card>>(`/debates/feed?tab=${tab}&limit=12${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}${category ? `&category=${category}` : ""}`, { signal }),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    refetchInterval: tab === "live" ? 20_000 : false,
  });
}

function InfiniteSentinel({ onVisible, disabled }: { onVisible: () => void; disabled: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (disabled || !ref.current) return;
    const io = new IntersectionObserver((e) => e[0]?.isIntersecting && onVisible(), { rootMargin: "600px" });
    io.observe(ref.current);
    return () => io.disconnect();
  }, [onVisible, disabled]);
  return <div ref={ref} aria-hidden className="h-px" />;
}

export function Feed() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = (TABS.some((t) => t.value === params.get("tab")) ? params.get("tab") : "live") as FeedTab;
  const { requireAuth } = useAuth();
  const q = useFeed(tab);
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const setTab = (t: FeedTab) => router.replace(t === "live" ? "/" : `/?tab=${t}`, { scroll: false });
  const start = () => requireAuth("Sign in to start a debate.") && router.push("/new");

  const empty = !q.isLoading && !q.isError && items.length === 0;
  const emptyCopy: Record<FeedTab, { title: string; body: string }> = {
    live: { title: "Nobody's on stage right now.", body: "Be the first. Start a debate against an AI in under a minute." },
    trending: { title: "Nothing trending yet.", body: "Votes make debates trend. Start one and share it." },
    ava: { title: "No AI showdowns yet.", body: "Pit two models against each other and watch them go." },
    challenges: { title: "No open challenges.", body: "Post a question and take a side — someone will take the other." },
  };

  return (
    <section aria-labelledby="feed-heading">
      {/* Cards title their questions with <h3>; this keeps the outline h1 → h2 → h3 for screen readers. */}
      <h2 id="feed-heading" className="sr-only">Debates</h2>
      <div className="sticky top-14 z-30 -mx-4 bg-bg/85 px-4 py-3 backdrop-blur-xl sm:top-16 sm:mx-0 sm:px-0">
        <Tabs value={tab} onChange={setTab} items={TABS} className="w-fit max-w-full" />
      </div>

      {q.isError && <ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} />}
      {empty && (
        <Empty title={emptyCopy[tab].title} body={emptyCopy[tab].body}
          action={<Button variant="for" onClick={start}>Start a debate →</Button>} />
      )}

      {/* Mobile: one debate per screen, vertical swipe. */}
      <div className="no-scrollbar -mx-4 h-[calc(100dvh-56px-64px-64px-env(safe-area-inset-bottom))] snap-y snap-mandatory overflow-y-auto md:hidden">
        {q.isLoading && <div className="h-full px-4 py-2"><CardSkeleton variant="hero" /></div>}
        {items.map((d) => (
          <div key={d.id} className="h-full snap-start snap-always border-b border-line">
            <DebateCard d={d} variant="full" />
          </div>
        ))}
        <InfiniteSentinel onVisible={() => q.fetchNextPage()} disabled={!q.hasNextPage || q.isFetchingNextPage} />
      </div>

      {/* Desktop: hero + grid. */}
      <div className="hidden md:block">
        {q.isLoading ? (
          <div className="grid gap-5 lg:grid-cols-3">
            <div className="lg:col-span-2"><CardSkeleton variant="hero" /></div><CardSkeleton /><CardSkeleton /><CardSkeleton /><CardSkeleton />
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-3">
            {items.map((d, i) => (
              <div key={d.id} className={i === 0 ? "lg:col-span-2 lg:row-span-1" : ""}>
                <DebateCard d={d} variant={i === 0 ? "hero" : "grid"} />
              </div>
            ))}
          </div>
        )}
        <InfiniteSentinel onVisible={() => q.fetchNextPage()} disabled={!q.hasNextPage || q.isFetchingNextPage} />
        {q.isFetchingNextPage && <div className="mt-5 grid gap-5 lg:grid-cols-3"><CardSkeleton /><CardSkeleton /><CardSkeleton /></div>}
      </div>
    </section>
  );
}

export function HomeHero() {
  const { status, requireAuth } = useAuth();
  const router = useRouter();
  if (status === "authed") return null;
  return (
    <section className="stage-duel grain relative -mx-4 mb-6 overflow-hidden border-b border-line px-4 pb-10 pt-12 sm:mx-0 sm:mb-10 sm:rounded-[2rem] sm:border sm:px-10 sm:py-16">
      <p className="font-mono text-[11px] font-bold tracking-[0.2em] text-faint">THE ARENA FOR IDEAS</p>
      <h1 className="font-display mt-4 max-w-4xl text-[clamp(2.6rem,8vw,5.6rem)] font-extrabold leading-[0.9]">
        Ask anything.<br />
        Pick your <span className="text-for">corners</span>.<br />
        Let the <span className="text-against">verdict</span> land.
      </h1>
      <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-dim sm:text-base">
        Debate humans or AI swarms in four sharp rounds. The crowd votes every round. An impartial AI judge
        checks every source and explains who won — and why.
      </p>
      <div className="mt-7 flex flex-wrap gap-3">
        <Button size="lg" variant="for" onClick={() => requireAuth("Create a free account to start debating — your first 3 AI debates are on us.") && router.push("/new?quick=1")}>
          Debate an AI now — free
        </Button>
        <Button size="lg" variant="outline" href="/?tab=ava">Watch AI vs AI</Button>
      </div>
    </section>
  );
}
