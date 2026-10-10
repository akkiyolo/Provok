"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { MomentumBar, RoundRail, Timer } from "@/components/arena/broadcast";
import { ClaimBoard } from "@/components/arena/claims";
import { Composer } from "@/components/arena/composer";
import { FloatingReactions, ReactionDock } from "@/components/arena/reactions";
import { RoundSection, ThinkingCard, TurnCard, TypingCard } from "@/components/arena/turns";
import { VideoStage } from "@/components/arena/video";
import { VotePanel } from "@/components/arena/vote";
import { ReportButton } from "@/components/report";
import { shareUrl, useShare } from "@/components/share";
import { useToast } from "@/components/toast";
import { Button, ErrorBlock, LiveBadge, ModelBadge, Pill, Sheet } from "@/components/ui";
import { ApiError, errorMessage, get, post } from "@/lib/api";
import { track } from "@/lib/analytics";
import { useAuth } from "@/lib/auth";
import { compact, cx, isLive, isRound, modeText, PERSONA_LABEL, sideName, sideOf, statusText } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import { type Reaction, useDebateChannel } from "@/lib/realtime";
import { type DebateView, type Position, ROUNDS } from "@/lib/types";

type WithClock = DebateView & { _offset: number };

const newer = (a: DebateView | undefined, b: DebateView) =>
  !!a?.version && !!b.version && new Date(a.version).getTime() > new Date(b.version).getTime();

export function useDebate(id: string) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["debate", id],
    queryFn: async ({ signal }) => {
      const d = await get<DebateView>(`/debates/${id}`, { signal });
      const cached = qc.getQueryData<WithClock>(["debate", id]);
      // Responses can arrive out of order (socket-triggered refetch vs. a mutation's response).
      // Never let an older snapshot replace a newer one — that would resurrect a finished turn.
      if (newer(cached, d)) return cached as WithClock;
      // Server clock − client clock, measured once per fetch (never during render).
      return { ...d, _offset: new Date(d.server_time).getTime() - Date.now() } as WithClock;
    },
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s && isLive(s) ? 30_000 : false; // backstop for missed socket events
    },
  });
}

function Corner({ debate, position }: { debate: DebateView; position: Position }) {
  const side = sideOf(debate, position);
  const isTurn = debate.expected?.position === position;
  return (
    <div className={cx("flex min-w-0 flex-1 flex-col gap-1", position === "against" && "items-end text-right")}>
      <span className={cx("font-mono text-[11px] font-bold tracking-[0.16em]", position === "for" ? "text-for" : "text-against")}>
        {position === "for" ? "FOR" : "AGAINST"}{isTurn && " · ON THE CLOCK"}
      </span>
      {side?.participant_type === "swarm" ? (
        <span className="flex flex-col gap-0.5" style={{ alignItems: position === "against" ? "flex-end" : "flex-start" }}>
          <ModelBadge model={side.model} position={position} />
          {side.persona && <span className="text-[11px] text-faint">{PERSONA_LABEL[side.persona] ?? side.persona}</span>}
        </span>
      ) : side?.user ? (
        <Link href={`/u/${side.user.username}`} className="truncate text-[15px] font-semibold hover:underline">
          {side.user.display_name} <span className="font-mono text-[11px] text-faint">{side.user.rating}</span>
        </Link>
      ) : (
        <span className="text-[15px] font-semibold text-faint">{sideName(side)}</span>
      )}
    </div>
  );
}

const noSubscribe = () => () => {};

/** The ?invite= token from a private invite link (never read during SSR, so hydration stays stable). */
function useInviteToken(): string | null {
  return useSyncExternalStore(noSubscribe, () => new URLSearchParams(window.location.search).get("invite"), () => null);
}

