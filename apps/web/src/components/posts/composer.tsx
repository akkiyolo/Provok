"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { closeCompose, useCompose } from "@/components/posts/compose-store";
import { useToast } from "@/components/toast";
import { Avatar, Button, Sheet, Spinner } from "@/components/ui";
import { api, errorMessage, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cx } from "@/lib/format";
import type { PostView } from "@/lib/types";

export const POST_MAX_CHARS = 500;
const MAX_MEDIA = 4;

interface Upload {
  key: string;
  preview: string;
  id?: string;
  error?: string;
}

/** Character counter ring: fills as you type, turns red past the limit. */
function CharRing({ count }: { count: number }) {
  const left = POST_MAX_CHARS - count;
  const r = 9;
  const c = 2 * Math.PI * r;
  const pct = Math.min(1, count / POST_MAX_CHARS);
  const tone = left < 0 ? "var(--danger)" : left <= 20 ? "var(--win)" : "var(--text-dim)";
  return (
    <span className="flex items-center gap-1.5" aria-live="polite">
      {left <= 20 && <span className={cx("font-mono text-[12px]", left < 0 ? "text-danger" : "text-dim")}>{left}</span>}
      <svg viewBox="0 0 24 24" className="size-6 -rotate-90" aria-hidden>
        <circle cx="12" cy="12" r={r} fill="none" stroke="var(--line)" strokeWidth="2.5" />
        <circle cx="12" cy="12" r={r} fill="none" stroke={tone} strokeWidth="2.5" strokeDasharray={c} strokeDashoffset={c * (1 - pct)} strokeLinecap="round" />
      </svg>
    </span>
  );
}

