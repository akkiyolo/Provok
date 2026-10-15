"use client";

import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, m, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useState } from "react";

import { MomentumBar, Ticker } from "@/components/arena/broadcast";
import { ClaimChip } from "@/components/arena/claims";
import { ShareButtons } from "@/components/share";
import { useToast } from "@/components/toast";
import { Button, ErrorBlock, ModelBadge, SideTag, Spinner } from "@/components/ui";
import { ApiError, errorMessage, get } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { track } from "@/lib/analytics";
import { cx, sideName, sideOf } from "@/lib/format";
import { type Position, ROUND_LABEL, ROUNDS, type VerdictResponse } from "@/lib/types";

const CRITERIA: Record<string, string> = {
  argument_strength: "Argument",
  evidence_quality: "Evidence",
  rebuttal_coverage: "Rebuttal",
  responsiveness: "Responsiveness",
  consistency: "Consistency",
};

const avg = (o: Record<string, number> | undefined) => (o ? Object.values(o).reduce((a, b) => a + b, 0) / Object.values(o).length : 0);

function useVerdict(id: string) {
  return useQuery({
    queryKey: ["verdict", id],
    queryFn: () => get<VerdictResponse>(`/debates/${id}/verdict`),
    retry: (n, e) => e instanceof ApiError && e.code === "verdict_pending" && n < 120,
    retryDelay: 5000,
    refetchInterval: (q) => (q.state.data?.audience.final_vote_open ? 20_000 : false),
  });
}

/** Explanation with C# references rendered as chips that scroll to the claim. */
function Reasoning({ text }: { text: string }) {
  return (
    <p className="text-[16px] leading-[1.7] text-text/90">
      {text.split(/(C\d{1,3})/g).map((part, i) =>
        /^C\d{1,3}$/.test(part) ? (
          <a key={i} href={`#claim-${part.slice(1)}`} className="mx-0.5 rounded-md bg-surface-3 px-1.5 py-0.5 font-mono text-[12px] font-bold hover:bg-line-strong">{part}</a>
        ) : <Fragment key={i}>{part}</Fragment>,
      )}
    </p>
  );
}

