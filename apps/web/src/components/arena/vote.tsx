"use client";

import { useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { Timer } from "@/components/arena/broadcast";
import { useToast } from "@/components/toast";
import { errorMessage, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { track } from "@/lib/analytics";
import { cx, sideName, sideOf } from "@/lib/format";
import type { DebateView, Position, RoundView } from "@/lib/types";
import { ROUND_LABEL } from "@/lib/types";

export function VotePanel({ debate, round, offsetMs }: { debate: DebateView; round: RoundView; offsetMs: number }) {
  const { requireAuth } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const params = useSearchParams();
  const [busy, setBusy] = useState<Position | null>(null);
  const mine = debate.viewer?.votes?.[round.round];
  const isDebater = !!debate.viewer?.position;

  const vote = async (position: Position) => {
    if (!requireAuth("Sign in to vote — it takes 10 seconds and your vote moves the momentum bar.")) {
      track("login_prompt_shown", { reason: "vote" }, debate.id);
      return;
    }
    setBusy(position);
    try {
      await post(`/debates/${debate.id}/votes`, { round: round.round, position, via_share_link: params.get("ref") === "share" });
      await qc.invalidateQueries({ queryKey: ["debate", debate.id] });
      toast(`Vote locked for ${position.toUpperCase()}. Tally drops when voting closes.`, position);
    } catch (e) {
      toast(errorMessage(e), "error");
    } finally {
      setBusy(null);
    }
  };

  if (isDebater) {
    return (
      <div className="rounded-2xl border border-line bg-surface px-4 py-3 text-sm text-dim">
        The crowd is voting on the {ROUND_LABEL[round.round]}. Results drop when the window closes.
      </div>
    );
  }

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
      className="stage grain overflow-hidden rounded-3xl border border-line-strong p-4 sm:p-5" role="group" aria-label={`Vote on the ${ROUND_LABEL[round.round]}`}>
      <div className="mb-3 flex items-center gap-3">
        <span className="font-mono text-[11px] font-bold tracking-[0.16em] text-live">VOTE NOW</span>
        <span className="text-sm font-semibold">Who won the {ROUND_LABEL[round.round]}?</span>
        {round.vote_closes_at && <Timer deadline={round.vote_closes_at} offsetMs={offsetMs} className="ml-auto" />}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {(["for", "against"] as Position[]).map((p) => {
          const chosen = mine === p;
          return (
            <button key={p} onClick={() => vote(p)} disabled={busy !== null} aria-pressed={chosen}
              className={cx(
                "flex flex-col items-start gap-1 rounded-2xl border-2 px-4 py-3 text-left transition active:scale-[0.98]",
                p === "for" ? "border-for/50 hover:bg-for-soft" : "border-against/50 hover:bg-against-soft",
                chosen && (p === "for" ? "bg-for text-[#0a0a0b]" : "bg-against text-white"),
              )}>
              <span className="font-mono text-[11px] font-bold tracking-[0.14em]">{p === "for" ? "FOR" : "AGAINST"}{chosen ? " ✓" : ""}</span>
              <span className="truncate text-[13px] font-semibold opacity-90">{sideName(sideOf(debate, p))}</span>
            </button>
          );
        })}
      </div>
      {mine && <p className="mt-2 text-[12px] text-faint">You can change your vote until the window closes.</p>}
    </motion.div>
  );
}