function Banner({ debate, onAction }: { debate: DebateView; onAction: (d: DebateView) => void }) {
  const { user, requireAuth } = useAuth();
  const toast = useToast();
  const meta = useMeta();
  const router = useRouter();
  const share = useShare();
  const [busy, setBusy] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [picked, setModel] = useState<string>("");
  const model = picked || meta?.default_model_key || "";
  const isCreator = debate.viewer?.is_creator;
  const inviteToken = useInviteToken();
  const act = async (path: string, body?: unknown, okMsg?: string) => {
    setBusy(true);
    try {
      const d = await post<DebateView>(`/debates/${debate.id}/${path}`, body);
      onAction(d);
      if (okMsg) toast(okMsg, "success");
    } catch (e) {
      if (e instanceof ApiError && e.code === "insufficient_credits") {
        toast(e.message, "error", { label: "Top up", onClick: () => router.push("/wallet") });
      } else toast(errorMessage(e), "error");
    } finally {
      setBusy(false);
    }
  };

  const shell = (children: React.ReactNode, tone: "win" | "dim" | "live" = "dim") => (
    <div className={cx("flex flex-col gap-3 rounded-3xl border p-4 sm:flex-row sm:items-center sm:p-5",
      tone === "win" ? "border-win/40 bg-win/5" : tone === "live" ? "border-live/40 bg-live/5" : "border-line bg-surface")}>
      {children}
    </div>
  );

  switch (debate.status) {
    case "waiting_for_opponent":
    case "swarm_fallback_offered": {
      const openSide = debate.sides.find((s) => !s.participant_type);
      if (isCreator) {
        const invitePath = openSide?.invite_token ? `/d/${debate.id}?invite=${encodeURIComponent(openSide.invite_token)}` : null;
        const inviteText = `I'm challenging you to a debate on Provok: "${debate.question}" Take the other side:`;
        return shell(
          <>
            <div className="flex-1">
              <p className="font-semibold">{debate.status === "swarm_fallback_offered" ? "No challenger yet." : "Waiting for a challenger…"}</p>
              <p className="text-sm text-dim">
                {openSide?.invited ? `We've pinged @${openSide.invited.username}. `
                  : invitePath ? "Send your private invite link. Only someone who has it can take the other side. "
                  : "Share the link — first to accept takes the other corner. "}
                Or bring in an AI opponent right now.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {invitePath ? (
                <>
                  <Button size="sm" variant="outline" onClick={() => {
                    track("share_clicked", { kind: "invite_link", via: "whatsapp" }, debate.id);
                    window.open(`https://wa.me/?text=${encodeURIComponent(`${inviteText} ${shareUrl(invitePath)}`)}`, "_blank", "noopener,noreferrer");
                  }}>
                    Send on WhatsApp
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => share({ title: debate.question, text: inviteText, path: invitePath, debateId: debate.id, kind: "invite_link" })}>
                    Copy invite link
                  </Button>
                </>
              ) : (
                <Button size="sm" variant="outline" onClick={() => share({ title: debate.question, text: `Take the other side: "${debate.question}"`, path: `/d/${debate.id}`, debateId: debate.id, kind: "challenge" })}>
                  Share challenge
                </Button>
              )}
              <Button size="sm" variant="primary" onClick={() => setAiOpen(true)}>Face an AI instead</Button>
              <Button size="sm" variant="ghost" loading={busy} onClick={() => act("cancel", undefined, "Debate cancelled.")}>Cancel</Button>
            </div>
            <Sheet open={aiOpen} onClose={() => setAiOpen(false)} title="Pick your AI opponent">
              <div className="flex flex-col gap-2">
                {(meta?.models ?? []).map((m) => (
                  <label key={m.key} className={cx("flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2.5", model === m.key ? "border-text bg-surface-2" : "border-line")}>
                    <input type="radio" checked={model === m.key} onChange={() => setModel(m.key)} className="accent-[var(--for)]" />
                    <span className="font-semibold">{m.display_name}</span>
                    <span className="ml-auto font-mono text-[11px] text-faint">{m.tier === "flagship" ? `${meta?.credit_costs.flagship} cr` : "1 free / cr"}</span>
                  </label>
                ))}
              </div>
              <Button className="mt-4 w-full" variant="for" loading={busy} disabled={!model}
                onClick={() => act("fallback", { model_key: model }, "Your AI opponent is in the arena.").then(() => setAiOpen(false))}>
                Start the debate
              </Button>
            </Sheet>
          </>, "win");
      }
      const invitedOther = openSide?.invited && openSide.invited.id !== user?.id;
      const needsLink = !!openSide?.invite_link && !inviteToken;
      return shell(
        <>
          <div className="flex-1">
            <p className="font-semibold">
              {invitedOther ? `This is a private challenge for @${openSide!.invited!.username}.`
                : needsLink ? "This is a private challenge." : openSide?.invite_link ? "You've been challenged." : "This corner is open."}
            </p>
            <p className="text-sm text-dim">
              {needsLink ? "Only someone with the invite link can take the other side."
                : `Take the ${openSide?.position === "for" ? "FOR" : "AGAINST"} side and the debate starts right away.`}
            </p>
          </div>
          {!invitedOther && !needsLink && (
            <Button variant={openSide?.position === "against" ? "against" : "for"} loading={busy}
              onClick={() => requireAuth("Sign in to take the other side.") && act("join", inviteToken ? { invite_token: inviteToken } : undefined, "You're in. Good luck.")}>
              Take the {openSide?.position === "for" ? "FOR" : "AGAINST"} side
            </Button>
          )}
        </>, "win");
    }
    case "lobby": {
      const mine = debate.sides.find((s) => s.user?.id === user?.id);
      return shell(
        <>
          <div className="flex-1">
            <p className="font-semibold">Pre-show. Check your camera and mic.</p>
            <p className="text-sm text-dim">The bell rings when both debaters are ready.
              {" "}{debate.sides.map((s) => `${s.position.toUpperCase()}: ${s.ready ? "ready" : "not ready"}`).join(" · ")}</p>
          </div>
          {mine && !mine.ready && <Button variant="primary" loading={busy} onClick={() => act("ready")}>I&apos;m ready</Button>}
        </>, "live");
    }
    case "judging":
      return shell(
        <div className="flex items-center gap-4">
          <span className="relative grid size-10 place-items-center">
            <span className="absolute inset-0 animate-ping rounded-full bg-win/30" />
            <span className="size-3 rounded-full bg-win" />
          </span>
          <div>
            <p className="font-semibold">The judge is deliberating.</p>
            <p className="text-sm text-dim">Checking sources, scoring every round blind, running the swap test. Final votes still count.</p>
          </div>
        </div>, "win");
    case "completed":
      return shell(
        <>
          <div className="flex-1">
            <p className="font-display text-xl font-bold">The verdict is in.</p>
            <p className="text-sm text-dim">See who the judge picked — and whether the crowd agreed.</p>
          </div>
          <Button variant="win" href={`/d/${debate.id}/verdict`}>Reveal the verdict →</Button>
        </>, "win");
    case "paused":
      return shell(<p className="text-sm text-dim">This debate is paused while we fix a technical hiccup. It resumes automatically — your progress is safe.</p>);
    case "cancelled":
    case "abandoned":
      return shell(<p className="text-sm text-dim">This debate {debate.status === "cancelled" ? "was cancelled" : "never found an opponent"}. Any credits were refunded.</p>);
    default:
      return null;
  }
}