function Reveal({ v, onDone }: { v: VerdictResponse; onDone: () => void }) {
  const reduce = useReducedMotion();
  const [stage, setStage] = useState(0);
  const d = v.debate;
  const winner = v.judge.winner_position;
  const rounds = ROUNDS.filter((r) => v.judge.per_round[r]);
  useEffect(() => {
    if (reduce) {
      onDone();
      return;
    }
    const timings = [1400, 1400 + rounds.length * 900 + 600, 2200, 3200];
    let t = 0;
    const ids = timings.map((ms, i) => {
      t += ms;
      return setTimeout(() => (i === timings.length - 1 ? onDone() : setStage(i + 1)), t);
    });
    return () => ids.forEach(clearTimeout);
  }, [reduce, onDone, rounds.length]);

  const flood = stage >= 3 && winner ? (winner === "for" ? "var(--for)" : "var(--against)") : "transparent";
  return (
    <m.div className="fixed inset-0 z-[70] flex flex-col items-center justify-center overflow-hidden bg-[#050506] px-6 text-[#F2EFE9]"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.6 }}>
      <m.div className="absolute inset-0" animate={{ backgroundColor: flood, opacity: stage >= 3 ? 0.22 : 0 }} transition={{ duration: 1.2 }} aria-hidden />
      <m.div className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(40% 40% at 50% 40%, rgba(242,239,233,0.12), transparent 70%)" }}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4, duration: 1.6 }} aria-hidden />
      <button onClick={onDone} className="absolute right-5 top-5 z-10 rounded-full border border-white/20 px-3 py-1 text-[12px] text-white/70 hover:text-white">Skip</button>

      <div className="relative z-10 flex w-full max-w-2xl flex-col items-center text-center">
        <m.p initial={{ opacity: 0, letterSpacing: "0.6em" }} animate={{ opacity: 1, letterSpacing: "0.3em" }} transition={{ duration: 1.2 }}
          className="font-mono text-[12px] font-bold text-white/60">THE VERDICT</m.p>
        <m.h1 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="font-display mt-4 text-[clamp(1.6rem,4.5vw,2.8rem)] font-extrabold leading-[1.02]">{d.question}</m.h1>

        <AnimatePresence>
          {stage >= 1 && (
            <m.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-10 w-full">
              <p className="mb-3 font-mono text-[11px] font-bold tracking-[0.2em] text-white/50">JUDGE · ROUND BY ROUND</p>
              <div className="flex flex-col gap-2">
                {rounds.map((r, i) => {
                  const pr = v.judge.per_round[r]!;
                  return (
                    <m.div key={r} initial={{ opacity: 0, x: -12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.9 }}
                      className="grid grid-cols-[1fr_auto_1fr] items-center gap-4 rounded-xl border border-white/10 px-4 py-2.5">
                      <span className="text-left font-mono text-2xl font-bold text-[#FF5A1F]"><Ticker value={avg(pr.for)} /></span>
                      <span className="font-mono text-[11px] font-bold tracking-[0.16em] text-white/60">{ROUND_LABEL[r].toUpperCase()}</span>
                      <span className="text-right font-mono text-2xl font-bold text-[#4C6FFF]"><Ticker value={avg(pr.against)} /></span>
                    </m.div>
                  );
                })}
              </div>
            </m.div>
          )}
        </AnimatePresence>

        {stage >= 2 && (
          <m.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="mt-8 w-full">
            <p className="mb-3 font-mono text-[11px] font-bold tracking-[0.2em] text-white/50">THE CROWD</p>
            <MomentumBar share={(v.audience.totals.for + v.audience.totals.against) ? v.audience.totals.for / (v.audience.totals.for + v.audience.totals.against) : null} size="lg" />
          </m.div>
        )}

        {stage >= 3 && (
          <m.div initial={{ scale: 2.4, opacity: 0, rotate: -6 }} animate={{ scale: 1, opacity: 1, rotate: -3 }}
            transition={{ type: "spring", stiffness: 260, damping: 16 }} className="mt-10">
            {winner ? (
              <div className="flex flex-col items-center gap-2">
                <span className="font-mono text-[12px] font-bold tracking-[0.3em] text-[#E8C547]">{v.judge.is_close ? "NARROW WIN" : "WINNER"}</span>
                <span className={cx("font-display text-[clamp(2.4rem,8vw,4.5rem)] font-extrabold leading-none", winner === "for" ? "text-[#FF5A1F]" : "text-[#4C6FFF]")}>
                  {winner.toUpperCase()}
                </span>
                <span className="text-lg font-semibold text-[#E8C547]">★ {sideName(sideOf(d, winner))}</span>
              </div>
            ) : (
              <span className="font-display text-5xl font-extrabold text-[#E8C547]">TOO CLOSE TO CALL</span>
            )}
          </m.div>
        )}
      </div>
    </m.div>
  );
}

