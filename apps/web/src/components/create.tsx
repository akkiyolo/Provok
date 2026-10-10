"use client";

import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, m } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useToast } from "@/components/toast";
import { Button, ModelBadge, SideTag } from "@/components/ui";
import { ApiError, errorMessage, get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { track } from "@/lib/analytics";
import { cx, PERSONA_LABEL } from "@/lib/format";
import { useMeta } from "@/lib/meta";
import type { DebateView, Position, PublicUser, Timing } from "@/lib/types";

type CornerType = "me" | "open" | "invite" | "link" | "swarm";
interface Corner {
  type: CornerType;
  username?: string;
  model_key?: string;
  persona?: string;
}

const SUGGESTIONS = [
  "Should AI-generated art be allowed to win art competitions?",
  "Is remote work better than the office for early-career engineers?",
  "Will electric vehicles replace petrol cars in India by 2040?",
  "Should social media be banned for under-16s?",
  "Is a four-day work week better for everyone?",
];

function useTopicCheck(question: string, enabled: boolean) {
  const [debounced, setDebounced] = useState(question);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(question.trim()), 650);
    return () => clearTimeout(t);
  }, [question]);
  return useQuery({
    queryKey: ["topic-check", debounced],
    queryFn: () => post<{ ok: boolean; reason: string | null; suggestion: string | null; category: string }>("/debates/topic-check", { question: debounced }),
    enabled: enabled && debounced.length >= 10,
    staleTime: Infinity,
    retry: false,
  });
}

