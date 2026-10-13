"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { useToast } from "@/components/toast";
import { Avatar, Sheet, Spinner } from "@/components/ui";
import { errorMessage, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { compact, cx } from "@/lib/format";
import type { LinkPreview, Page, Poll, PostView, PublicUser } from "@/lib/types";

/** The ✓ shown next to Provok's official accounts. */
export function VerifiedBadge() {
  return (
    <span title="Official Provok account" aria-label="Official account" className="ml-1 inline-grid size-[15px] place-items-center rounded-full bg-text align-[-2px] text-bg">
      <svg viewBox="0 0 12 12" className="size-2.5" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M2.5 6.2 5 8.5l4.5-5" strokeLinecap="round" strokeLinejoin="round" /></svg>
    </span>
  );
}

// ── Link preview card ──────────────────────────────────────────────────────

export function LinkCard({ lp }: { lp: LinkPreview }) {
  return (
    <a href={lp.url} target="_blank" rel="noopener noreferrer nofollow ugc" onClick={(e) => e.stopPropagation()}
      className="mt-3 block overflow-hidden rounded-2xl border border-line transition hover:bg-surface-2/60">
      {lp.image && (
        // eslint-disable-next-line @next/next/no-img-element -- remote preview image chosen by the linked site
        <img src={lp.image} alt="" loading="lazy" referrerPolicy="no-referrer" className="aspect-[1.91/1] w-full bg-surface-2 object-cover" />
      )}
      <div className="px-4 py-3">
        <p className="text-[12px] text-faint">{lp.site}</p>
        <p className="line-clamp-2 text-[14.5px] font-semibold">{lp.title}</p>
        {lp.description && <p className="mt-0.5 line-clamp-2 text-[13px] text-dim">{lp.description}</p>}
      </div>
    </a>
  );
}

// ── Polls ──────────────────────────────────────────────────────────────────

function timeLeft(endsAt: string): string {
  const ms = new Date(endsAt).getTime() - Date.now();
  if (ms <= 0) return "Final results";
  const h = Math.floor(ms / 3_600_000);
  if (h >= 24) return `${Math.floor(h / 24)}d left`;
  if (h >= 1) return `${h}h left`;
  return `${Math.max(1, Math.floor(ms / 60_000))}m left`;
}

export function PollView({ p, onVoted, onDebate }: { p: PostView; onVoted: (fresh: PostView) => void; onDebate: () => void }) {
  const { requireAuth } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState<number | null>(null);
  const poll = p.poll as Poll;
  const showResults = poll.options.some((o) => o.votes !== null);
  const top = Math.max(0, ...poll.options.map((o) => o.votes ?? 0));

  const vote = async (i: number) => {
    if (!requireAuth("Sign in to vote.")) return;
    setBusy(i);
    try {
      onVoted(await post<PostView>(`/posts/${p.id}/vote`, { option: i }));
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };

  // A close poll is the perfect debate: offer to settle it once enough people have voted.
  const counts = poll.options.map((o) => o.votes ?? 0);
  const split = poll.total >= 4 && showResults && Math.max(...counts) / poll.total <= 0.65;

  return (
    <div className="mt-3 flex flex-col gap-2" onClick={(e) => e.stopPropagation()}>
      {poll.options.map((o, i) => {
        const pct = poll.total ? Math.round(((o.votes ?? 0) / poll.total) * 100) : 0;
        return showResults ? (
          <div key={i} className="relative overflow-hidden rounded-xl border border-line px-3.5 py-2 text-[14.5px]">
            <div className={cx("absolute inset-y-0 left-0", (o.votes ?? 0) === top && top > 0 ? "bg-text/20" : "bg-surface-2")} style={{ width: `${pct}%` }} aria-hidden />
            <div className="relative flex items-center gap-2">
              <span className={cx("flex-1", poll.viewer_vote === i && "font-semibold")}>{o.label}{poll.viewer_vote === i && " ✓"}</span>
              <span className="font-mono text-[13px] tabular">{pct}%</span>
            </div>
          </div>
        ) : (
          <button key={i} type="button" disabled={busy !== null || poll.closed} onClick={() => void vote(i)}
            className="flex items-center justify-center gap-2 rounded-full border border-line-strong px-4 py-2 text-[14.5px] font-semibold transition hover:bg-surface-2 disabled:opacity-60">
            {busy === i && <Spinner className="size-3.5" />}{o.label}
          </button>
        );
      })}
      <p className="text-[12.5px] text-faint">
        {compact(poll.total)} vote{poll.total === 1 ? "" : "s"} · {timeLeft(poll.ends_at)}
        {split && <> · <button type="button" onClick={onDebate} className="font-semibold text-text hover:underline">Close call. Debate it ⚔</button></>}
      </p>
    </div>
  );
}

// ── Who liked this ─────────────────────────────────────────────────────────

export function LikersSheet({ postId, open, onClose }: { postId: string; open: boolean; onClose: () => void }) {
  const q = useInfiniteQuery({
    queryKey: ["likers", postId],
    queryFn: ({ pageParam }) => get<Page<PublicUser>>(`/posts/${postId}/likes${pageParam ? `?cursor=${encodeURIComponent(pageParam)}` : ""}`),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: open,
  });
  const users = q.data?.pages.flatMap((pg) => pg.items) ?? [];
  return (
    <Sheet open={open} onClose={onClose} title="Liked by">
      {q.isLoading && <Spinner className="size-5" />}
      {q.isError && <p className="text-sm text-danger">{errorMessage(q.error)}</p>}
      {!q.isLoading && users.length === 0 && <p className="text-sm text-dim">No likes yet.</p>}
      <ul className="flex flex-col gap-1">
        {users.map((u) => (
          <li key={u.username}>
            <Link href={`/u/${u.username}`} onClick={onClose} className="flex items-center gap-3 rounded-xl px-2 py-2 hover:bg-surface-2">
              <Avatar user={u} size={36} />
              <span className="min-w-0">
                <span className="block truncate font-semibold">{u.display_name}{u.verified && <VerifiedBadge />}</span>
                <span className="block truncate text-[13px] text-faint">@{u.username}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {q.hasNextPage && <button type="button" onClick={() => void q.fetchNextPage()} className="mt-2 text-sm font-semibold hover:underline">Show more</button>}
    </Sheet>
  );
}
