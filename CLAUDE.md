# PROVOK — Build Spec for Claude Code

> **Implementation notes (2026-10-08) — these override the spec where they differ:**
> - Stack chosen with the founder: **FastAPI + Postgres + Redis + ARQ** backend (no Supabase: own auth,
>   websockets and S3 storage) and **Next.js 16** frontend in `apps/web`. Video is in scope. Auth is
>   Google + email/password (verified email replaces phone OTP).
> - Read `PROGRESS.md` first. Layout: `backend/app/{engine,llm,swarm,ledger,judge,moderation,payments,video,workers,api}`,
>   tests in `backend/tests`, migrations in `backend/migrations`. `legacy/` is the old v1 app — don't edit it.
> - `apps/web` uses Next 16 (Cache Components, `proxy.ts`, async `params`): read `apps/web/node_modules/next/dist/docs/` before changing it.
> - Run: `pytest` (needs TEST_DATABASE_URL/TEST_REDIS_URL), `ruff check backend`, and in `apps/web`: `npm run lint && npm run typecheck && npm run build`.

> Put this file in the repo root as `PROVOK_BUILD_SPEC.md` and also copy Sections 0–2 into `CLAUDE.md`.
> Then run Claude Code **one phase at a time** (Section 12). Do not ask it to build everything in one go.

---

## 0. Instructions to Claude Code (read first)

You are building **Provok**, a social debate platform. Follow these rules for the entire project:

1. **Work phase by phase** (Section 12). At the end of each phase: run tests, run the app, update `PROGRESS.md` (what's done, what's stubbed, known issues), then STOP and wait for me.
2. **Never hardcode model IDs, prices, limits or feature flags.** Everything goes through `config` / env vars / the `model_registry` table.
3. **The server is authoritative.** Debate state, timers, turn order, mute state and votes are decided server-side only. The client renders state, it never decides it.
4. **One debate engine for all modes.** A side is `human` or `swarm`. Live/async/video differ only in config (deadlines, input channel). Never fork the engine per mode.
5. **Every LLM call goes through the single LLM gateway** (`backend/app/llm/gateway.py`, built on LiteLLM) and is logged to `llm_calls` with cost.
6. **User text is untrusted data.** Never place human debate content into a prompt outside of explicit delimiters. Apply the injection defences in Section 8.
7. **Write tests for the state machine, vote rules, credit accounting and judge aggregation.** These are the parts that must never break.
8. **Type everything.** TypeScript strict on the frontend, Pydantic models + type hints on the backend.
9. If a requirement is ambiguous, pick the simplest option, note it in `PROGRESS.md`, and continue.
10. Follow the design system in Section 10 exactly. Do not fall back to default shadcn/Tailwind styling.

---

## 1. Product summary

Provok: a user poses a question, chooses who argues each side, and the audience plus an AI judge decide who made the stronger case.

**Matchups**
- Human vs Human (text, or live audio/video)
- Human vs AI Swarm
- AI Swarm vs AI Swarm (including model-vs-model, e.g. "GPT-6 Astra vs Claude")

**Format** (every debate): Opening → Rebuttal → Cross-examination → Closing → Verdict.
- Audience votes after each round (tally hidden until the round closes).
- Final verdict = AI judge (evidence-based, explained) shown **separately** from audience vote.

**Timing modes**
- `live`: short turn deadlines (default 120s text / 90s speech per turn)
- `async`: long turn deadlines (default 24h)
- `video`: live, face-to-face via LiveKit; speech is transcribed and fed into the same engine

**Monetisation**
- Human vs Human: always free (text). Video: free, with a configurable monthly minute cap (`VIDEO_FREE_MINUTES_PER_MONTH`, default unlimited).
- AI modes: first `FREE_AI_DEBATES` (default 3) free per user, then paid via credits.
- Credits: standard-model debate = 1 credit, flagship-model debate = `FLAGSHIP_CREDIT_COST` (default 4).
- Packs via Razorpay (UPI/cards). Watching and voting are always free.

**Launch topic policy:** block politics, religion, caste and other high-conflict categories at question creation (configurable list).

---

## 2. Tech stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router, latest stable), TypeScript strict, Tailwind CSS, shadcn/ui (heavily restyled), Framer Motion, TanStack Query |
| Backend API | FastAPI (Python 3.12), Pydantic v2 |
| Workers / timers | ARQ (Redis) — AI turns, deadlines, judging, clip generation |
| DB / Auth / Realtime | Supabase: Postgres, Auth (phone OTP + Google), Realtime, Row Level Security, Storage |
| LLM gateway | LiteLLM (Python SDK) |
| Web research | Tavily API (behind an interface so it can be swapped) |
| Video | LiveKit (Cloud) + per-track speech-to-text (Deepgram, behind an interface) |
| Payments | Razorpay (orders + webhooks) |
| Rate limiting | Redis (Upstash in prod) sliding window |
| Observability | Sentry (web + API), Langfuse (LiteLLM callback) |
| Hosting | Vercel (web), Railway or Fly.io (API + worker), Supabase Cloud |
| CI | GitHub Actions: lint, typecheck, tests on every push |

### Repo layout
```
provok/
  apps/web/                 # Next.js app
  backend/
    app/
      api/                  # FastAPI routers
      engine/               # state machine, transitions, deadlines
      llm/                  # gateway, model registry, prompts/
      swarm/                # researcher, strategist, writer, critic
      ledger/               # claim extraction
      judge/                # citation check, scoring, aggregation
      moderation/           # content + injection checks
      payments/             # credits, razorpay
      video/                # livekit rooms, transcription
      workers/              # ARQ tasks
    tests/
  supabase/migrations/
  .github/workflows/
  PROGRESS.md
  CLAUDE.md
```

### Environment variables
```
SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY
REDIS_URL
OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY
TAVILY_API_KEY
LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
SENTRY_DSN_WEB, SENTRY_DSN_API
RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET
LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
DEEPGRAM_API_KEY
FREE_AI_DEBATES=3
FLAGSHIP_CREDIT_COST=4
VIDEO_FREE_MINUTES_PER_MONTH=
DAILY_LLM_SPEND_ALERT_USD=
BLOCKED_TOPIC_CATEGORIES=politics,religion,caste
```

---