"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { get } from "@/lib/api";
import type { DailyDebate } from "@/lib/types";

export interface Season {
  active: boolean;
  key?: string;
  label?: string;
  headline?: string;
  sub?: string;
  until?: string;
}

export function useSeason() {
  return useQuery({ queryKey: ["season"], queryFn: () => get<Season>("/season"), staleTime: 10 * 60_000 });
}

function Diya({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" aria-hidden className={className}>
      <path d="M24 5c3.6 5 5.4 8.6 5.4 11.6a5.4 5.4 0 0 1-10.8 0C18.6 13.6 20.4 10 24 5Z" fill="var(--festive)" />
      <path d="M24 12c1.4 2.2 2.1 3.8 2.1 5a2.1 2.1 0 0 1-4.2 0c0-1.2.7-2.8 2.1-5Z" fill="var(--text)" opacity=".85" />
      <path d="M6 26h36c-1.4 9-8.6 15-18 15S7.4 35 6 26Z" fill="currentColor" />
      <path d="M10 26c4 3 9 4.5 14 4.5S34 29 38 26" fill="none" stroke="var(--bg)" strokeWidth="1.6" opacity=".5" />
    </svg>
  );
}

const LIGHTS = 18;

/** Shown during a seasonal moment (e.g. Diwali week), on the Arena and Home feeds. Dismissal lasts for the visit. */
export function SeasonBanner({ className = "" }: { className?: string }) {
  const season = useSeason().data;
  const daily = useQuery({ queryKey: ["posts", "daily"], queryFn: () => get<{ daily: DailyDebate | null }>("/daily"),
    staleTime: 60_000, enabled: !!season?.active });
  const [hidden, setHidden] = useState(false);
  if (!season?.active || hidden) return null;
  const today = daily.data?.daily;
  const href = today?.debate ? `/d/${today.debate.id}` : "/home";
  return (
    <section aria-label={`${season.label} on Provok`}
      className={`grain relative overflow-hidden rounded-3xl border border-line bg-surface ${className}`}
      style={{ backgroundImage: "radial-gradient(60% 120% at 0% 0%, var(--festive-glow), transparent 70%)" }}>
      <div className="festive-lights pointer-events-none absolute inset-x-6 top-2 flex justify-between" aria-hidden>
        {Array.from({ length: LIGHTS }, (_, i) => (
          <span key={i} className="size-1.5 rounded-full" style={{ animationDelay: `${(i % 6) * 0.35}s` }} />
        ))}
      </div>
      <button type="button" onClick={() => setHidden(true)} aria-label="Dismiss"
        className="absolute right-3 top-5 z-10 grid size-8 place-items-center text-faint hover:text-text sm:right-5 sm:top-1/2 sm:-translate-y-1/2">✕</button>
      <div className="flex items-start gap-3 py-4 pl-4 pr-12 pt-6 sm:items-center sm:gap-5 sm:py-5 sm:pl-6 sm:pr-16 sm:pt-7">
        <Diya className="mt-0.5 size-8 shrink-0 text-faint sm:mt-0 sm:size-11" />
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[11px] font-bold tracking-[0.2em] text-festive">{season.label?.toUpperCase()} WEEK</p>
          <p className="font-display mt-0.5 text-[1.15rem] font-extrabold leading-tight sm:mt-1 sm:text-[1.6rem]">{season.headline}</p>
          <p className="mt-1 line-clamp-2 text-sm text-dim">{today ? <>Today: <span className="text-text">{today.question}</span></> : season.sub}</p>
          <Link href={href} className="mt-2 inline-block text-sm font-semibold underline-offset-4 hover:underline sm:hidden">
            {today?.debate ? "Watch today's debate →" : "See today's debate →"}
          </Link>
        </div>
        <Link href={href} className="hidden h-10 shrink-0 items-center rounded-full border border-line-strong px-4 text-sm font-semibold hover:bg-surface-2 sm:inline-flex">
          {today?.debate ? "Watch today's debate →" : "See today's debate →"}
        </Link>
      </div>
    </section>
  );
}
