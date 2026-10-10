"use client";

import { AnimatePresence, motion } from "motion/react";

import { SideTag } from "@/components/ui";
import { cx } from "@/lib/format";
import type { ClaimStatus, ClaimView, Position } from "@/lib/types";

const STAMP: Partial<Record<ClaimStatus, { text: string; cls: string }>> = {
  rebutted: { text: "REBUTTED", cls: "border-dim text-dim" },
  conceded: { text: "CONCEDED", cls: "border-win text-win" },
  supported: { text: "SOURCE CHECKS OUT", cls: "border-ok text-ok" },
  unsupported: { text: "UNSUPPORTED", cls: "border-dim text-dim" },
  misattributed: { text: "SOURCE DOESN'T SAY THAT", cls: "border-danger text-danger" },
};

export function ClaimChip({ claim, id }: { claim: ClaimView; id?: string }) {
  const stamp = STAMP[claim.status];
  const struck = claim.status === "rebutted" || claim.status === "conceded";
  return (
    <motion.li id={id} layout initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }}
      className={cx("relative rounded-xl border bg-surface p-3",
        claim.position === "for" ? "border-for/25" : "border-against/30",
        claim.status === "unaddressed" && "animate-pulse-soft")}>
      <div className="mb-1 flex items-center gap-2">
        <span className="font-mono text-[10.5px] font-bold text-faint">C{claim.seq}</span>
        {claim.responds_to && <span className="font-mono text-[10px] text-faint">→ C{claim.responds_to}</span>}
        {claim.status === "unaddressed" && <span className="ml-auto font-mono text-[9.5px] font-bold tracking-[0.14em] text-win">UNANSWERED</span>}
      </div>
      <p className={cx("text-[13px] leading-snug", struck && "text-dim line-through decoration-2", claim.status === "misattributed" && "text-dim")}>
        {claim.text}
      </p>
      {claim.source_url && (
        <a href={claim.source_url} target="_blank" rel="noopener noreferrer nofollow ugc" className="mt-1 block truncate text-[11px] text-faint underline decoration-dotted">
          {new URL(claim.source_url).hostname.replace(/^www\./, "")}
        </a>
      )}
      <AnimatePresence>
        {stamp && (
          <motion.span key={claim.status}
            initial={{ scale: 2.2, opacity: 0, rotate: -14 }} animate={{ scale: 1, opacity: 1, rotate: -8 }}
            transition={{ type: "spring", stiffness: 420, damping: 18 }}
            className={cx("absolute -right-1 -top-2 rounded-md border-2 bg-bg px-1.5 py-0.5 font-mono text-[9px] font-black tracking-[0.12em]", stamp.cls)}>
            {stamp.text}
          </motion.span>
        )}
      </AnimatePresence>
    </motion.li>
  );
}

export function ClaimBoard({ claims }: { claims: ClaimView[] }) {
  const col = (p: Position) => claims.filter((c) => c.position === p);
  if (claims.length === 0) {
    return <p className="py-10 text-center text-sm text-dim">Claims appear here as the debaters make them — and get stamped as they&apos;re rebutted, conceded or fact-checked.</p>;
  }
  const stats = (p: Position) => {
    const c = col(p);
    return `${c.filter((x) => x.status === "unaddressed").length} unanswered · ${c.filter((x) => x.status === "rebutted").length} rebutted`;
  };
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-5">
      {(["for", "against"] as Position[]).map((p) => (
        <div key={p}>
          <div className="mb-3 flex flex-col gap-0.5">
            <SideTag position={p} />
            <span className="text-[11px] text-faint">{stats(p)}</span>
          </div>
          <ul className="flex flex-col gap-3">{col(p).map((c) => <ClaimChip key={c.id} claim={c} />)}</ul>
        </div>
      ))}
    </div>
  );
}
