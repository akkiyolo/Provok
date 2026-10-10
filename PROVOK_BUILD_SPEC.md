# PROVOK — Build Spec for Claude Code

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

## 3. Data model (Postgres / Supabase)

Write as SQL migrations. Enable RLS on every table.

```
profiles(id uuid pk = auth.users.id, username unique, display_name, avatar_url,
         rating int default 1200, wins int, losses int, draws int,
         free_ai_debates_used int default 0, credits int default 0,
         video_minutes_used_month int default 0, created_at)

model_registry(key text pk, litellm_id text, display_name, provider,
               tier text check in ('standard','flagship','utility','judge'),
               enabled bool, notes)

debates(id uuid pk, question text, topic_category text,
        mode text check in ('hvh','hva','ava'),
        timing text check in ('live','async','video'),
        status text,               -- see state machine
        current_round text, current_turn_index int,
        deadline_at timestamptz, created_by uuid,
        is_featured bool default false,
        word_limit int default 200,
        created_at, completed_at)

sides(id uuid pk, debate_id fk, position text check in ('for','against'),
      participant_type text check in ('human','swarm'),
      user_id uuid null, swarm_config jsonb null,
      -- swarm_config: {"model_key":"claude_opus","persona":"data_driven"}
      unique(debate_id, position))

turns(id uuid pk, debate_id fk, round text, side_id fk,
      kind text check in ('argument','question','answer'),
      content text, word_count int,
      source text check in ('typed','transcript','swarm'),
      model_key text null,          -- actual model that produced it
      moderation_status text, created_at)

claims(id uuid pk, debate_id fk, turn_id fk, side_id fk, text,
       source_url text null, responds_to_claim_id uuid null,
       status text check in ('unaddressed','rebutted','conceded','supported','unsupported','misattributed'),
       created_at)

votes(id uuid pk, debate_id fk, round text, user_id, side_id, weight numeric default 1,
      via_share_link bool default false, created_at,
      unique(debate_id, round, user_id))

verdicts(id uuid pk, debate_id fk unique, winner_side_id null, is_close bool,
         scores jsonb, per_round jsonb, reasoning text, judge_runs jsonb, created_at)

llm_calls(id, debate_id null, role text, model_key, input_tokens, output_tokens,
          cost_usd numeric, latency_ms, success bool, created_at)

credit_ledger(id, user_id, delta int, reason text, ref_id, created_at)
payments(id, user_id, razorpay_order_id, razorpay_payment_id, amount_inr, credits, status, created_at)

reports(id, reporter_id, target_type, target_id, reason, status, created_at)
follows(follower_id, followee_id, created_at)
video_sessions(id, debate_id, livekit_room, started_at, ended_at, recording_url)
clips(id, debate_id, start_ms, end_ms, reason, url, created_at)
```

**RLS rules (minimum)**
- Anyone can read public debates, sides, turns, claims, verdicts, aggregated vote counts (after round close).
- Only the side's owner can insert a turn for that side, and only via the API (service role) after engine validation. Prefer: all writes go through FastAPI with the service role; the client only reads + subscribes.
- Users can only read their own credit_ledger, payments, votes.
- Debaters cannot vote in their own debate (enforce in API + DB check).

---

## 4. Debate engine (state machine)

```
CREATED
  → WAITING_FOR_OPPONENT        (hvh only; open challenge)
      → SWARM_FALLBACK_OFFERED  (timeout; creator may accept AI opponent → mode becomes hva)
  → OPENING → REBUTTAL → CROSS_EXAM → CLOSING
  → JUDGING → COMPLETED
  (any) → ABANDONED / CANCELLED
```

**Turn order per round**
- OPENING, REBUTTAL, CLOSING: `[for, against]` (each one `argument` turn)
- CROSS_EXAM: `[for:question, against:answer, against:question, for:answer]`