export function Arena({ id }: { id: string }) {
  const q = useDebate(id);
  const qc = useQueryClient();
  const router = useRouter();
  const toast = useToast();
  const share = useShare();
  const [reactions, setReactions] = useState<Reaction[]>([]);
  const [claimsOpen, setClaimsOpen] = useState(false);
  const [confirmConcede, setConfirmConcede] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    // Collapse the broadcast header once the viewer scrolls into the debate (keeps phones readable).
    // Hysteresis: collapsing shortens the page, which can pull scrollY back under the threshold. A single
    // threshold then flips the header back and forth on short pages (e.g. a debate waiting for an opponent).
    const onScroll = () => setCollapsed((c) => (c ? window.scrollY > 20 : window.scrollY > 140));
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const onReaction = useCallback((r: Reaction) => {
    setReactions((rs) => [...rs.slice(-24), r]);
    setTimeout(() => setReactions((rs) => rs.filter((x) => x.id !== r.id)), 2600);
  }, []);
  const channel = useDebateChannel(id, onReaction);
  const setDebate = useCallback((d: DebateView) => {
    const cached = qc.getQueryData<WithClock>(["debate", id]);
    if (newer(cached, d)) return;
    qc.setQueryData(["debate", id], { ...d, _offset: new Date(d.server_time).getTime() - Date.now() });
  }, [qc, id]);

  const d = q.data;
  useEffect(() => {
    if (d) track("page_view", { page: "arena", status: d.status }, d.id);
  }, [d?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const openVote = useMemo(() => d?.rounds.filter((r) => r.vote_open).at(-1) ?? null, [d]);
  if (q.isError) {
    const status = q.error instanceof ApiError ? q.error.status : 0;
    return (
      <div className="mx-auto max-w-2xl px-4 py-16">
        <ErrorBlock message={status === 404 ? "This debate doesn't exist or was removed." : errorMessage(q.error)}
          retry={status === 404 ? undefined : () => q.refetch()} />
      </div>
    );
  }
  if (!d) return <ArenaSkeleton />;

  const myPos = d.viewer?.position ?? null;
  const myTurn = !!myPos && d.expected?.position === myPos && isRound(d.status) && d.timing !== "video";
  const viewers = channel.viewers ?? d.viewers;
  const live = isLive(d.status);
  const typingPos = (["for", "against"] as Position[]).find((p) => channel.typing[p] !== undefined);
  const swarmTurn = d.expected && sideOf(d, d.expected.position)?.participant_type === "swarm" && isRound(d.status);

  const concede = async () => {
    try {
      setDebate(await post<DebateView>(`/debates/${d.id}/concede`));
      toast("You conceded. Respect.", "info");
    } catch (e) {
      toast(errorMessage(e), "error");
    }
    setConfirmConcede(false);
  };

  return (
    <div className="stage-duel grain min-h-dvh pb-40">
      {/* Header */}
      <header className="sticky top-14 z-30 border-b border-line bg-bg/85 backdrop-blur-xl sm:top-16">
        <div className="mx-auto max-w-6xl px-4 py-3 sm:px-6 sm:py-4">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <button onClick={() => (history.length > 1 ? router.back() : router.push("/"))} aria-label="Back"
              className="-ml-1 grid size-8 place-items-center rounded-full text-dim hover:bg-surface-2">
              <svg viewBox="0 0 20 20" className="size-4" fill="currentColor"><path d="M12.7 4.3 7 10l5.7 5.7-1.4 1.4L4.2 10l7.1-7.1z" /></svg>
            </button>
            {live ? <LiveBadge label={d.status === "judging" ? "JUDGING" : d.status === "lobby" ? "PRE-SHOW" : "LIVE"} /> : <Pill>{d.status === "waiting_for_opponent" && d.sides.some((s) => s.invite_link || s.invited) ? "Private challenge" : statusText(d.status)}</Pill>}
            <Pill>{modeText(d.mode)}</Pill>
            {d.timing === "async" && <Pill>Async</Pill>}
            <span className="ml-auto flex items-center gap-3 font-mono text-[11px] text-faint">
              {viewers > 0 && <span>{compact(viewers)} watching</span>}
              <span className={cx("size-1.5 rounded-full", channel.connected ? "bg-ok" : "bg-faint")} title={channel.connected ? "Live updates on" : "Reconnecting"} />
            </span>
          </div>
          <h1 className={cx("font-display font-extrabold leading-[1.02] transition-all",
            collapsed ? "truncate text-base sm:text-lg" : "text-[clamp(1.35rem,4vw,2.4rem)]")}>{d.question}</h1>
          <div className={cx("mt-3 flex items-start gap-4", collapsed && "hidden")}>
            <Corner debate={d} position="for" />
            <span className="font-display pt-4 text-sm font-bold text-faint">vs</span>
            <Corner debate={d} position="against" />
          </div>
          <div className={collapsed ? "mt-2" : "mt-3"}><MomentumBar share={d.momentum?.for_share ?? null} size="sm" showLabels={!collapsed} /></div>
          {(isRound(d.status) || d.status === "judging" || d.status === "completed") && (
            <div className="mt-3 flex items-end gap-4">
              <RoundRail current={d.current_round} status={d.status} className="flex-1" />
              {isRound(d.status) && <Timer deadline={d.deadline_at} offsetMs={d._offset} urgentAt={d.timing === "async" ? 3600 : 10} className="text-base" />}
            </div>
          )}
        </div>
      </header>

      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 pt-5 sm:px-6">
        <Banner debate={d} onAction={setDebate} />

        {d.timing === "video" && (d.status === "lobby" || isRound(d.status)) && (
          <VideoStage debate={d} captions={channel.captions} speakers={channel.speakers} />
        )}

        {openVote && <VotePanel debate={d} round={openVote} offsetMs={d._offset} />}

        {ROUNDS.filter((r) => d.turns.some((t) => t.round === r) || d.current_round === r).map((r) => {
          const turns = d.turns.filter((t) => t.round === r);
          const isCurrent = d.current_round === r && isRound(d.status);
          return (
            <RoundSection key={r} round={r} debate={d}>
              <div className="flex flex-col gap-3">
                {turns.map((t) => <TurnCard key={t.id} turn={t} side={sideOf(d, t.position)} />)}
                {isCurrent && typingPos && <TypingCard position={typingPos} text={channel.typing[typingPos] ?? ""} side={sideOf(d, typingPos)} />}
                {isCurrent && swarmTurn && !typingPos && d.expected && <ThinkingCard position={d.expected.position} side={sideOf(d, d.expected.position)} />}
                {isCurrent && d.expected && !swarmTurn && !myTurn && d.timing !== "video" && (
                  <p className="rounded-2xl border border-dashed border-line px-4 py-3 text-sm text-dim">
                    Waiting for <span className={d.expected.position === "for" ? "text-for" : "text-against"}>{sideName(sideOf(d, d.expected.position))}</span>
                    {" "}to {d.expected.kind === "question" ? "ask a question" : d.expected.kind === "answer" ? "answer" : "make their case"}…
                  </p>
                )}
              </div>
            </RoundSection>
          );
        })}

        {myTurn && <Composer key={`${d.current_round}:${d.turn_index}`} debate={d} offsetMs={d._offset} onSubmitted={setDebate}
          onOpenClaims={() => setClaimsOpen(true)} />}

        {myPos && d.turns.some((t) => t.position === myPos && !t.is_forfeit) && (
          <div className="flex flex-col gap-2 rounded-3xl border border-line bg-surface p-4 sm:flex-row sm:items-center">
            <p className="flex-1 text-sm text-dim">Every vote moves your momentum bar. Bring your people.</p>
            <Button size="sm" variant={myPos === "for" ? "for" : "against"}
              onClick={() => share({ title: d.question, text: `I'm arguing ${myPos.toUpperCase()} on "${d.question}" — come vote for me ⚔️`, path: `/d/${d.id}`, debateId: d.id, kind: "vote_for_me" })}>
              Vote for me — share
            </Button>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-4 border-t border-line pt-4 text-[12px] text-faint">
          <ReportButton targetType="debate" targetId={d.id} label="Report debate" />
          {myPos && isRound(d.status) && (
            <button className="hover:text-danger" onClick={() => setConfirmConcede(true)}>Concede</button>
          )}
          <span className="ml-auto">Word limit {d.word_limit} · {d.topic_category}</span>
        </div>
      </div>

      {/* Bottom dock: claim board + reactions */}
      <div className={cx("fixed inset-x-0 bottom-0 z-40 items-center justify-center gap-2 px-3 pb-[calc(12px+env(safe-area-inset-bottom))]",
        myTurn ? "hidden" : "flex")}>
        <button onClick={() => setClaimsOpen(true)}
          className="flex h-11 items-center gap-2 rounded-full border border-line bg-surface/90 px-4 text-[13px] font-semibold shadow-xl backdrop-blur hover:bg-surface-2">
          Claim Board
          <span className="rounded-full bg-surface-3 px-1.5 font-mono text-[11px]">{d.claims.length}</span>
        </button>
        {live && <ReactionDock side={myPos} onReact={channel.sendReaction} />}
        {d.status === "completed" && (
          <motion.span initial={{ y: 30, opacity: 0 }} animate={{ y: 0, opacity: 1 }}>
            <Link href={`/d/${d.id}/verdict`} className="flex h-11 items-center rounded-full bg-win px-5 font-semibold text-[#0a0a0b] shadow-[0_0_40px_rgba(232,197,71,0.45)]">
              Reveal the verdict →
            </Link>
          </motion.span>
        )}
      </div>
      <FloatingReactions items={reactions} />

      <Sheet open={claimsOpen} onClose={() => setClaimsOpen(false)} title="Claim Board" wide>
        <ClaimBoard claims={d.claims} />
      </Sheet>
      <Sheet open={confirmConcede} onClose={() => setConfirmConcede(false)} title="Concede the debate?">
        <p className="text-sm text-dim">Your opponent wins and the judge records the concession. This can&apos;t be undone.</p>
        <div className="mt-5 flex gap-2">
          <Button variant="ghost" className="flex-1" onClick={() => setConfirmConcede(false)}>Keep fighting</Button>
          <Button variant="danger" className="flex-1" onClick={concede}>Concede</Button>
        </div>
      </Sheet>
    </div>
  );
}

export function ArenaSkeleton() {
  return (
    <div className="stage-duel grain min-h-dvh" aria-busy="true" aria-label="Loading debate">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        <div className="skeleton mb-3 h-5 w-32" />
        <div className="skeleton mb-2 h-10 w-full" />
        <div className="skeleton mb-6 h-10 w-2/3" />
        <div className="mb-6 flex justify-between"><div className="skeleton h-10 w-40" /><div className="skeleton h-10 w-40" /></div>
        <div className="skeleton mb-8 h-2 w-full" />
        <div className="flex flex-col gap-3"><div className="skeleton h-32 w-full md:w-[90%]" /><div className="skeleton h-32 w-full md:ml-[10%] md:w-[90%]" /></div>
      </div>
    </div>
  );
}
