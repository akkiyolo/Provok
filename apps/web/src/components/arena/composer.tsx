"use client";

import { useState } from "react";

import { Timer } from "@/components/arena/broadcast";
import { useToast } from "@/components/toast";
import { Button } from "@/components/ui";
import { ApiError, errorMessage, post } from "@/lib/api";
import { cx, wordCount } from "@/lib/format";
import type { DebateView } from "@/lib/types";
import { ROUND_LABEL } from "@/lib/types";

const PROMPTS: Record<string, string> = {
  "opening:argument": "Open strong. Define the terms in your favour and land your two or three best arguments.",
  "rebuttal:argument": "Go after their strongest claim. Name it, then take it apart.",
  "cross_exam:question": "Ask ONE sharp question that exposes the weakest point in their case.",
  "cross_exam:answer": "Answer directly first — yes or no if you can — then justify.",
  "closing:argument": "Crystallise the clashes you won and weigh why they matter most.",
};

function Ring({ used, limit }: { used: number; limit: number }) {
  const r = 14;
  const c = 2 * Math.PI * r;
  const pct = Math.min(1, used / limit);
  const over = used > limit;
  const near = !over && used >= limit * 0.9;
  return (
    <div className="relative grid size-10 place-items-center" aria-label={`${used} of ${limit} words`} role="status">
      <svg viewBox="0 0 36 36" className="absolute inset-0 -rotate-90" aria-hidden>
        <circle cx="18" cy="18" r={r} fill="none" stroke="var(--line)" strokeWidth="3" />
        <circle cx="18" cy="18" r={r} fill="none" strokeWidth="3" strokeLinecap="round"
          stroke={over ? "var(--danger)" : near ? "var(--win)" : "var(--text)"} strokeDasharray={c} strokeDashoffset={c * (1 - pct)}
          className="transition-[stroke-dashoffset] duration-200" />
      </svg>
      <span className={cx("font-mono text-[10px] font-bold tabular", over ? "text-danger" : "text-dim")}>{limit - used}</span>
    </div>
  );
}

/** Remount per turn (`key={round:index}`) so drafts and idempotency keys are per turn. */
export function Composer({ debate, offsetMs, onSubmitted, onOpenClaims }: {
  debate: DebateView; offsetMs: number; onSubmitted: (d: DebateView) => void; onOpenClaims: () => void;
}) {
  const exp = debate.expected!;
  const key = `provok:draft:${debate.id}:${debate.current_round}:${debate.turn_index}`;
  const [text, setText] = useState(() => {
    try {
      return localStorage.getItem(key) ?? "";
    } catch {
      return "";
    }
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [idem] = useState(() => crypto.randomUUID().replace(/-/g, ""));
  const toast = useToast();
  const used = wordCount(text);
  const over = used > debate.word_limit;

  const update = (value: string) => {
    setText(value);
    try {
      if (value) localStorage.setItem(key, value);
      else localStorage.removeItem(key);
    } catch {
      /* private mode */
    }
  };

  const submit = async () => {
    if (!text.trim() || over || busy) return;
    setBusy(true);
    setError(null);
    try {
      const d = await post<DebateView>(`/debates/${debate.id}/turns`, { content: text.trim(), idempotency_key: idem });
      try {
        localStorage.removeItem(key);
      } catch {
        /* ignore */
      }
      setText("");
      onSubmitted(d);
      toast("Your turn is in. Share it so people vote for you.", "for");
    } catch (e) {
      setError(errorMessage(e));
      if (e instanceof ApiError && e.code === "not_your_turn") onSubmitted(debate);
    } finally {
      setBusy(false);
    }
  };

  const promptKey = `${debate.current_round}:${exp.kind}`;
  return (
    <div className={cx("rounded-3xl border bg-surface p-4 sm:p-5", exp.position === "for" ? "border-for/60 shadow-[0_0_40px_var(--for-glow)]" : "border-against/60 shadow-[0_0_40px_var(--against-glow)]")}>
      <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 whitespace-nowrap">
        <span className="font-mono text-[11px] font-bold tracking-[0.16em] text-live">YOUR TURN</span>
        <span className="text-[13px] text-dim">{ROUND_LABEL[debate.current_round!]} · {exp.kind}</span>
        <button type="button" onClick={onOpenClaims} className="rounded-full border border-line px-2.5 py-0.5 text-[12px] text-dim hover:text-text">
          Claim Board · {debate.claims.length}
        </button>
        <Timer deadline={debate.deadline_at} offsetMs={offsetMs} className="ml-auto" urgentAt={debate.timing === "async" ? 600 : 10} />
      </div>
      <label htmlFor="composer" className="sr-only">Write your {exp.kind}</label>
      <textarea
        id="composer"
        data-turn={`${debate.current_round}:${debate.turn_index}`}
        value={text}
        onChange={(e) => update(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            void submit();
          }
        }}
        placeholder={PROMPTS[promptKey] ?? "Make your case."}
        rows={exp.kind === "argument" ? 6 : 3}
        maxLength={12000}
        className="w-full resize-y rounded-2xl border border-line bg-bg/40 p-3.5 text-[15px] leading-relaxed outline-none placeholder:text-faint focus:border-text/50"
      />
      {error && <p role="alert" className="mt-2 text-sm text-danger">{error}</p>}
      <div className="mt-3 flex items-center gap-3">
        <Ring used={used} limit={debate.word_limit} />
        <span className={cx("text-[12.5px]", over ? "text-danger" : "text-faint")}>
          {over ? `${used - debate.word_limit} words over the limit` : `${used}/${debate.word_limit} words`}
        </span>
        <Button className="ml-auto" variant={exp.position === "for" ? "for" : "against"} loading={busy}
          disabled={!text.trim() || over} onClick={submit}>
          Submit {exp.kind}
        </Button>
      </div>
      <p className="mt-2 hidden text-right text-[11px] text-faint sm:block">Ctrl / ⌘ + Enter to submit · drafts save automatically</p>
    </div>
  );
}