**Rules**
- `engine/transitions.py` is a pure function: `(debate_state, event) -> (new_state, side_effects)`. No I/O inside. Fully unit-tested.
- Events: `turn_submitted`, `deadline_expired`, `opponent_joined`, `fallback_accepted`, `round_vote_closed`, `judging_done`, `cancelled`.
- After each round ends: open voting for that round for `ROUND_VOTE_WINDOW` (live: 30s, async: until next round ends), then close and reveal tally.
- Deadline expiry: human side → turn recorded as forfeit ("No response"), debate continues. Swarm side → retry once, then pause debate and flag.
- When it's a swarm side's turn, enqueue `swarm_turn` job immediately.
- Word limit enforced server-side (`word_limit`, default 200). Reject over-limit turns with a clear error.
- Every state change is published on Supabase Realtime channel `debate:{id}`.

**Tests required:** every valid transition, every invalid transition rejected, deadline handling for human and swarm, cross-exam ordering, fallback flow.

---

## 5. LLM gateway (LiteLLM)

`backend/app/llm/gateway.py`
- `async def complete(role, model_key, messages, stream=False, max_tokens, timeout=60, debate_id=None)`
- Resolves `model_key` → `litellm_id` via `model_registry` (cached).
- Logs every call to `llm_calls` (tokens, `litellm.completion_cost`, latency). If cost comes back 0 for a known paid model, log a warning.
- Langfuse callback enabled.
- **Fallbacks allowed ONLY for utility roles** (researcher summarisation, extraction, moderation). **Never for debater or judge roles** — if a debater model fails, retry once, then pause the debate. Model-vs-model results must be honest.
- Prompt caching: mark the system prompt + earlier debate history as cacheable for Anthropic models.
- Daily spend check: if today's `sum(cost_usd)` > `DAILY_LLM_SPEND_ALERT_USD`, send an alert (Sentry event + log) and disable new AI debates via feature flag.

**Seed model_registry** (IDs are config, verify against provider docs before launch):
- `claude_opus` → `anthropic/claude-opus-5-5` (flagship)
- `claude_sonnet` → `anthropic/claude-sonnet-5-5` (standard)
- `claude_haiku` → `anthropic/claude-haiku-4-5-20251001` (utility)
- `astra` → `openai/<GPT-6 Astra model id>` (flagship) — fill in
- `judge_primary` → `gemini/<model id>` (judge) — fill in
- Judge model must be a **different provider family** from both debaters where possible.

All prompts live as versioned files in `backend/app/llm/prompts/` (e.g. `writer.v1.md`), never inline strings.

---

## 6. AI Swarm (one swarm turn)

Pipeline per swarm turn (job `swarm_turn`):
1. **Researcher** (utility model + Tavily): on first turn of a debate, search the question for this side's position, fetch top results, extract facts with URLs into `research_cache` (per debate+position). Later turns reuse cache, with one targeted search if the strategist asks for it.
2. **Strategist** (debater model): input = question, position, round, claim ledger (own claims, opponent claims + statuses), research facts. Output JSON: `{targets: [claim_ids to attack], defend: [claim_ids], new_points: [...], cross_exam_question_target?}`.
3. **Writer** (debater model, streamed to realtime): writes the turn within the word limit, citing only URLs present in research_cache.
4. **Critic** (debater model): checks logic gaps, unsupported claims, word limit, concessions on the core position. Returns issues; writer revises once (non-streamed revision replaces streamed draft only if critic found blocking issues; otherwise stream is final).
   - For simplicity in v1: run critic **before** streaming — generate draft → critique → final, then stream the final text to the client with a typing effect. Document this choice.

**Hard rules (enforced in code, not just prompts)**
- Citations: strip any URL not in research_cache.
- Never concede the core position. System prompt: "You argue {position}. You may acknowledge a point only to rebut it."
- Personas (configurable): `data_driven`, `moral_framing`, `economic`, `contrarian`. In AVA mode, the two sides must use different personas and, by default, different models.
- Cross-exam: when asking, target the opponent's weakest unsupported/unaddressed claim; when answering, be ≤80 words and consistent with own prior claims.

---

## 7. Claim ledger + Judge

### Claim ledger (`ledger_extract` job after every turn)
Utility model extracts structured JSON from the new turn:
`[{text, source_url|null, responds_to: [existing claim ids], effect: 'rebuts'|'concedes'|'supports'|null}]`
Update statuses of referenced claims. Publish the updated ledger on realtime.

