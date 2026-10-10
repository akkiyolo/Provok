"use client";

import { motion } from "motion/react";
import { Fragment } from "react";

import { ReportButton } from "@/components/report";
import { Avatar, ModelBadge, SideTag } from "@/components/ui";
import { cx, timeAgo } from "@/lib/format";
import type { Citation, DebateView, Position, RoundName, SideView, TurnView } from "@/lib/types";
import { ROUND_LABEL } from "@/lib/types";

const KIND_LABEL = { argument: "", question: "Question", answer: "Answer" } as const;

/** Render turn text with [n] citation markers as accessible superscript links. */
export function TurnText({ text, citations }: { text: string; citations: Citation[] }) {
  const byN = new Map(citations.map((c) => [c.n, c]));
  const parts = text.split(/(\[\d{1,2}\])/g);
  return (
    <>
      {text.split("\n\n").length > 1
        ? text.split("\n\n").map((para, i) => (
            <p key={i} className="mb-3 last:mb-0"><TurnText text={para} citations={citations} /></p>
          ))
        : parts.map((part, i) => {
            const m = /^\[(\d{1,2})\]$/.exec(part);
            const c = m ? byN.get(Number(m[1])) : undefined;
            if (c) {
              return (
                <a key={i} href={c.url} target="_blank" rel="noopener noreferrer nofollow ugc" title={c.title}
                  className="mx-0.5 align-super font-mono text-[10px] font-bold text-dim underline decoration-dotted underline-offset-2 hover:text-text">
                  {c.n}<span className="sr-only"> (source: {c.title})</span>
                </a>
              );
            }
            return <Fragment key={i}>{part}</Fragment>;
          })}
    </>
  );
}

function Speaker({ side, position }: { side: SideView | undefined; position: Position }) {
  if (side?.participant_type === "swarm") return <ModelBadge model={side.model} position={position} />;
  return (
    <span className="flex items-center gap-2">
      <Avatar user={side?.user ?? null} size={22} />
      <span className="text-[13px] font-semibold">{side?.user?.display_name ?? "Debater"}</span>
    </span>
  );
}

export function TurnCard({ turn, side, highlight }: { turn: TurnView; side: SideView | undefined; highlight?: boolean }) {
  const p = turn.position;
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 260, damping: 28 }}
      aria-label={`${p.toUpperCase()} ${KIND_LABEL[turn.kind] || "argument"}`}
      className={cx(
        "group relative rounded-2xl border bg-surface p-4 sm:p-5",
        p === "for" ? "border-for/25 md:mr-6" : "border-against/30 md:ml-6",
        highlight && (p === "for" ? "shadow-[0_0_0_1px_var(--for),0_0_32px_var(--for-glow)]" : "shadow-[0_0_0_1px_var(--against),0_0_32px_var(--against-glow)]"),
      )}
    >
      <span className={cx("absolute inset-y-4 w-[3px] rounded-full", p === "for" ? "-left-px bg-for" : "-right-px bg-against")} aria-hidden />
      <header className="mb-2.5 flex flex-wrap items-center gap-2">
        <SideTag position={p} />
        {KIND_LABEL[turn.kind] && (
          <span className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-[0.1em] text-dim">
            {KIND_LABEL[turn.kind]}
          </span>
        )}
        <Speaker side={side} position={p} />
        {turn.source === "transcript" && <span className="text-[11px] text-faint">🎙 transcript</span>}
        <span className="ml-auto font-mono text-[10.5px] text-faint">{timeAgo(turn.created_at)}</span>
      </header>
      {turn.is_forfeit ? (
        <p className="italic text-faint">No response — the clock ran out.</p>
      ) : turn.hidden && turn.content === "This turn is under review." ? (
        <p className="italic text-faint">This turn is under review by our moderators.</p>
      ) : (
        <div className={cx("text-[15px] leading-[1.65] text-text/95", turn.hidden && "opacity-70")}>
          <TurnText text={turn.content} citations={turn.citations} />
        </div>
      )}
      {!turn.is_forfeit && (
        <footer className="mt-3 flex items-center gap-3 text-[11px] text-faint">
          <span className="font-mono">{turn.word_count} words</span>
          {turn.citations.length > 0 && <span>{turn.citations.length} source{turn.citations.length > 1 ? "s" : ""}</span>}
          <span className="ml-auto opacity-0 transition group-hover:opacity-100 focus-within:opacity-100">
            <ReportButton targetType="turn" targetId={turn.id} />
          </span>
        </footer>
      )}
    </motion.article>
  );
}

/** Live Typing Stage: a swarm turn streaming in, lit in its side's colour. */
export function TypingCard({ position, text, side }: { position: Position; text: string; side: SideView | undefined }) {
  return (
    <div aria-live="polite" aria-busy="true"
      className={cx("relative rounded-2xl border p-4 sm:p-5",
        position === "for" ? "border-for/60 bg-for-soft shadow-[0_0_40px_var(--for-glow)] md:mr-6" : "border-against/60 bg-against-soft shadow-[0_0_40px_var(--against-glow)] md:ml-6")}>
      <header className="mb-2.5 flex items-center gap-2">
        <SideTag position={position} />
        <Speaker side={side} position={position} />
        <span className="ml-auto font-mono text-[10.5px] font-bold tracking-[0.12em] text-live animate-pulse-soft">ON AIR</span>
      </header>
      <p className="text-[15px] leading-[1.65]">
        {text || <span className="text-dim">Researching, planning, drafting…</span>}
        <span className={cx("ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[3px] animate-pulse", position === "for" ? "bg-for" : "bg-against")} aria-hidden />
      </p>
    </div>
  );
}

export function ThinkingCard({ position, side }: { position: Position; side: SideView | undefined }) {
  return (
    <div className={cx("flex items-center gap-3 rounded-2xl border border-dashed p-4", position === "for" ? "border-for/40 md:mr-6" : "border-against/40 md:ml-6")}>
      <SideTag position={position} />
      <Speaker side={side} position={position} />
      <span className="flex gap-1" aria-label="Thinking">
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className={cx("size-1.5 rounded-full", position === "for" ? "bg-for" : "bg-against")}
            animate={{ opacity: [0.2, 1, 0.2] }} transition={{ repeat: Infinity, duration: 1.2, delay: i * 0.2 }} />
        ))}
      </span>
      <span className="text-[13px] text-dim">researching &amp; drafting…</span>
    </div>
  );
}

export function RoundSection({ round, debate, children }: { round: RoundName; debate: DebateView; children: React.ReactNode }) {
  const active = debate.current_round === round && ["opening", "rebuttal", "cross_exam", "closing"].includes(debate.status);
  return (
    <section aria-label={`${ROUND_LABEL[round]} round`} className="flex flex-col gap-3">
      <div className="sticky top-[var(--arena-header,0px)] z-10 -mx-1 flex items-center gap-3 bg-bg/80 px-1 py-2 backdrop-blur">
        <span className={cx("font-mono text-[11px] font-bold uppercase tracking-[0.18em]", active ? "text-text" : "text-faint")}>
          {ROUND_LABEL[round]}
        </span>
        <span className="h-px flex-1 bg-line" />
        {active && <span className="font-mono text-[10px] font-bold tracking-[0.14em] text-live">NOW</span>}
      </div>
      {children}
    </section>
  );
}