export function Composer({ replyTo, quote, onPosted, autoFocus, placeholder }: {
  replyTo?: PostView; quote?: PostView; onPosted?: (p: PostView) => void; autoFocus?: boolean; placeholder?: string;
}) {
  const { user, requireAuth } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [uploads, setUploads] = useState<Upload[]>([]);
  const [busy, setBusy] = useState(false);
  const [poll, setPoll] = useState<string[] | null>(null);
  const [pollHours, setPollHours] = useState(24);
  const fileRef = useRef<HTMLInputElement>(null);
  const uploading = uploads.some((u) => !u.id && !u.error);
  const count = [...text.trim()].length;
  const pollOk = !poll || (count > 0 && poll.filter((o) => o.trim()).length >= 2 && poll.every((o) => o.trim().length <= 40));
  const canPost = !busy && !uploading && pollOk && count <= POST_MAX_CHARS && (count > 0 || uploads.some((u) => u.id));

  const addFiles = (files: FileList | null) => {
    if (!files?.length || !requireAuth("Sign in to post.")) return;
    const room = MAX_MEDIA - uploads.length;
    const picked = Array.from(files).slice(0, room);
    if (files.length > room) toast(`You can add up to ${MAX_MEDIA} photos.`, "info");
    for (const file of picked) {
      const key = `${file.name}-${file.size}-${Math.random()}`;
      setUploads((u) => [...u, { key, preview: URL.createObjectURL(file) }]);
      const form = new FormData();
      form.append("file", file);
      void api<{ id: string }>("/media", { method: "POST", form })
        .then((r) => setUploads((u) => u.map((x) => (x.key === key ? { ...x, id: r.id } : x))))
        .catch((e) => {
          toast(errorMessage(e), "error");
          setUploads((u) => u.map((x) => (x.key === key ? { ...x, error: errorMessage(e) } : x)));
        });
    }
  };

  const remove = (key: string) => setUploads((u) => {
    const gone = u.find((x) => x.key === key);
    if (gone) URL.revokeObjectURL(gone.preview);
    return u.filter((x) => x.key !== key);
  });

  const submit = async () => {
    if (!requireAuth("Sign in to post.") || !canPost) return;
    setBusy(true);
    try {
      const created = await post<PostView>("/posts", {
        text: text.trim() || null,
        media_ids: uploads.filter((u) => u.id).map((u) => u.id),
        reply_to_id: replyTo?.id ?? null,
        quote_of_id: quote?.id ?? null,
        poll: poll ? poll.map((o) => o.trim()).filter(Boolean) : null,
        poll_hours: poll ? pollHours : null,
      });
      uploads.forEach((u) => URL.revokeObjectURL(u.preview));
      setText("");
      setUploads([]);
      setPoll(null);
      await qc.invalidateQueries({ queryKey: ["posts"] });
      toast(replyTo ? "Reply posted." : "Posted.", "success");
      onPosted?.(created);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex gap-3">
      <Avatar user={user} size={40} />
      <div className="min-w-0 flex-1">
        <label htmlFor={`compose-${replyTo?.id ?? quote?.id ?? "new"}`} className="sr-only">
          {replyTo ? "Write your reply" : "Write a post"}
        </label>
        <textarea
          id={`compose-${replyTo?.id ?? quote?.id ?? "new"}`}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => requireAuth("Sign in to post.")}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void submit(); }}
          autoFocus={autoFocus}
          rows={replyTo ? 2 : 3}
          placeholder={placeholder ?? (replyTo ? `Reply to @${replyTo.author?.username ?? "post"}…` : quote ? "Add your take…" : "What's your take?")}
          className="w-full resize-none bg-transparent pt-2 text-[16px] leading-relaxed outline-none placeholder:text-faint"
        />
        {uploads.length > 0 && (
          <div className={cx("mt-2 grid gap-2", uploads.length > 1 ? "grid-cols-2" : "grid-cols-1")}>
            {uploads.map((u) => (
              <div key={u.key} className="relative overflow-hidden rounded-2xl border border-line">
                {/* eslint-disable-next-line @next/next/no-img-element -- local blob preview */}
                <img src={u.preview} alt="" className={cx("w-full object-cover", uploads.length > 1 ? "aspect-square" : "max-h-80")} />
                {!u.id && !u.error && <span className="absolute inset-0 grid place-items-center bg-black/40"><Spinner className="size-6" /></span>}
                {u.error && <span className="absolute inset-x-0 bottom-0 bg-danger/90 px-2 py-1 text-[12px] text-white">Upload failed</span>}
                <button type="button" onClick={() => remove(u.key)} aria-label="Remove photo"
                  className="absolute right-2 top-2 grid size-7 place-items-center rounded-full bg-black/70 text-white hover:bg-black">
                  <svg viewBox="0 0 20 20" className="size-3.5" fill="currentColor" aria-hidden><path d="M5.3 4.3 10 9l4.7-4.7 1 1L11 10l4.7 4.7-1 1L10 11l-4.7 4.7-1-1L9 10 4.3 5.3z" /></svg>
                </button>
              </div>
            ))}
          </div>
        )}
        {poll && (
          <fieldset className="mt-2 flex flex-col gap-2 rounded-2xl border border-line p-3">
            <legend className="sr-only">Poll options</legend>
            {poll.map((o, i) => (
              <div key={i} className="flex items-center gap-2">
                <input value={o} maxLength={40} placeholder={`Choice ${i + 1}`} aria-label={`Poll choice ${i + 1}`}
                  onChange={(e) => setPoll((pl) => pl!.map((x, j) => (j === i ? e.target.value : x)))}
                  className="h-10 flex-1 rounded-xl border border-line bg-surface-2 px-3 text-[14.5px] outline-none focus:border-text/50" />
                {poll.length > 2 && (
                  <button type="button" aria-label={`Remove choice ${i + 1}`} onClick={() => setPoll((pl) => pl!.filter((_, j) => j !== i))}
                    className="grid size-8 place-items-center rounded-full text-faint hover:bg-surface-2 hover:text-text">×</button>
                )}
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-2 text-[13px]">
              {poll.length < 4 && <button type="button" onClick={() => setPoll((pl) => [...pl!, ""])} className="font-semibold hover:underline">+ Add choice</button>}
              <label className="ml-auto flex items-center gap-1.5 text-dim">
                Runs for
                <select value={pollHours} onChange={(e) => setPollHours(Number(e.target.value))}
                  className="rounded-lg border border-line bg-surface-2 px-2 py-1 text-text">
                  <option value={1}>1 hour</option><option value={6}>6 hours</option><option value={24}>1 day</option>
                  <option value={72}>3 days</option><option value={168}>7 days</option>
                </select>
              </label>
              <button type="button" onClick={() => setPoll(null)} className="text-danger hover:underline">Remove poll</button>
            </div>
          </fieldset>
        )}
        <div className="mt-2 flex items-center gap-2 border-t border-line pt-2">
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple className="hidden"
            onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={uploads.length >= MAX_MEDIA || !!poll}
            aria-label="Add photos" className="grid size-9 place-items-center rounded-full text-dim transition hover:bg-surface-2 hover:text-text disabled:opacity-40">
            <svg viewBox="0 0 20 20" className="size-5" fill="currentColor" aria-hidden><path d="M3 4h14a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zm1 2v7.6l3.5-3.6 2.6 2.6L13 9.7l3 3V6zm3 1.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z" /></svg>
          </button>
          {!replyTo && !quote && (
            <button type="button" onClick={() => setPoll((pl) => (pl ? null : ["", ""]))} disabled={uploads.length > 0}
              aria-label={poll ? "Remove poll" : "Add a poll"} aria-pressed={!!poll}
              className={cx("grid size-9 place-items-center rounded-full transition hover:bg-surface-2 disabled:opacity-40", poll ? "text-text" : "text-dim hover:text-text")}>
              <svg viewBox="0 0 20 20" className="size-5" fill="currentColor" aria-hidden><path d="M3 4h9v2.4H3zm0 4.8h14v2.4H3zm0 4.8h6V16H3z" /></svg>
            </button>
          )}
          <span className="ml-auto" />
          {count > 0 && <CharRing count={count} />}
          <Button size="sm" onClick={submit} loading={busy} disabled={!canPost}>{replyTo ? "Reply" : "Post"}</Button>
        </div>
      </div>
    </div>
  );
}

/** The app-wide compose sheet (new post, reply, quote). Mounted once in Providers. */
export function ComposeSheet() {
  const s = useCompose();
  return (
    <Sheet open={s.open} onClose={closeCompose} wide title={s.replyTo ? "Reply" : s.quote ? "Quote" : "New post"}>
      {s.replyTo && <QuotedPreview post={s.replyTo} label={`Replying to @${s.replyTo.author?.username ?? "post"}`} />}
      <Composer key={`${s.replyTo?.id ?? ""}${s.quote?.id ?? ""}`} replyTo={s.replyTo} quote={s.quote} autoFocus onPosted={closeCompose} />
      {s.quote && <div className="mt-3 pl-[52px]"><QuotedPreview post={s.quote} /></div>}
    </Sheet>
  );
}

function QuotedPreview({ post: p, label }: { post: PostView; label?: string }) {
  return (
    <div className="mb-3 rounded-2xl border border-line p-3">
      {label && <p className="mb-1 font-mono text-[11px] font-bold tracking-[0.12em] text-faint">{label.toUpperCase()}</p>}
      <p className="text-[13px] font-semibold">{p.author?.display_name} <span className="font-normal text-faint">@{p.author?.username}</span></p>
      {p.text && <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-[14px] text-dim">{p.text}</p>}
      {!p.text && p.media.length > 0 && <p className="mt-1 text-[14px] text-dim">{p.media.length} photo{p.media.length > 1 ? "s" : ""}</p>}
    </div>
  );
}