function CornerSlot({ position, value, onChange, other, models, personas, defaultModel, costs }: {
  position: Position; value: Corner; onChange: (c: Corner) => void; other: Corner;
  models: { key: string; display_name: string; tier: string | null }[]; personas: { key: string }[];
  defaultModel: string | undefined; costs: { standard: number; flagship: number } | undefined;
}) {
  const [query, setQuery] = useState(value.username ?? "");
  const { data: found } = useQuery({
    queryKey: ["user-search", query],
    queryFn: () => get<{ users: PublicUser[] }>(`/search?q=${encodeURIComponent(query)}`),
    enabled: value.type === "invite" && query.length >= 2,
  });
  const options: { type: CornerType; label: string; hint: string; disabled?: boolean }[] = [
    { type: "me", label: "Me", hint: "You argue this side", disabled: other.type === "me" },
    { type: "swarm", label: "AI Swarm", hint: "Research + strategy + writer + critic" },
    { type: "open", label: "Open challenge", hint: "Anyone can take it", disabled: other.type !== "me" },
    { type: "invite", label: "Challenge someone", hint: "Invite a specific person", disabled: other.type !== "me" },
    { type: "link", label: "Invite link", hint: "Send a private link, e.g. on WhatsApp", disabled: other.type !== "me" },
  ];
  const color = position === "for" ? "for" : "against";
  return (
    <div className={cx("flex flex-col gap-3 rounded-3xl border-2 p-4 sm:p-5", position === "for" ? "border-for/50 bg-for-soft" : "border-against/50 bg-against-soft")}>
      <SideTag position={position} className="text-[12px]" />
      <div className="grid grid-cols-2 gap-2">
        {options.map((o) => (
          <button key={o.type} type="button" disabled={o.disabled}
            onClick={() => onChange(o.type === "swarm" ? { type: "swarm", model_key: value.model_key ?? defaultModel, persona: value.persona ?? (position === "for" ? "data_driven" : "moral_framing") } : { type: o.type })}
            aria-pressed={value.type === o.type}
            className={cx("flex flex-col items-start rounded-2xl border px-3 py-2.5 text-left transition disabled:opacity-35",
              value.type === o.type ? (color === "for" ? "border-for bg-for text-[#0a0a0b]" : "border-against bg-against text-white") : "border-line bg-surface hover:border-line-strong")}>
            <span className="text-[14px] font-bold">{o.label}</span>
            <span className={cx("text-[11.5px]", value.type === o.type ? "opacity-80" : "text-faint")}>{o.hint}</span>
          </button>
        ))}
      </div>
      <AnimatePresence initial={false}>
        {value.type === "swarm" && (
          <m.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="flex flex-col gap-2 overflow-hidden">
            <p className="text-[12px] font-semibold text-dim">Model</p>
            <div className="flex flex-wrap gap-2">
              {models.map((m) => (
                <button key={m.key} type="button" onClick={() => onChange({ ...value, model_key: m.key })} aria-pressed={value.model_key === m.key}
                  className={cx("rounded-full border px-3 py-1.5 font-mono text-[11.5px] font-bold uppercase tracking-[0.06em]",
                    value.model_key === m.key ? "border-text bg-text text-bg" : "border-line-strong text-dim hover:text-text")}>
                  {m.display_name}
                  <span className="ml-1.5 opacity-60">{m.tier === "flagship" ? `${costs?.flagship ?? 4} cr ★` : "free"}</span>
                </button>
              ))}
            </div>
            <p className="mt-1 text-[12px] font-semibold text-dim">Persona</p>
            <div className="flex flex-wrap gap-2">
              {personas.map((p) => (
                <button key={p.key} type="button" onClick={() => onChange({ ...value, persona: p.key })} aria-pressed={value.persona === p.key}
                  disabled={other.type === "swarm" && other.persona === p.key}
                  className={cx("rounded-full border px-3 py-1.5 text-[12.5px] font-semibold disabled:opacity-30",
                    value.persona === p.key ? "border-text bg-text text-bg" : "border-line-strong text-dim hover:text-text")}>
                  {PERSONA_LABEL[p.key] ?? p.key}
                </button>
              ))}
            </div>
          </m.div>
        )}
        {value.type === "invite" && (
          <m.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <input value={query} onChange={(e) => { setQuery(e.target.value.replace(/^@/, "")); onChange({ type: "invite" }); }}
              placeholder="Search by username" aria-label="Opponent username"
              className="h-10 w-full rounded-xl border border-line bg-surface px-3 text-sm outline-none focus:border-text/50" />
            <div className="mt-2 flex flex-col gap-1">
              {(found?.users ?? []).slice(0, 5).map((u) => (
                <button key={u.username} type="button" onClick={() => { setQuery(u.username); onChange({ type: "invite", username: u.username }); }}
                  className={cx("rounded-xl px-3 py-2 text-left text-sm", value.username === u.username ? "bg-text text-bg" : "hover:bg-surface-2")}>
                  {u.display_name} <span className="opacity-60">@{u.username}</span>
                </button>
              ))}
            </div>
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function CreateWizard() {
  const meta = useMeta();
  const { user, requireAuth, status } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const toast = useToast();
  const [step, setStep] = useState(0);
  const [question, setQuestion] = useState("");
  const [forC, setFor] = useState<Corner>({ type: "me" });
  const [againstC, setAgainst] = useState<Corner>({ type: "swarm" });
  const [timing, setTiming] = useState<Timing>("live");
  const [wordLimit, setWordLimit] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const models = useMemo(() => meta?.models ?? [], [meta]);
  const defaultModel = meta?.default_model_key ?? models.find((m) => m.tier !== "flagship")?.key ?? models[0]?.key;
  const topic = useTopicCheck(question, status === "authed");

  useEffect(() => {
    if (status === "anon") requireAuth("Create a free account to start a debate.");
  }, [status, requireAuth]);

  useEffect(() => {
    track("create_started", { quick: params.get("quick") === "1", rematch: params.get("rematch") === "1" });
    const invite = params.get("invite");
    if (invite) setTimeout(() => setAgainst({ type: "invite", username: invite }), 0);
    if (params.get("rematch") === "1") {
      try {
        const tpl = JSON.parse(sessionStorage.getItem("provok:rematch") ?? "null");
        if (tpl) {
          setTimeout(() => {
            setQuestion(tpl.question);
            setFor(tpl.for);
            setAgainst(tpl.against);
            setTiming(tpl.timing === "video" ? "video" : tpl.timing);
            setWordLimit(tpl.word_limit);
            setStep(3);
          }, 0);
        }
      } catch {
        /* ignore */
      }
    }
  }, [params]);

  // Fill in sensible AI defaults once models load.
  useEffect(() => {
    if (!models.length) return;
    const fill = (c: Corner, persona: string): Corner => (c.type === "swarm" && !c.model_key ? { ...c, model_key: defaultModel, persona: c.persona ?? persona } : c);
    setTimeout(() => {
      setFor((c) => fill(c, "data_driven"));
      setAgainst((c) => fill(c, "moral_framing"));
    }, 0);
  }, [models, defaultModel]);

  const mode = forC.type === "swarm" && againstC.type === "swarm" ? "ava" : forC.type === "swarm" || againstC.type === "swarm" ? "hva" : "hvh";
  const swarmModels = [forC, againstC].filter((c) => c.type === "swarm").map((c) => models.find((m) => m.key === c.model_key));
  const flagship = swarmModels.some((m) => m?.tier === "flagship");
  const cost = mode === "hvh" ? 0 : flagship ? meta?.credit_costs.flagship ?? 4 : meta?.credit_costs.standard ?? 1;
  const free = mode === "hvh" || ((user?.free_ai_debates_left ?? 0) > 0 && (!flagship || meta?.free_covers_flagship));
  const canAfford = free || (user?.credits ?? 0) >= cost;
  const videoAllowed = mode === "hvh" && !!meta?.features.video;
  const cornersValid = [forC, againstC].every((c) => c.type !== "invite" || !!c.username) &&
    [forC, againstC].every((c) => c.type !== "swarm" || !!c.model_key);

  useEffect(() => {
    if (timing === "video" && !videoAllowed) setTimeout(() => setTiming("live"), 0);
  }, [timing, videoAllowed]);

  const quickStart = () => {
    setFor({ type: "me" });
    setAgainst({ type: "swarm", model_key: defaultModel, persona: "contrarian" });
    setTiming("live");
    setStep(3);
  };

  const submit = async () => {
    if (!requireAuth("Sign in to start a debate.")) return;
    setBusy(true);
    setError(null);
    const body = {
      question: question.trim(), timing, word_limit: wordLimit ?? undefined,
      for: forC, against: againstC,
    };
    try {
      const d = await post<DebateView>("/debates", body);
      sessionStorage.removeItem("provok:rematch");
      track("create_step", { step: "created", mode }, d.id);
      router.push(`/d/${d.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.code === "insufficient_credits") {
        toast(e.message, "error", { label: "Top up", onClick: () => router.push("/wallet") });
      }
      setError(errorMessage(e));
      if (e instanceof ApiError && ["blocked_category", "not_debatable", "too_short", "too_long", "abusive"].includes(e.code)) setStep(0);
    } finally {
      setBusy(false);
    }
  };

  const steps = ["Question", "Matchup", "Format", "Confirm"];
  const qOk = question.trim().length >= (meta?.question_chars.min ?? 10) && topic.data?.ok !== false;

  return (
    <div className="mx-auto min-h-[85dvh] max-w-3xl px-4 pb-24 pt-6 sm:px-6">
      <ol className="mb-8 flex gap-2" aria-label="Steps">
        {steps.map((s, i) => (
          <li key={s} className="flex flex-1 flex-col gap-1.5" aria-current={i === step ? "step" : undefined}>
            <span className={cx("h-1 rounded-full", i <= step ? "bg-text" : "bg-line")} />
            <span className={cx("font-mono text-[10px] font-bold uppercase tracking-[0.14em]", i === step ? "text-text" : "text-faint")}>{s}</span>
          </li>
        ))}
      </ol>

      <AnimatePresence mode="wait">
        <m.div key={step} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.22 }}>
          {step === 0 && (
            <section>
              <h1 className="font-display text-[clamp(2rem,6vw,3.4rem)] font-extrabold leading-[0.95]">What should we fight about?</h1>
              <p className="mt-3 text-dim">Phrase it as a yes/no motion. Sharp questions make great debates.</p>
              <textarea value={question} onChange={(e) => setQuestion(e.target.value.slice(0, meta?.question_chars.max ?? 280))}
                autoFocus rows={3} placeholder="Should…" aria-label="Debate question"
                className="font-display mt-6 w-full resize-none rounded-3xl border border-line bg-surface p-5 text-[clamp(1.4rem,4vw,2rem)] font-bold leading-tight outline-none placeholder:text-faint focus:border-text/50" />
              <div className="mt-2 flex min-h-6 items-center gap-2 text-[13px]" aria-live="polite">
                {topic.isFetching && <span className="text-faint">Checking topic…</span>}
                {!topic.isFetching && topic.data?.ok && <span className="text-ok">✓ Good to go · {topic.data.category}</span>}
                {!topic.isFetching && topic.data && !topic.data.ok && (
                  <span className="text-danger">
                    {topic.data.reason}
                    {topic.data.suggestion && (
                      <button className="ml-2 font-semibold text-text underline" onClick={() => setQuestion(topic.data!.suggestion!)}>Use “{topic.data.suggestion}”</button>
                    )}
                  </span>
                )}
                <span className="ml-auto font-mono text-faint">{question.length}/{meta?.question_chars.max ?? 280}</span>
              </div>
              {!question && (
                <div className="mt-6 flex flex-wrap gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => setQuestion(s)} className="rounded-full border border-line px-3 py-1.5 text-left text-[13px] text-dim hover:border-line-strong hover:text-text">{s}</button>
                  ))}
                </div>
              )}
              <div className="mt-8 flex flex-wrap gap-3">
                <Button size="lg" disabled={!qOk} onClick={() => setStep(1)}>Pick the corners →</Button>
                {params.get("quick") === "1" && models.length > 0 && (
                  <Button size="lg" variant="for" disabled={!qOk} onClick={quickStart}>Fight an AI now</Button>
                )}
              </div>
            </section>
          )}

          {step === 1 && (
            <section>
              <h2 className="font-display text-[clamp(1.8rem,5vw,2.8rem)] font-extrabold leading-none">Pick your fighters.</h2>
              <p className="mt-3 line-clamp-2 text-dim">“{question}”</p>
              <div className="mt-6 grid gap-4 sm:grid-cols-2">
                <CornerSlot position="for" value={forC} onChange={setFor} other={againstC} models={models} personas={meta?.personas ?? []} defaultModel={defaultModel} costs={meta?.credit_costs} />
                <CornerSlot position="against" value={againstC} onChange={setAgainst} other={forC} models={models} personas={meta?.personas ?? []} defaultModel={defaultModel} costs={meta?.credit_costs} />
              </div>
              {!meta?.features.ai_debates && mode !== "hvh" && <p className="mt-3 text-sm text-danger">AI debates are paused right now — try human vs human.</p>}
              <div className="mt-8 flex gap-3">
                <Button variant="ghost" onClick={() => setStep(0)}>← Back</Button>
                <Button size="lg" disabled={!cornersValid} onClick={() => setStep(2)}>Choose the format →</Button>
              </div>
            </section>
          )}

          {step === 2 && (
            <section>
              <h2 className="font-display text-[clamp(1.8rem,5vw,2.8rem)] font-extrabold leading-none">How fast?</h2>
              <div className="mt-6 grid gap-3 sm:grid-cols-3">
                {([
                  { v: "live", t: "Live", d: `${Math.round((meta?.timings.live ?? 120) / 60)} min per turn. Watched in real time.` },
                  { v: "async", t: "Async", d: "24h per turn. Argue on your own schedule." },
                  { v: "video", t: "Video", d: "Face to face. Spoken turns, live captions.", off: !videoAllowed },
                ] as { v: Timing; t: string; d: string; off?: boolean }[]).map((o) => (
                  <button key={o.v} disabled={o.off} onClick={() => setTiming(o.v)} aria-pressed={timing === o.v}
                    className={cx("rounded-3xl border-2 p-4 text-left transition disabled:opacity-35",
                      timing === o.v ? "border-text bg-surface-2" : "border-line hover:border-line-strong")}>
                    <span className="font-display text-xl font-bold">{o.t}</span>
                    <span className="mt-1 block text-[13px] text-dim">{o.off && o.v === "video" ? "Human vs human only." : o.d}</span>
                  </button>
                ))}
              </div>
              {timing !== "video" && (
                <div className="mt-6">
                  <label className="flex items-center justify-between text-sm font-semibold" htmlFor="wl">
                    Word limit per turn <span className="font-mono">{wordLimit ?? meta?.word_limit.default ?? 200}</span>
                  </label>
                  <input id="wl" type="range" min={meta?.word_limit.min ?? 50} max={Math.min(meta?.word_limit.max ?? 500, 400)} step={10}
                    value={wordLimit ?? meta?.word_limit.default ?? 200} onChange={(e) => setWordLimit(Number(e.target.value))}
                    className="mt-3 w-full accent-[var(--for)]" />
                </div>
              )}
              <div className="mt-8 flex gap-3">
                <Button variant="ghost" onClick={() => setStep(1)}>← Back</Button>
                <Button size="lg" onClick={() => setStep(3)}>Review →</Button>
              </div>
            </section>
          )}

          {step === 3 && (
            <section>
              <p className="font-mono text-[11px] font-bold tracking-[0.2em] text-faint">READY TO START</p>
              <h2 className="font-display mt-2 text-[clamp(1.8rem,5vw,2.8rem)] font-extrabold leading-[1]">{question}</h2>
              <div className="mt-6 grid grid-cols-2 gap-3">
                {([["for", forC], ["against", againstC]] as [Position, Corner][]).map(([p, c]) => (
                  <div key={p} className={cx("rounded-2xl border p-4", p === "for" ? "border-for/50" : "border-against/50")}>
                    <SideTag position={p} />
                    <p className="mt-2 font-semibold">
                      {c.type === "me" ? "You" : c.type === "open" ? "Open challenge" : c.type === "invite" ? `@${c.username}` : c.type === "link" ? "Whoever gets your link" :
                        <ModelBadge model={models.find((m) => m.key === c.model_key) ?? null} position={p} />}
                    </p>
                    {c.type === "swarm" && c.persona && <p className="text-[12px] text-faint">{PERSONA_LABEL[c.persona]}</p>}
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-4 rounded-2xl border border-line bg-surface p-4 text-sm">
                <span className="capitalize">{timing}</span>
                <span className="text-faint">·</span>
                <span>{timing === "video" ? "Spoken turns" : `${wordLimit ?? meta?.word_limit.default ?? 200} words/turn`}</span>
                <span className="ml-auto font-semibold">
                  {mode === "hvh" ? <span className="text-ok">Free</span> : free ? <span className="text-ok">Free · {user?.free_ai_debates_left} free AI debates left</span> : (
                    <span className={canAfford ? "" : "text-danger"}>{cost} credit{cost > 1 ? "s" : ""} · you have {user?.credits ?? 0}</span>
                  )}
                </span>
              </div>
              {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
              <div className="mt-8 flex flex-wrap gap-3">
                <Button variant="ghost" onClick={() => setStep(2)}>← Back</Button>
                {canAfford ? (
                  <Button size="lg" variant="for" loading={busy} onClick={submit} disabled={!cornersValid || !qOk}>Start the debate ⚔️</Button>
                ) : (
                  <Button size="lg" variant="win" href="/wallet">Get credits to start</Button>
                )}
              </div>
            </section>
          )}
        </m.div>
      </AnimatePresence>
    </div>
  );
}
