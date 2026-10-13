"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { openCompose } from "@/components/posts/compose-store";
import { ChallengeSheet, FactCheckNote, Translate, useFactCheck } from "@/components/posts/post-ai";
import { LikersSheet, LinkCard, PollView, VerifiedBadge } from "@/components/posts/post-extras";
import { PostText } from "@/components/posts/post-text";
import { ReportButton } from "@/components/report";
import { useShare } from "@/components/share";
import { useToast } from "@/components/toast";
import { Avatar } from "@/components/ui";
import { api, del, errorMessage, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { compact, cx, timeAgo } from "@/lib/format";
import type { PostMedia, PostView } from "@/lib/types";

const isPost = (q: PostView["quote"]): q is PostView => !!q && !("unavailable" in q);

// ── Media ──────────────────────────────────────────────────────────────────

function MediaGrid({ media }: { media: PostMedia[] }) {
  if (media.length === 0) return null;
  const one = media.length === 1;
  return (
    <div className={cx("mt-3 grid gap-1 overflow-hidden rounded-2xl border border-line", one ? "grid-cols-1" : "grid-cols-2",
      media.length === 3 && "grid-rows-2")}>
      {media.map((m, i) => (
        <a key={m.id} href={m.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
          className={cx("block bg-surface-2", media.length === 3 && i === 0 && "row-span-2")}>
          {/* eslint-disable-next-line @next/next/no-img-element -- user uploads served from the media bucket */}
          <img src={m.url} alt={m.alt ?? ""} width={m.width} height={m.height} loading="lazy"
            className={cx("size-full object-cover", one ? "max-h-[520px]" : "aspect-square")} />
        </a>
      ))}
    </div>
  );
}

// ── Action buttons ─────────────────────────────────────────────────────────

function Action({ label, count, active, tone, onClick, children }: {
  label: string; count?: number; active?: boolean; tone?: "like" | "repost"; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button type="button" aria-label={label} aria-pressed={active}
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      className={cx("group flex items-center gap-1.5 rounded-full py-1.5 pl-1.5 pr-2 text-[13px] tabular transition",
        active ? (tone === "like" ? "text-live" : tone === "repost" ? "text-ok" : "text-text") : "text-faint hover:text-text")}>
      <span className="grid size-7 place-items-center rounded-full transition group-hover:bg-surface-2">{children}</span>
      {count !== undefined && count > 0 && <span>{compact(count)}</span>}
    </button>
  );
}

const I = {
  reply: <svg viewBox="0 0 20 20" className="size-[17px]" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden><path d="M4 4h12v9H9l-4 3v-3H4z" strokeLinejoin="round" /></svg>,
  repost: <svg viewBox="0 0 20 20" className="size-[17px]" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden><path d="M5 8V6h9l-2-2M15 12v2H6l2 2" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  like: (on: boolean) => <svg viewBox="0 0 20 20" className="size-[17px]" fill={on ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.6" aria-hidden><path d="M10 16.5S3.5 12.6 3.5 8A3.5 3.5 0 0 1 10 6.2 3.5 3.5 0 0 1 16.5 8c0 4.6-6.5 8.5-6.5 8.5z" strokeLinejoin="round" /></svg>,
  bookmark: (on: boolean) => <svg viewBox="0 0 20 20" className="size-[17px]" fill={on ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.6" aria-hidden><path d="M5.5 3.5h9v13L10 13.5l-4.5 3z" strokeLinejoin="round" /></svg>,
  challenge: <svg viewBox="0 0 20 20" className="size-[17px]" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden><path d="M4 16 15.5 4.5M15.5 4.5V8M15.5 4.5H12M16 16 4.5 4.5M4.5 4.5V8M4.5 4.5H8" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  share: <svg viewBox="0 0 20 20" className="size-[17px]" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden><path d="M10 13V3.5M6.5 7 10 3.5 13.5 7M4 11v5h12v-5" strokeLinecap="round" strokeLinejoin="round" /></svg>,
  more: <svg viewBox="0 0 20 20" className="size-[17px]" fill="currentColor" aria-hidden><circle cx="4.5" cy="10" r="1.5" /><circle cx="10" cy="10" r="1.5" /><circle cx="15.5" cy="10" r="1.5" /></svg>,
};

/** Small popover menu that closes on outside click and Escape. */
function Menu({ trigger, children }: { trigger: (open: () => void) => React.ReactNode; children: (close: () => void) => React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={ref} className="relative" onClick={(e) => e.stopPropagation()}>
      {trigger(() => setOpen((o) => !o))}
      {open && (
        <div role="menu" className="absolute right-0 top-9 z-30 w-52 rounded-2xl border border-line bg-surface p-1.5 shadow-2xl">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

const menuItem = "block w-full rounded-xl px-3 py-2 text-left text-sm hover:bg-surface-2";

// ── Card ───────────────────────────────────────────────────────────────────

export function PostCard({ p, linked = true, focus = false, embedded = false, showPinned = false }: {
  p: PostView; linked?: boolean; focus?: boolean; embedded?: boolean; showPinned?: boolean;
}) {
  const { requireAuth } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const share = useShare();
  const qc = useQueryClient();
  // Local, optimistic copy of the counters and the viewer's reactions; the server's answer replaces it.
  const [view, setView] = useState(p);
  const [removed, setRemoved] = useState(false);
  const [challenging, setChallenging] = useState<false | "invite" | "open">(false);
  const [likersOpen, setLikersOpen] = useState(false);
  const factcheck = useFactCheck(view);
  const author = view.author;
  const href = `/p/${view.id}`;

  const react = async (kind: "like" | "repost" | "bookmark", on: boolean) => {
    if (!requireAuth("Sign in to join the conversation.")) return;
    const key = { like: "liked", repost: "reposted", bookmark: "bookmarked" } as const;
    const counter = { like: "likes", repost: "reposts", bookmark: null } as const;
    const before = view;
    setView((v) => ({
      ...v,
      viewer: { ...v.viewer, [key[kind]]: on },
      counts: counter[kind] ? { ...v.counts, [counter[kind]!]: Math.max(0, v.counts[counter[kind]!] + (on ? 1 : -1)) } : v.counts,
    }));
    try {
      const fresh = on ? await post<PostView>(`/posts/${view.id}/${kind}`) : await del<PostView>(`/posts/${view.id}/${kind}`);
      setView((v) => ({ ...fresh, feed_id: v.feed_id, reposted_by: v.reposted_by }));
      if (kind === "bookmark") {
        toast(on ? "Saved to bookmarks." : "Removed from bookmarks.", "success");
        void qc.invalidateQueries({ queryKey: ["posts", "bookmarks"] });
      }
    } catch (e) {
      setView(before);
      toast(errorMessage(e), "error");
    }
  };

  const pin = async (on: boolean) => {
    try {
      if (on) await post(`/posts/${view.id}/pin`);
      else await del(`/posts/${view.id}/pin`);
      setView((v) => ({ ...v, pinned: on }));
      toast(on ? "Pinned to your profile." : "Unpinned.", "success");
      void qc.invalidateQueries({ queryKey: ["profile"] });
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  const relationship = async (kind: "mute" | "block") => {
    if (!author || !requireAuth("Sign in first.")) return;
    try {
      await api(`/users/${author.username}/${kind}`, { method: "POST" });
      toast(kind === "mute" ? `Muted @${author.username}. You won't see their posts.` : `Blocked @${author.username}.`, "success");
      void qc.invalidateQueries({ queryKey: ["posts"] });
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  const remove = async () => {
    if (!window.confirm("Delete this post? This can't be undone.")) return;
    try {
      await del(`/posts/${view.id}`);
      setRemoved(true);
      toast("Post deleted.", "success");
      void qc.invalidateQueries({ queryKey: ["posts"] });
      if (focus) router.push("/home");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  if (removed) return null;
  const open = (e: React.MouseEvent) => {
    if (!linked || (e.target as HTMLElement).closest("a, button, [role='menu']")) return;
    if (window.getSelection()?.toString()) return; // selecting text isn't a click
    router.push(href);
  };

  return (
    <article onClick={open} aria-labelledby={`post-${view.feed_id}-author`}
      className={cx("px-4 pt-3 transition sm:px-5", embedded ? "pb-3" : "border-b border-line pb-1",
        linked && "cursor-pointer hover:bg-surface/60")}>
      {showPinned && view.pinned && (
        <p className="mb-1 pl-[52px] text-[12.5px] font-semibold text-faint">📌 Pinned</p>
      )}
      {view.reposted_by && (
        <p className="mb-1 flex items-center gap-1.5 pl-[52px] text-[12.5px] font-semibold text-faint">
          {I.repost}
          <Link href={`/u/${view.reposted_by.username}`} className="hover:underline">{view.reposted_by.display_name}</Link> reposted
        </p>
      )}
      <div className="flex gap-3">
        <Link href={author ? `/u/${author.username}` : "#"} className="shrink-0" aria-hidden tabIndex={-1}>
          <Avatar user={author} size={40} />
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-1">
            <p id={`post-${view.feed_id}-author`} className="min-w-0 flex-1 truncate text-[14.5px]">
              {author ? (
                <Link href={`/u/${author.username}`} className="font-semibold hover:underline">{author.display_name}</Link>
              ) : <span className="font-semibold">Deleted user</span>}
              {author?.verified && <VerifiedBadge />}
              {author && <span className="text-faint"> @{author.username}</span>}
              {author && (author.debates ?? 0) > 0 && author.rating !== null && (
                <span title={`Debate rating ${author.rating} from ${author.debates} debate${author.debates === 1 ? "" : "s"}`}
                  className="ml-1.5 rounded-full border border-line px-1.5 py-px align-[1px] font-mono text-[10.5px] text-dim">◆ {author.rating}</span>
              )}
              <span className="text-faint"> · </span>
              <Link href={href} className="text-faint hover:underline"><time dateTime={view.created_at}>{timeAgo(view.created_at)}</time></Link>
            </p>
            {!embedded && <Menu trigger={(toggle) => (
              <button type="button" aria-label="More options" onClick={toggle} className="-mr-1.5 -mt-1 grid size-8 place-items-center rounded-full text-faint hover:bg-surface-2 hover:text-text">{I.more}</button>
            )}>
              {(close) => view.viewer.is_author ? (
                <>
                  {!view.reply_to && (
                    <button role="menuitem" className={menuItem} onClick={() => { close(); void pin(!view.pinned); }}>
                      {view.pinned ? "Unpin from profile" : "Pin to your profile"}
                    </button>
                  )}
                  <button role="menuitem" className={cx(menuItem, "text-danger")} onClick={() => { close(); void remove(); }}>Delete post</button>
                </>
              ) : (
                <>
                  {view.text && !factcheck.fc && (
                    <button role="menuitem" className={menuItem} onClick={() => { close(); void factcheck.request(); }}>Fact-check with AI</button>
                  )}
                  <div className={menuItem}><ReportButton targetType="post" targetId={view.id} label="Report post" /></div>
                  {author && <button role="menuitem" className={menuItem} onClick={() => { close(); void relationship("mute"); }}>Mute @{author.username}</button>}
                  {author && <button role="menuitem" className={cx(menuItem, "text-danger")} onClick={() => { close(); void relationship("block"); }}>Block @{author.username}</button>}
                </>
              )}
            </Menu>}
          </div>
          {view.reply_to?.username && !focus && (
            <p className="text-[13px] text-faint">Replying to <Link href={`/u/${view.reply_to.username}`} className="text-dim hover:underline">@{view.reply_to.username}</Link></p>
          )}
          {view.text && <PostText text={view.text} className={cx("mt-0.5 whitespace-pre-wrap break-words leading-relaxed", focus ? "text-[18px]" : "text-[15px]")} />}
          {!embedded && <Translate p={view} />}
          {!embedded && factcheck.fc && <FactCheckNote fc={factcheck.fc} />}
          {view.poll && !embedded && <PollView p={view} onVoted={(fresh) => setView((v) => ({ ...fresh, feed_id: v.feed_id, reposted_by: v.reposted_by }))}
            onDebate={() => requireAuth("Sign in to start a debate.") && setChallenging("open")} />}
          <MediaGrid media={view.media} />
          {view.link_preview && view.media.length === 0 && !view.quote && <LinkCard lp={view.link_preview} />}
          {!embedded && view.quote && (isPost(view.quote) ? (
            <div className="mt-3 overflow-hidden rounded-2xl border border-line" onClick={(e) => e.stopPropagation()}>
              <PostCard p={view.quote} embedded />
            </div>
          ) : (
            <p className="mt-3 rounded-2xl border border-line px-4 py-3 text-sm text-faint">This post is unavailable.</p>
          ))}
          {!embedded && <div className="-ml-1.5 mt-1 flex items-center justify-between pr-2 sm:max-w-md">
            <Action label="Reply" count={view.counts.replies} onClick={() => requireAuth("Sign in to reply.") && openCompose({ replyTo: view })}>{I.reply}</Action>
            <Menu trigger={(toggle) => (
              <Action label={view.viewer.reposted ? "Undo repost" : "Repost or quote"} count={view.counts.reposts + view.counts.quotes}
                active={view.viewer.reposted} tone="repost" onClick={toggle}>{I.repost}</Action>
            )}>
              {(close) => (
                <>
                  <button role="menuitem" className={menuItem} onClick={() => { close(); void react("repost", !view.viewer.reposted); }}>
                    {view.viewer.reposted ? "Undo repost" : "Repost"}
                  </button>
                  <button role="menuitem" className={menuItem} onClick={() => { close(); if (requireAuth("Sign in to quote.")) openCompose({ quote: view }); }}>Quote</button>
                </>
              )}
            </Menu>
            <Action label={view.viewer.liked ? "Unlike" : "Like"} count={view.counts.likes} active={view.viewer.liked} tone="like"
              onClick={() => void react("like", !view.viewer.liked)}>{I.like(view.viewer.liked)}</Action>
            {view.viewer.is_author ? (
              view.debates > 0 && <Link href={href} onClick={(e) => e.stopPropagation()} className="flex items-center gap-1.5 py-1.5 pl-1.5 pr-2 text-[13px] text-faint hover:text-text" title="Debates started from this post">
                <span className="grid size-7 place-items-center">{I.challenge}</span>{view.debates}
              </Link>
            ) : (
              <Action label="Challenge to a debate" count={view.debates} onClick={() => requireAuth("Sign in to challenge.") && setChallenging("invite")}>{I.challenge}</Action>
            )}
            <Action label={view.viewer.bookmarked ? "Remove bookmark" : "Bookmark"} active={view.viewer.bookmarked}
              onClick={() => void react("bookmark", !view.viewer.bookmarked)}>{I.bookmark(view.viewer.bookmarked)}</Action>
            <Action label="Share" onClick={() => void share({ title: `${author?.display_name ?? "Someone"} on Provok`, text: (view.text ?? "").slice(0, 120), path: href, kind: "post" })}>
              {I.share}
            </Action>
          </div>}
          {focus && (view.counts.likes > 0 || view.counts.views > 0) && (
            <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1 border-t border-line py-2.5 text-[14px] text-dim">
              {view.counts.likes > 0 && (
                <button type="button" onClick={() => setLikersOpen(true)} className="hover:underline">
                  <b className="text-text">{compact(view.counts.likes)}</b> Like{view.counts.likes === 1 ? "" : "s"}
                </button>
              )}
              {view.counts.reposts > 0 && <span><b className="text-text">{compact(view.counts.reposts)}</b> Repost{view.counts.reposts === 1 ? "" : "s"}</span>}
              <span><b className="text-text">{compact(view.counts.views)}</b> View{view.counts.views === 1 ? "" : "s"}</span>
            </p>
          )}
          {challenging && <ChallengeSheet p={view} mode={challenging} open onClose={() => setChallenging(false)} />}
          {likersOpen && <LikersSheet postId={view.id} open={likersOpen} onClose={() => setLikersOpen(false)} />}
        </div>
      </div>
    </article>
  );
}

export function PostSkeleton() {
  return (
    <div className="flex gap-3 border-b border-line px-4 py-4 sm:px-5" aria-hidden>
      <div className="skeleton size-10 shrink-0 rounded-full" />
      <div className="flex flex-1 flex-col gap-2">
        <div className="skeleton h-3.5 w-40" />
        <div className="skeleton h-3.5 w-full" />
        <div className="skeleton h-3.5 w-2/3" />
      </div>
    </div>
  );
}
