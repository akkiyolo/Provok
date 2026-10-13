"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { VerifiedBadge } from "@/components/posts/post-extras";
import { useToast } from "@/components/toast";
import { Avatar, Button, Empty, ErrorBlock, PageTitle, Spinner, Tabs } from "@/components/ui";
import { ApiError, errorMessage, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cx, timeAgo } from "@/lib/format";
import type { Conversation, DirectMessage, Page, PublicUser } from "@/lib/types";

/** Unread conversations, for the nav badge (requests from strangers don't count). */
export function useUnreadMessages() {
  const { status } = useAuth();
  const q = useQuery({
    queryKey: ["dm-unread"],
    queryFn: () => get<{ unread: number }>("/conversations/unread"),
    enabled: status === "authed",
    refetchInterval: 30_000,
  });
  return q.data?.unread ?? 0;
}

export function MessagesView() {
  const { status, requireAuth } = useAuth();
  const [tab, setTab] = useState<"inbox" | "requests">("inbox");
  const q = useQuery({
    queryKey: ["conversations"],
    queryFn: () => get<{ items: Conversation[] }>("/conversations"),
    enabled: status === "authed",
    refetchInterval: 15_000,
  });
  useEffect(() => {
    if (status === "anon") requireAuth("Sign in to see your messages.");
  }, [status, requireAuth]);
  const all = q.data?.items ?? [];
  const requests = all.filter((c) => c.request);
  const shown = tab === "requests" ? requests : all.filter((c) => !c.request);
  return (
    <div className="mx-auto max-w-2xl px-4 pt-8 sm:px-6">
      <PageTitle eyebrow="DIRECT" title="Messages" />
      <Tabs value={tab} onChange={setTab} className="mb-4 w-fit"
        items={[{ value: "inbox", label: "Inbox" }, { value: "requests", label: `Requests${requests.length ? ` (${requests.length})` : ""}` }]} />
      {q.isError && <ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} />}
      {q.isLoading && <div className="flex flex-col gap-2">{[0, 1, 2].map((i) => <div key={i} className="skeleton h-16" />)}</div>}
      {q.data && shown.length === 0 && (
        <Empty title={tab === "requests" ? "No message requests." : "No messages yet."}
          body={tab === "requests" ? "Messages from people you don't follow wait here until you reply." : "Open someone's profile and tap Message to start a conversation."} />
      )}
      <ul className="flex flex-col gap-1">
        {shown.map((c) => (
          <li key={c.id}>
            <Link href={`/messages/${c.id}`} className={cx("flex items-center gap-3 rounded-2xl border px-3 py-3 transition hover:border-line-strong", c.unread ? "border-line-strong bg-surface" : "border-transparent")}>
              <Avatar user={c.with} size={44} />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-2">
                  <span className="truncate font-semibold">{c.with.display_name}{c.with.verified && <VerifiedBadge />}</span>
                  <span className="truncate text-[12.5px] text-faint">@{c.with.username}</span>
                  <span className="ml-auto shrink-0 text-[12px] text-faint">{timeAgo(c.last_message_at)}</span>
                </span>
                <span className={cx("block truncate text-[14px]", c.unread ? "font-semibold text-text" : "text-dim")}>
                  {c.last?.mine && "You: "}{c.last?.text}
                </span>
              </span>
              {c.unread && <span className="size-2.5 shrink-0 rounded-full bg-text" aria-label="Unread" />}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ThreadView({ id }: { id: string }) {
  const { status, requireAuth } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const q = useInfiniteQuery({
    queryKey: ["dm", id],
    queryFn: ({ pageParam }) => get<Page<DirectMessage> & { with: PublicUser }>(`/conversations/${id}${pageParam ? `?cursor=${encodeURIComponent(pageParam)}` : ""}`),
    initialPageParam: "",
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    enabled: status === "authed",
    refetchInterval: 5_000, // new messages while the thread is open
  });
  useEffect(() => {
    if (status === "anon") requireAuth("Sign in to see your messages.");
  }, [status, requireAuth]);
  const other = q.data?.pages[0]?.with;
  const msgs = (q.data?.pages.flatMap((pg) => pg.items) ?? []).slice().reverse(); // oldest first on screen
  const newest = msgs[msgs.length - 1]?.id;
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
    void qc.invalidateQueries({ queryKey: ["dm-unread"] });
  }, [newest, qc]);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim()) return;
    setSending(true);
    try {
      await post<DirectMessage>(`/conversations/${id}/messages`, { text });
      setText("");
      await qc.invalidateQueries({ queryKey: ["dm", id] });
      void qc.invalidateQueries({ queryKey: ["conversations"] });
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setSending(false);
    }
  };

  if (q.isError) {
    const gone = q.error instanceof ApiError && q.error.status === 404;
    return <div className="mx-auto max-w-2xl px-4 py-16">{gone ? <Empty title="Conversation not found." action={<Button href="/messages">All messages</Button>} /> : <ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} />}</div>;
  }
  return (
    <div className="mx-auto flex h-[calc(100dvh-56px-64px-env(safe-area-inset-bottom))] max-w-2xl flex-col sm:h-[calc(100dvh-64px)] sm:px-6">
      <header className="flex items-center gap-3 border-b border-line px-4 py-3">
        <Link href="/messages" aria-label="All messages" className="grid size-9 place-items-center rounded-full hover:bg-surface-2">←</Link>
        {other && (
          <Link href={`/u/${other.username}`} className="flex min-w-0 items-center gap-2.5">
            <Avatar user={other} size={36} />
            <span className="min-w-0">
              <span className="block truncate font-semibold">{other.display_name}{other.verified && <VerifiedBadge />}</span>
              <span className="block truncate text-[12.5px] text-faint">@{other.username}</span>
            </span>
          </Link>
        )}
      </header>
      <div className="flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
        {q.hasNextPage && (
          <div className="mb-3 text-center">
            <button type="button" onClick={() => void q.fetchNextPage()} className="text-sm font-semibold hover:underline">
              {q.isFetchingNextPage ? "Loading…" : "Load earlier messages"}
            </button>
          </div>
        )}
        {q.isLoading && <div className="grid place-items-center py-10"><Spinner className="size-6" /></div>}
        {q.data && msgs.length === 0 && <p className="py-10 text-center text-sm text-dim">Say hello 👋</p>}
        <ul className="flex flex-col gap-1.5">
          {msgs.map((m) => (
            <li key={m.id} className={cx("flex", m.mine ? "justify-end" : "justify-start")}>
              <span title={new Date(m.created_at).toLocaleString()}
                className={cx("max-w-[80%] whitespace-pre-wrap break-words rounded-3xl px-4 py-2 text-[15px] leading-relaxed",
                  m.mine ? "rounded-br-lg bg-text text-bg" : "rounded-bl-lg border border-line bg-surface")}>
                {m.text}
              </span>
            </li>
          ))}
        </ul>
        <div ref={bottom} />
      </div>
      <form onSubmit={send} className="flex items-end gap-2 border-t border-line px-4 py-3">
        <label htmlFor="dm-text" className="sr-only">Message</label>
        <textarea id="dm-text" value={text} onChange={(e) => setText(e.target.value)} rows={1} maxLength={1000} placeholder="Write a message"
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(e); } }}
          className="max-h-32 min-h-11 flex-1 resize-none rounded-3xl border border-line bg-surface px-4 py-2.5 text-[15px] outline-none focus:border-text/50" />
        <Button type="submit" loading={sending} disabled={!text.trim()}>Send</Button>
      </form>
    </div>
  );
}