### Judge (`judge_debate` job when status = JUDGING)
1. **Citation check:** for each claim with a source URL, fetch the page (timeout, size cap) and ask the judge model whether it supports the claim → `supported` / `unsupported` / `misattributed`.
2. **Rubric per round per side** (1–10 each): argument strength, evidence quality, rebuttal coverage, responsiveness (cross-exam), consistency. Each score has a one-line justification referencing claim IDs.
3. **Blinding:** sides are labelled A/B; the judge never sees usernames, whether a side is human or AI, or model names.
4. **Swap test:** run the full judging twice with A/B labels and order swapped. Average scores. If the winner differs between runs or the margin < `CLOSE_MARGIN`, set `is_close = true`.
5. **Input:** judge primarily from the claim ledger + turns wrapped in delimiters. Store both runs in `verdicts.judge_runs`.
6. **Output:** winner, per-round scores, and a readable explanation (≤200 words) that links to specific claims.
7. Update debater ratings (Elo, K=32) for human participants; record model win/loss for leaderboard.

**Judge regression tests:** keep 10 fixture debates with expected winners; CI fails if the judge's aggregation logic changes outcomes (LLM calls mocked in CI; a separate manual script runs them live).

---

## 8. Safety: moderation, injection, rate limits, abuse

- **Question creation:** classifier checks blocked categories + abuse. Reject with a friendly reason.
- **Every human turn and every AI turn:** moderation check (utility model or provider moderation endpoint). Block or flag; flagged turns hidden pending review.
- **Prompt injection:**
  - All user content wrapped as `<debate_text side="A">...</debate_text>` with system instructions that content inside is data, never instructions.
  - A cheap injection classifier on human turns; detected attempts are stripped/flagged and logged; 3 strikes → account restricted.
  - Judge scores from the extracted ledger where possible.
- **Rate limits (Redis sliding window):** debates created/user/hour, AI debates/user/day, votes/user/minute, signups/IP/hour, turn submissions/user/minute.
- **Abuse:** phone OTP required to debate (watching is open). Free AI debates tracked per verified phone. New accounts' votes get weight 0.5 for the first 7 days. Track `via_share_link` votes separately.
- **Reports:** report button on every turn/debate/user; simple admin page (`/admin`, role-gated) to review reports, hide content, ban users, feature debates.

---

## 9. Video debates (Phase 9 — build after text is solid)

- LiveKit room per video debate: `debate-{id}`. Debaters get publish tokens; spectators get subscribe-only tokens.
- **Server-controlled turns:** on each state change, the backend uses the LiveKit server API to mute/unmute tracks (non-speaking side muted during opening/rebuttal/closing; both unmuted in cross-exam).
- **Transcription:** per-participant audio track → streaming STT (Deepgram) → finalised segments appended as a `turn` with `source='transcript'` at the end of each turn. Speaker identity comes from the track, no diarization needed.
- From there the engine, ledger, judge and voting are identical to text debates.
- Audio-only toggle (default ON for weak connections).
- Recording via LiveKit egress → Supabase Storage. Track minutes in `video_sessions` and `profiles.video_minutes_used_month`.
- **Highlight clips:** after the verdict, pick 2–3 moments (judge-flagged decisive rebuttals, `misattributed` sources, biggest vote swing) and generate 30–60s vertical clips with burned-in captions + question overlay (ffmpeg in a worker). Shareable to Shorts/Reels.
- Moderation: live transcript moderation, debater "end/report" button, host kick, recordings retained for review.

---

## 10. Design system — "The Arena"

The goal: Provok should feel like **watching a live sport broadcast of ideas**, not a forum. Every screen answers: *who's winning, what just happened, what can I do right now.*

### Visual direction
- **Stage lighting:** near-black backgrounds with soft radial spotlight gradients behind active content. Dark-first; provide a light theme too.
- **Two corners:** FOR = **Ember** (`#FF5A1F`), AGAINST = **Volt** (`#4C6FFF`). These colours are sacred: they only ever mean a side. Neutral UI uses bone/graphite.
- **Tokens (define as CSS variables, light + dark):**
  ```
  --bg: #0A0A0B; --surface: #131316; --surface-2: #1B1B20; --line: #2A2A31;
  --text: #F2EFE9 (bone); --text-dim: #9A978F;
  --for: #FF5A1F; --for-glow: rgba(255,90,31,.35);
  --against: #4C6FFF; --against-glow: rgba(76,111,255,.35);
  --live: #FF2E4D; --win: #E8C547 (gold, verdict only)
  light: --bg: #F6F4EF; --surface: #FFFFFF; --text: #121214; (side colours unchanged)
  ```