export function VerdictView({ id }: { id: string }) {
  const q = useVerdict(id);
  const router = useRouter();
  const toast = useToast();
  const { requireAuth } = useAuth();
  const [revealed, setRevealed] = useState<boolean | null>(null);

  useEffect(() => {
    if (!q.data) return;
    track("verdict_viewed", { winner: q.data.judge.winner_position ?? "none" }, id);
    let seen = false;
    try {
      seen = sessionStorage.getItem(`provok:revealed:${id}`) === "1";
    } catch {
      /* ignore */
    }
    setTimeout(() => setRevealed(seen), 0);
  }, [q.data, id]);

  const finishReveal = () => {
    try {
      sessionStorage.setItem(`provok:revealed:${id}`, "1");
    } catch {
      /* ignore */
    }
    setRevealed(true);
  };

  const rematch = async () => {
    if (!requireAuth("Sign in to call a rematch.")) return;
    try {
      const tpl = await get<Record<string, unknown>>(`/debates/${id}/rematch-template`);
      sessionStorage.setItem("provok:rematch", JSON.stringify(tpl));
      track("rematch_clicked", {}, id);
      router.push("/new?rematch=1");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
  };

  if (q.isError && !(q.error instanceof ApiError && q.error.code === "verdict_pending")) {
    return <div className="mx-auto max-w-2xl px-4 py-16"><ErrorBlock message={errorMessage(q.error)} retry={() => q.refetch()} /></div>;
  }
  if (!q.data) {
    return (
      <div className="stage grain flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
        <Spinner className="size-8 text-win" />
        <p className="font-display text-3xl font-extrabold">The judge is deliberating.</p>
        <p className="max-w-md text-dim">Checking every cited source, scoring each round blind, then re-running with the sides swapped to rule out bias.</p>
        <Link href={`/d/${id}`} className="text-sm text-dim underline underline-offset-4">Back to the arena</Link>
      </div>
    );
  }

  const v = q.data;
  const d = v.debate;
  const winner = v.judge.winner_position;
  const crowd = v.audience.winner_position;
  const rounds = ROUNDS.filter((r) => v.judge.per_round[r]);
  const agree = winner && crowd ? winner === crowd : null;
  const winnerName = winner ? sideName(sideOf(d, winner)) : null;

  return (
    <>
      <AnimatePresence>{revealed === false && <Reveal v={v} onDone={finishReveal} />}</AnimatePresence>
      <div className={cx("grain relative min-h-dvh", winner === "for" ? "stage-duel" : "stage-duel")}>
        <div className="mx-auto max-w-4xl px-4 pb-24 pt-8 sm:px-6">
          <Link href={`/d/${id}`} className="text-sm text-dim hover:text-text">← Back to the arena</Link>
          <p className="mt-6 font-mono text-[11px] font-bold tracking-[0.2em] text-win">THE VERDICT</p>
          <h1 className="font-display mt-2 text-[clamp(1.8rem,5vw,3.2rem)] font-extrabold leading-[1]">{d.question}</h1>

          <section className="mt-8 grid gap-4 sm:grid-cols-2">
            <div className={cx("rounded-3xl border-2 p-5", winner === "for" ? "border-for" : winner === "against" ? "border-against" : "border-win")}>
              <p className="font-mono text-[11px] font-bold tracking-[0.16em] text-dim">AI JUDGE</p>
              {winner ? (
                <>
                  <p className="mt-2 flex items-center gap-2"><SideTag position={winner} /><span className="text-win">★</span></p>
                  <p className="font-display mt-1 text-3xl font-extrabold text-win">{winnerName}</p>
                  <p className="mt-1 text-sm text-dim">{v.judge.is_close ? "A narrow call — the judge's two blind runs were split or the margin was small." : "A clear win across both blind judging runs."}</p>
                </>
              ) : (
                <p className="font-display mt-2 text-3xl font-extrabold text-win">Too close to call</p>
              )}
              {v.judge.scores.for !== undefined && (
                <p className="mt-3 font-mono text-sm"><span className="text-for">{v.judge.scores.for?.toFixed(2)}</span> <span className="text-faint">vs</span> <span className="text-against">{v.judge.scores.against?.toFixed(2)}</span></p>
              )}
            </div>
            <div className="rounded-3xl border border-line bg-surface p-5">
              <p className="font-mono text-[11px] font-bold tracking-[0.16em] text-dim">THE CROWD</p>
              <p className="font-display mt-2 text-3xl font-extrabold">
                {crowd ? <span className={crowd === "for" ? "text-for" : "text-against"}>{crowd.toUpperCase()}</span> :
                  v.audience.totals.for + v.audience.totals.against === 0 ? "No votes yet" : "Dead even"}
              </p>
              <div className="mt-3">
                <MomentumBar emptyLabel="Be the first to vote" share={(v.audience.totals.for + v.audience.totals.against) ? v.audience.totals.for / (v.audience.totals.for + v.audience.totals.against) : null} />
              </div>
              {agree !== null && <p className={cx("mt-3 text-sm font-semibold", agree ? "text-ok" : "text-win")}>{agree ? "Judge and crowd agree." : "Upset! The crowd disagrees with the judge."}</p>}
              {v.audience.final_vote_open && <p className="mt-2 text-[12px] text-faint">Final-round voting is still open — the crowd tally may still move.</p>}
            </div>
          </section>

          <section className="mt-8 rounded-3xl border border-line bg-surface p-5 sm:p-7">
            <h2 className="font-display text-2xl font-bold">Why</h2>
            <div className="mt-3"><Reasoning text={v.judge.reasoning} /></div>
            {v.judge.decisive_claims.length > 0 && (
              <>
                <p className="mt-6 font-mono text-[11px] font-bold tracking-[0.16em] text-dim">DECISIVE CLAIMS</p>
                <ul className="mt-3 grid gap-3 sm:grid-cols-2">
                  {v.judge.decisive_claims.map((c) => (
                    <ClaimChip key={c.id} id={`claim-${c.seq}`} claim={{ ...c, turn_id: "", source_url: null, responds_to: null }} />
                  ))}
                </ul>
              </>
            )}
          </section>

          {rounds.length > 0 && (
            <section className="mt-8 rounded-3xl border border-line bg-surface p-5 sm:p-7">
              <h2 className="font-display text-2xl font-bold">Scorecard</h2>
              {/* Seven columns don't fit a phone: the table scrolls sideways inside the card, one line per cell. */}
              <div className="-mx-5 overflow-x-auto px-5 sm:-mx-7 sm:px-7">
              <table className="mt-4 w-full min-w-[640px] whitespace-nowrap text-sm [&_td]:pr-4 [&_th]:pr-4">
                <thead>
                  <tr className="text-left font-mono text-[11px] tracking-[0.1em] text-faint">
                    <th className="py-2 font-semibold">ROUND</th>
                    {Object.values(CRITERIA).map((c) => <th key={c} className="py-2 font-semibold">{c.toUpperCase()}</th>)}
                    <th className="py-2 font-semibold">CROWD</th>
                  </tr>
                </thead>
                <tbody>
                  {rounds.map((r) => {
                    const pr = v.judge.per_round[r]!;
                    const t = v.audience.per_round[r];
                    return (
                      <tr key={r} className="border-t border-line">
                        <td className="py-3 font-semibold">{ROUND_LABEL[r]}</td>
                        {Object.keys(CRITERIA).map((c) => (
                          <td key={c} className="py-3 font-mono tabular">
                            <span className="text-for">{pr.for?.[c]?.toFixed(1)}</span><span className="text-faint"> · </span><span className="text-against">{pr.against?.[c]?.toFixed(1)}</span>
                          </td>
                        ))}
                        <td className="py-3 font-mono tabular">{t ? `${Math.round(t.for_share * 100)}% FOR` : "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              </div>
              <p className="mt-3 text-[12px] text-faint">Scores 1–10, averaged over two blind judging runs with the sides&apos; labels swapped. The judge never sees names, models or who is human.</p>
            </section>
          )}

          {v.clips.length > 0 && (
            <section className="mt-8">
              <h2 className="font-display text-2xl font-bold">Highlights</h2>
              <div className="no-scrollbar mt-4 flex snap-x gap-4 overflow-x-auto pb-2">
                {v.clips.map((c) => (
                  <figure key={c.id} className="w-56 shrink-0 snap-start overflow-hidden rounded-2xl border border-line bg-surface">
                    <video src={c.url} controls playsInline preload="metadata" className="aspect-[9/16] w-full bg-black" onPlay={() => track("clip_played", {}, id)} />
                    <figcaption className="p-3 text-[12px] text-dim">{c.reason}</figcaption>
                  </figure>
                ))}
              </div>
            </section>
          )}

          <section className="mt-8 flex flex-col gap-4 rounded-3xl border border-line bg-surface p-5 sm:flex-row sm:items-center sm:p-7">
            <div className="flex-1">
              <p className="font-display text-xl font-bold">Disagree with the judge?</p>
              <p className="text-sm text-dim">Call a rematch with the corners swapped — or share it and let the internet argue.</p>
            </div>
            <div className="flex flex-col gap-3">
              <Button variant="win" onClick={rematch}>Rematch →</Button>
              <ShareButtons title={d.question} kind="verdict" debateId={id} path={`/d/${id}/verdict`}
                text={winner ? `${winnerName} won "${d.question}" on Provok. Agree? ⚔️` : `"${d.question}" was too close to call on Provok. Your call? ⚔️`} />
            </div>
          </section>

          <div className="mt-6 flex flex-wrap gap-2 text-[12px] text-faint">
            {d.sides.filter((s) => s.model).map((s) => <ModelBadge key={s.id} model={s.model} position={s.position as Position} />)}
            {v.judge.model_name && <span>Judged by {v.judge.model_name.replace(/^Judge \((.*)\)$/, "$1")}</span>}
          </div>
        </div>
      </div>
    </>
  );
}
