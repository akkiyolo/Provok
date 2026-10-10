"use client";

import { animate, motion, useMotionValue, useSpring, useTransform } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { cx, formatClock } from "@/lib/format";
import { ROUND_LABEL, ROUNDS, type RoundName, type Status } from "@/lib/types";

// ── Momentum Bar ───────────────────────────────────────────────────────────

/** Tug-of-war between Ember (FOR) and Volt (AGAINST). `share` is FOR's share 0..1, or null before any round closes. */
export function MomentumBar({ share, size = "md", showLabels = true, emptyLabel = "Crowd lean revealed after each round" }: {
  share: number | null; size?: "sm" | "md" | "lg"; showLabels?: boolean; emptyLabel?: string;
}) {
  const target = share ?? 0.5;
  const mv = useMotionValue(target);
  const spring = useSpring(mv, { stiffness: 120, damping: 18, mass: 0.8 });
  const width = useTransform(spring, (v) => `${Math.round(v * 1000) / 10}%`);
  const [display, setDisplay] = useState(Math.round(target * 100));
  useEffect(() => {
    mv.set(target);
  }, [target, mv]);
  useEffect(() => spring.on("change", (v) => setDisplay(Math.round(v * 100))), [spring]);

  const h = size === "sm" ? "h-1.5" : size === "lg" ? "h-3.5" : "h-2.5";
  return (
    <div className="w-full" role="img"
      aria-label={share === null ? "Audience lean: no rounds closed yet" : `Audience lean: ${Math.round(target * 100)}% FOR, ${100 - Math.round(target * 100)}% AGAINST`}>
      {showLabels && (
        <div className="mb-1.5 flex items-center justify-between font-mono text-[11px] font-bold tracking-[0.12em]">
          <span className="text-for">FOR {share === null ? "—" : `${display}%`}</span>
          {share === null && <span className="font-sans text-[11px] font-medium tracking-normal text-faint">{emptyLabel}</span>}
          <span className="text-against">{share === null ? "—" : `${100 - display}%`} AGAINST</span>
        </div>
      )}
      <div className={cx("relative w-full overflow-hidden rounded-full bg-against", h, share === null && "opacity-40")}>
        <motion.div className="absolute inset-y-0 left-0 bg-for" style={{ width }} />
        <motion.div className="absolute inset-y-0 w-[3px] -translate-x-1/2 bg-bg" style={{ left: width }} aria-hidden />
      </div>
    </div>
  );
}

// ── Countdown ──────────────────────────────────────────────────────────────

/** Seconds left until `deadline`, corrected by `offsetMs` (server clock − client clock). */
export function useCountdown(deadline: string | null, offsetMs = 0): number | null {
  const [now, setNow] = useState(0);
  useEffect(() => {
    if (!deadline) return;
    const tick = () => setNow(Date.now());
    const raf = requestAnimationFrame(tick);
    const id = setInterval(tick, 250);
    return () => {
      cancelAnimationFrame(raf);
      clearInterval(id);
    };
  }, [deadline]);
  if (!deadline || now === 0) return null;
  return Math.max(0, (new Date(deadline).getTime() - (now + offsetMs)) / 1000);
}

export function Timer({ deadline, offsetMs = 0, urgentAt = 10, className }: {
  deadline: string | null; offsetMs?: number; urgentAt?: number; className?: string;
}) {
  const left = useCountdown(deadline, offsetMs);
  if (left === null) return null;
  const urgent = left <= urgentAt;
  return (
    <span
      className={cx("font-mono text-sm font-semibold tabular transition-colors", urgent ? "text-live" : "text-text", className)}
      aria-label={`${Math.ceil(left)} seconds left`}
    >
      {urgent && left > 0 && <span className="mr-1 inline-block size-1.5 rounded-full bg-live align-middle animate-live-dot" aria-hidden />}
      {formatClock(left)}
    </span>
  );
}

// ── Round Rail ─────────────────────────────────────────────────────────────

export function RoundRail({ current, status, className }: { current: RoundName | null; status: Status; className?: string }) {
  const currentIdx = current ? ROUNDS.indexOf(current) : -1;
  const finished = status === "judging" || status === "completed";
  return (
    <ol className={cx("grid grid-cols-4 gap-1.5", className)} aria-label="Debate rounds">
      {ROUNDS.map((r, i) => {
        const done = finished || i < currentIdx;
        const active = !finished && i === currentIdx;
        return (
          <li key={r} aria-current={active ? "step" : undefined} className="flex flex-col gap-1.5">
            <span className={cx("h-1 rounded-full transition-colors duration-500",
              active ? "bg-text shadow-[0_0_12px_rgba(242,239,233,0.5)]" : done ? "bg-dim/60" : "bg-line")} />
            <span className={cx("font-mono text-[10px] font-semibold uppercase tracking-[0.12em]",
              active ? "text-text" : done ? "text-dim" : "text-faint")}>{ROUND_LABEL[r]}</span>
          </li>
        );
      })}
    </ol>
  );
}

// ── Number ticker ──────────────────────────────────────────────────────────

export function Ticker({ value, decimals = 1, className, duration = 1.2 }: { value: number; decimals?: number; className?: string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const controls = animate(0, value, {
      duration, ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => { node.textContent = v.toFixed(decimals); },
    });
    return () => controls.stop();
  }, [value, decimals, duration]);
  return <span ref={ref} className={cx("tabular", className)}>{(0).toFixed(decimals)}</span>;
}