- **Type:** Bricolage Grotesque (display: questions, scores, verdicts — big, tight tracking), Geist Sans (UI/body), Geist Mono (timers, scores, stats). Questions are the hero: huge, confident type.
- **Motion (Framer Motion):** purposeful, broadcast-style. Spring physics for the momentum bar, number tickers for scores, stamp animations for claim status changes. Respect `prefers-reduced-motion`.
- **Texture:** subtle film grain overlay on stage backgrounds; thin divider lines; no generic cards-with-shadows look.

### Signature components
1. **Momentum Bar** — a horizontal tug-of-war bar between Ember and Volt showing the live audience lean (after each round closes) with spring animation. Appears on feed cards, arena header, share images.
2. **Claim Board** — side-by-side columns of claim chips. When a claim is rebutted it gets a strike-through stamp; unanswered claims pulse softly ("UNANSWERED"); `misattributed` sources get a red "SOURCE DOESN'T SAY THAT" stamp. This makes debates readable at a glance and is the most screenshot-able element.
3. **Round Rail** — 4 segments (Opening, Rebuttal, Cross-ex, Closing) with the current one lit, plus a mono countdown timer that turns `--live` red in the last 10 seconds.
4. **Live Typing Stage** — swarm turns appear with a streaming typing effect inside the side's colour-lit panel; the model name badge shows on AI sides (e.g. "CLAUDE OPUS" / "GPT-6 ASTRA" in mono caps).
5. **Verdict Reveal** — full-screen cinematic: lights dim, judge scores tick round by round, audience vote and judge verdict revealed separately, winner side floods with its colour, gold `--win` accent on the winner. Then a share sheet with the generated image.
6. **Matchup Picker** — on create, two "corner" slots side by side: tap each to choose *Me / Challenge someone / AI Swarm (pick model + persona)*. Feels like picking fighters.

### Screens
- **Home feed `/`** — mobile: full-height vertical swipe feed (one debate per screen) of live and trending debates; desktop: hero "LIVE NOW" strip + grid. Each card: question (huge), two corners with avatars/model badges, momentum bar, round rail, LIVE badge, watcher count, "Vote" and "Watch" actions. Tabs: Live · Trending · AI vs AI · Open Challenges.
- **Create `/new`** — step 1: type the question (live topic-check feedback); step 2: Matchup Picker; step 3: timing (Live / Async / Video) + word limit; step 4: confirm (shows credit cost or "Free"). Under 30 seconds end-to-end.
- **Arena `/d/[id]`** — header: question, momentum bar, round rail, timer, watchers. Body: two side panels (stacked on mobile, side-by-side desktop) showing turns per round; Claim Board in a toggleable drawer (bottom sheet on mobile). Composer for the active human debater: textarea with live word counter ring, "Submit turn". Spectators: vote buttons appear when a round's vote opens. Video mode: two video tiles framed in side colours, live captions underneath, same header/claim board.
- **Verdict `/d/[id]/verdict`** — the reveal, then the full breakdown: per-round scores, judge explanation with links to claims, audience vs judge comparison, highlight clips (video), "Rematch" and "Share".
- **Open Challenges `/challenges`** — list of questions waiting for an opponent with "Take the other side" buttons.
- **Leaderboards `/leaderboard`** — Humans (Elo), and **"Which AI argues best?"** (model win rates overall and by topic category).
- **Profile `/u/[username]`** — rating, W/L/D, debates, followers, best moments.
- **Wallet `/wallet`** — free debates left, credits, buy packs (Razorpay), history.
- **Auth** — phone OTP + Google; watching requires no login; login prompt appears at the moment of voting/debating.

### Share images (critical for growth)
- Dynamic OG images via Next.js `ImageResponse` for `/d/[id]`: question, both corners, momentum bar, current round or final verdict. Verify they render in WhatsApp and X previews.
- "Vote for me" share button after each of the user's turns, prefilled text + link.

