"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useToast } from "@/components/toast";
import { Button, Sheet, Spinner } from "@/components/ui";
import { api, errorMessage, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cx } from "@/lib/format";
import type { DebateView, FactCheck, FactCheckRating, PostView } from "@/lib/types";

// ── Challenge: turn a post into a debate with its author ───────────────────

interface Suggestion {
  question: string;
  author_side: "for" | "against";
  challenger_side: "for" | "against";
  author: string | null;
}

export function ChallengeSheet({ p, open, onClose, mode = "invite" }: {
  p: PostView; open: boolean; onClose: () => void; mode?: "invite" | "open";
}) {
  const router = useRouter();
  const toast = useToast();
  const [question, setQuestion] = useState<string | null>(null);
  const [side, setSide] = useState<"for" | "against">("for");
  const [timing, setTiming] = useState<"async" | "live">("async");
  const [busy, setBusy] = useState(false);
  const s = useQuery({
    queryKey: ["challenge-question", p.id, mode],
    queryFn: () => post<Suggestion>(`/posts/${p.id}/challenge-question?mode=${mode}`),
    enabled: open,
    staleTime: Infinity,
    retry: false,
  });
  const text = question ?? s.data?.question ?? "";
  const author = p.author?.username;

  const start = async () => {
    if (!s.data || (mode === "invite" && !author)) return;
    setBusy(true);
    try {
      const mine = { type: "me" };
      const theirs = mode === "open" ? { type: "open" } : { type: "invite", username: author };
      const my = mode === "open" ? side : s.data.challenger_side;
      const d = await post<DebateView>("/debates", {
        question: text.trim(), timing, source_post_id: p.id,
        for: my === "for" ? mine : theirs,
        against: my === "against" ? mine : theirs,
      });
      toast(mode === "open" ? "Debate posted. Anyone can take the other side." : `Challenge sent to @${author}.`, "success");
      onClose();
      router.push(`/d/${d.id}`);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title="Settle it in a debate">
      {s.isLoading && <div className="flex items-center gap-3 py-6 text-sm text-dim"><Spinner className="size-5" /> Finding the fair question…</div>}
      {s.isError && <p className="py-4 text-sm text-danger">{errorMessage(s.error)}</p>}
      {s.data && (
        <div className="flex flex-col gap-4">
          <div>
            <label htmlFor={`cq-${p.id}`} className="mb-1.5 block text-[13px] font-medium text-dim">The motion (edit it if you like)</label>
            <textarea id={`cq-${p.id}`} value={text} onChange={(e) => setQuestion(e.target.value)} rows={2} maxLength={400}
              className="font-display w-full resize-none rounded-2xl border border-line bg-surface-2 px-4 py-3 text-xl font-bold leading-snug outline-none focus:border-text/50" />
          </div>
          {mode === "open" ? (
            <fieldset className="grid grid-cols-2 gap-2 text-sm">
              <legend className="mb-1.5 text-[13px] font-medium text-dim">Your side</legend>
              {(["for", "against"] as const).map((sd) => (
                <button key={sd} type="button" aria-pressed={side === sd} onClick={() => setSide(sd)}
                  className={cx("rounded-2xl border p-3 text-left", side === sd ? (sd === "for" ? "border-for bg-for-soft" : "border-against bg-against-soft") : "border-line hover:bg-surface-2")}>
                  <span className="font-mono text-[11px] font-bold tracking-[0.14em]">{sd === "for" ? "FOR" : "AGAINST"}</span>
                  <span className="block text-[12px] text-dim">{side === sd ? "You" : "Open to anyone"}</span>
                </button>
              ))}
            </fieldset>
          ) : (
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className={cx("rounded-2xl border p-3", s.data.author_side === "for" ? "border-for/60" : "border-against/60")}>
              <p className="font-mono text-[11px] font-bold tracking-[0.14em] text-faint">{s.data.author_side === "for" ? "FOR" : "AGAINST"}</p>
              <p className="font-semibold">@{author}</p>
            </div>
            <div className={cx("rounded-2xl border p-3", s.data.challenger_side === "for" ? "border-for/60" : "border-against/60")}>
              <p className="font-mono text-[11px] font-bold tracking-[0.14em] text-faint">{s.data.challenger_side === "for" ? "FOR" : "AGAINST"}</p>
              <p className="font-semibold">You</p>
            </div>
          </div>
          )}
          <fieldset className="flex gap-2">
            <legend className="mb-1.5 text-[13px] font-medium text-dim">Format</legend>
            {(["async", "live"] as const).map((t) => (
              <button key={t} type="button" aria-pressed={timing === t} onClick={() => setTiming(t)}
                className={cx("flex-1 rounded-2xl border px-3 py-2.5 text-left text-sm", timing === t ? "border-text bg-surface-2" : "border-line hover:bg-surface-2")}>
                <span className="block font-semibold">{t === "async" ? "Take your time" : "Live"}</span>
                <span className="text-[12px] text-dim">{t === "async" ? "Up to a day per turn" : "Minutes per turn"}</span>
              </button>
            ))}
          </fieldset>
          <p className="text-[13px] text-dim">{mode === "open"
            ? "It goes to Open Challenges: the first person to take the other side starts the debate. The crowd votes every round and an AI judge gives the verdict. Free."
            : `@${author} gets a challenge. If they accept, the crowd votes every round and an AI judge gives the verdict. Free.`}</p>
          <Button onClick={start} loading={busy} disabled={text.trim().length < 10}>{mode === "open" ? "Post the debate ⚔" : "Send the challenge ⚔"}</Button>
        </div>
      )}
    </Sheet>
  );
}

// ── Fact-check note ────────────────────────────────────────────────────────

const RATING: Record<FactCheckRating, { label: string; tone: string }> = {
  accurate: { label: "Accurate", tone: "text-ok border-ok/40" },
  mostly_accurate: { label: "Mostly accurate", tone: "text-ok border-ok/40" },
  missing_context: { label: "Missing context", tone: "text-text border-line-strong" },
  unverifiable: { label: "Couldn't verify", tone: "text-dim border-line-strong" },
  misleading: { label: "Misleading", tone: "text-danger border-danger/50" },
  false: { label: "False", tone: "text-danger border-danger/50" },
};

export function FactCheckNote({ fc }: { fc: FactCheck }) {
  if (fc.status === "pending") {
    return <p className="mt-3 flex items-center gap-2 text-[13px] text-dim"><Spinner className="size-3.5" /> AI is checking this post…</p>;
  }
  if (fc.status === "opinion") {
    return <p className="mt-3 text-[13px] text-dim">AI fact-check: this is an opinion, nothing factual to check.</p>;
  }
  if (fc.status !== "done" || !fc.rating) return null;
  const r = RATING[fc.rating];
  return (
    <aside aria-label="AI fact-check" onClick={(e) => e.stopPropagation()} className={cx("mt-3 rounded-2xl border bg-surface/60 px-4 py-3", r.tone)}>
      <p className="font-mono text-[11px] font-bold tracking-[0.14em]">AI FACT-CHECK · {r.label.toUpperCase()}</p>
      {fc.summary && <p className="mt-1 text-[14px] leading-relaxed text-text">{fc.summary}</p>}
      {fc.sources.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {fc.sources.map((s) => (
            <li key={s.url} className="truncate text-[12.5px]">
              <a href={s.url} target="_blank" rel="noopener noreferrer nofollow" className="text-dim underline decoration-line-strong underline-offset-2 hover:text-text">{s.title}</a>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-[11px] text-faint">Generated by AI from web sources. It can be wrong.</p>
    </aside>
  );
}

/** Ask for a fact-check and poll until it lands (about 10–30 seconds). */
export function useFactCheck(p: PostView) {
  const { requireAuth } = useAuth();
  const toast = useToast();
  const [requested, setRequested] = useState(false);
  const q = useQuery({
    queryKey: ["factcheck", p.id],
    queryFn: () => get<FactCheck>(`/posts/${p.id}/factcheck`),
    enabled: requested,
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 3000 : false),
  });
  const request = async () => {
    if (!requireAuth("Sign in to fact-check posts.")) return;
    try {
      await post<FactCheck>(`/posts/${p.id}/factcheck`);
      setRequested(true);
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };
  const fc = q.data ?? p.factcheck;
  return { fc: fc?.status ? fc : null, request };
}

// ── Translation ────────────────────────────────────────────────────────────

const LANG_NAME: Record<string, string> = { en: "English", hi: "हिन्दी" };

export function Translate({ p }: { p: PostView }) {
  const { requireAuth } = useAuth();
  const toast = useToast();
  const [shown, setShown] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!p.text || !p.lang) return null;
  const to = p.lang === "en" ? "hi" : "en";
  const run = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (shown !== null) return setShown(null);
    if (!requireAuth("Sign in to translate posts.")) return;
    setBusy(true);
    try {
      const r = await api<{ lang: string; text: string }>(`/posts/${p.id}/translate?to=${to}`, { method: "POST" });
      setShown(r.text);
    } catch (err) {
      toast(errorMessage(err), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt-1">
      <button type="button" onClick={run} className="text-[13px] text-dim hover:text-text hover:underline" disabled={busy}>
        {busy ? "Translating…" : shown !== null ? "Show original" : `Translate to ${LANG_NAME[to]}`}
      </button>
      {shown !== null && <p lang={to} className="mt-1 whitespace-pre-wrap border-l-2 border-line-strong pl-3 text-[15px] leading-relaxed">{shown}</p>}
    </div>
  );
}
