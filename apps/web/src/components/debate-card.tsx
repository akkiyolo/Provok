"use client";

import Link from "next/link";

import { MomentumBar, RoundRail, Timer } from "@/components/arena/broadcast";
import { Avatar, LiveBadge, ModelBadge, Pill, SideTag } from "@/components/ui";
import { compact, cx, isLive, modeText, sideName, sideOf, statusText, timeAgo } from "@/lib/format";
import type { DebateCard as Card, Position, SideView } from "@/lib/types";

function Corner({ side, position, align = "left", winner }: { side: SideView | undefined; position: Position; align?: "left" | "right"; winner?: boolean }) {
  return (
    <div className={cx("flex min-w-0 items-center gap-2.5", align === "right" && "flex-row-reverse text-right")}>
      {side?.participant_type === "swarm" ? (
        <span className={cx("grid size-9 shrink-0 place-items-center rounded-full border",
          position === "for" ? "border-for/50 bg-for-soft text-for" : "border-against/50 bg-against-soft text-against")} aria-hidden>
          <svg viewBox="0 0 16 16" className="size-4" fill="currentColor"><path d="M8 1l1.6 4.4L14 7l-4.4 1.6L8 13l-1.6-4.4L2 7l4.4-1.6z" /></svg>
        </span>
      ) : side?.user ? (
        <Avatar user={side.user} size={36} ring={position} />
      ) : (
        <span className="grid size-9 shrink-0 place-items-center rounded-full border border-dashed border-line-strong text-faint" aria-hidden>?</span>
      )}
      <div className={cx("min-w-0", align === "right" && "items-end")}>
        <SideTag position={position} className={align === "right" ? "flex-row-reverse" : ""} />
        <p className={cx("truncate text-[13.5px] font-semibold", winner && "text-win")}>
          {winner && "★ "}{side?.participant_type === "swarm" ? <ModelBadge model={side.model} position={position} /> : sideName(side)}
        </p>
      </div>
    </div>
  );
}

export function DebateCard({ d, variant = "grid" }: { d: Card; variant?: "grid" | "hero" | "full" }) {
  const live = isLive(d.status);
  const open = d.status === "waiting_for_opponent" || d.status === "swarm_fallback_offered";
  const big = variant !== "grid";
  return (
    <Link href={`/d/${d.id}`}
      className={cx(
        "group stage grain relative flex flex-col overflow-hidden border border-line transition",
        "hover:border-line-strong focus-visible:border-text",
        variant === "full" ? "h-full justify-between rounded-none border-0 px-5 pb-28 pt-6" : "rounded-3xl p-5",
        variant === "hero" && "min-h-[300px] p-7",
      )}>
      <div className="flex flex-wrap items-center gap-2">
        {live ? <LiveBadge label={d.status === "judging" ? "JUDGING" : "LIVE"} /> : open ? (
          <span className="rounded-full bg-win/15 px-2 py-0.5 font-mono text-[10.5px] font-bold tracking-[0.14em] text-win">OPEN</span>
        ) : <Pill>{statusText(d.status)}</Pill>}
        <Pill>{modeText(d.mode)}</Pill>
        {d.timing === "video" && <Pill>🎙 Video</Pill>}
        {d.is_featured && <Pill className="border-win/40 text-win">Featured</Pill>}
        <span className="ml-auto font-mono text-[11px] text-faint">
          {live && d.viewers > 0 ? `${compact(d.viewers)} watching` : timeAgo(d.created_at)}
        </span>
      </div>

      <h3 className={cx("font-display my-5 font-extrabold leading-[1.02]",
        variant === "full" ? "text-[clamp(2.1rem,9vw,3rem)]" : big ? "text-[clamp(1.7rem,3.2vw,2.6rem)]" : "line-clamp-3 text-[1.45rem]")}>
        {d.question}
      </h3>

      <div className="mt-auto flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <Corner side={sideOf(d, "for")} position="for" winner={d.winner_position === "for"} />
          <span className="font-display text-sm font-bold text-faint">vs</span>
          <Corner side={sideOf(d, "against")} position="against" align="right" winner={d.winner_position === "against"} />
        </div>
        <MomentumBar share={d.momentum?.for_share ?? null} size="sm" showLabels={d.momentum !== null} />
        {live && d.status !== "lobby" && (
          <div className="flex items-end gap-4">
            <RoundRail current={d.current_round} status={d.status} className="flex-1" />
            {d.timing !== "async" && <Timer deadline={d.deadline_at} />}
          </div>
        )}
        <div className="flex items-center justify-between text-[12.5px]">
          <span className="text-faint">{d.votes > 0 ? `${compact(d.votes)} votes` : open ? "Waiting for a challenger" : " "}</span>
          <span className={cx("rounded-full px-3 py-1.5 font-semibold transition",
            open ? "bg-win text-[#0a0a0b]" : live ? "bg-text text-bg" : "border border-line-strong")}>
            {open ? "Take the other side →" : live ? "Watch & vote →" : d.status === "completed" ? "See verdict →" : "Open →"}
          </span>
        </div>
      </div>
    </Link>
  );
}

export function CardSkeleton({ variant = "grid" }: { variant?: "grid" | "hero" }) {
  return (
    <div className={cx("stage grain flex flex-col gap-4 rounded-3xl border border-line p-5", variant === "hero" ? "min-h-[300px]" : "min-h-[260px]")} aria-hidden>
      <div className="skeleton h-5 w-24" />
      <div className="skeleton h-8 w-11/12" />
      <div className="skeleton h-8 w-2/3" />
      <div className="mt-auto flex justify-between"><div className="skeleton h-9 w-32" /><div className="skeleton h-9 w-32" /></div>
      <div className="skeleton h-2 w-full rounded-full" />
    </div>
  );
}