### Quality bar
- Lighthouse mobile ≥ 90 performance on feed and arena.
- Works at 360px width without horizontal scroll.
- Skeleton states styled like the stage (no grey boxes); empty states that push action ("No live debates. Start one →").
- Accessibility: side colours are never the only signal (always paired with FOR/AGAINST labels), focus states, ARIA on the live regions.

---

## 11. API surface (FastAPI)

```
POST /debates                      create (validates topic, credits)
GET  /debates/feed?tab=            feed
GET  /debates/{id}                 full state
POST /debates/{id}/join            take open side (hvh)
POST /debates/{id}/fallback        accept AI opponent
POST /debates/{id}/turns           submit turn (engine-validated)
POST /debates/{id}/votes           vote for current open round
POST /debates/{id}/report
GET  /debates/{id}/verdict
POST /video/{id}/token             LiveKit token (role-scoped)
GET  /leaderboard?type=human|model
GET  /me/wallet ; POST /payments/order ; POST /payments/webhook (Razorpay, signature-verified)
GET  /admin/reports ; POST /admin/actions
```
Auth: verify Supabase JWT on every request. All mutations rate-limited.

---

## 12. Build phases (run one at a time)

Each phase ends with: tests passing, app running locally, `PROGRESS.md` updated, STOP.

**Phase 0 — Scaffold.** Monorepo, Next.js app with design tokens + fonts + base layout, FastAPI skeleton, ARQ worker, Supabase local, Redis via docker-compose, CI workflow, Sentry wired. *Done when:* `docker compose up` + `pnpm dev` show a styled placeholder home page and `/health` returns OK.

**Phase 1 — Data + Auth.** All migrations, RLS policies, seed `model_registry`, Supabase auth (phone OTP + Google), profile creation. *Done when:* a user can sign in and see their profile; RLS tests pass.

**Phase 2 — Debate engine.** Pure state machine + exhaustive tests, deadline jobs, realtime publishing, create/join/turn endpoints. *Done when:* two humans can complete a full text debate (async and live) via the API; tests cover all transitions.

**Phase 3 — Core UI.** Feed, Create (with Matchup Picker), Arena (text), Open Challenges, with realtime updates. Follow Section 10 precisely. *Done when:* the HvH flow works end-to-end in the browser on mobile and desktop.

**Phase 4 — LLM gateway + Swarm.** LiteLLM gateway with logging/cost, prompts as files, researcher/strategist/writer/critic, streaming to arena, HvA and AvA modes, swarm fallback for unanswered challenges. *Done when:* a human can debate an AI swarm and an AvA debate (two different models) runs to completion unattended.

**Phase 5 — Claim ledger + Judge.** Extraction after every turn, Claim Board UI, citation checking, blinded swap-test judge, verdict + Verdict Reveal screen, Elo + model leaderboard. *Done when:* every completed debate gets an explained verdict; regression fixtures pass.

**Phase 6 — Voting + Sharing.** Per-round voting with hidden tallies, vote weighting, momentum bar, OG images, share flows. *Done when:* a shared link previews correctly and votes update the momentum bar after each round.

**Phase 7 — Credits + Payments.** Free AI debate counter, credit ledger, Razorpay orders + verified webhook, wallet screen, credit checks at debate creation. *Done when:* a test-mode payment adds credits and the 4th AI debate requires credits.

**Phase 8 — Safety + Ops.** Topic/turn moderation, injection defences, rate limits, reports + admin page, daily spend alert + kill switch, uptime check. *Done when:* injection test strings are neutralised, rate limits trigger, admin can hide content.

**Phase 9 — Video.** LiveKit rooms, role tokens, server-controlled muting, per-track transcription into turns, audio-only mode, recording, minute tracking, highlight clip generation. *Done when:* two users can run a full video debate that gets transcribed, judged, and clipped.

**Phase 10 — Polish + Launch.** Performance pass, empty/loading/error states, onboarding (first debate vs AI in under 60 seconds), seed daily AI-vs-AI featured debates, analytics events (debate started/completed, votes by non-debaters, second-debate-within-7-days).

---

## 13. Launch metrics to instrument

Per mode (hvh / hva / ava / video):
- % of started debates that complete
- votes per debate from non-participants
- % of users who start a second debate within 7 days
- cost per completed debate (from `llm_calls`)
- free → paid conversion after the free AI debates are used