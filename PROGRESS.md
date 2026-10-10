# PROGRESS

_Last updated: 2026-10-10_

The v1 codebase (FastAPI + vanilla JS, preserved in `legacy/`) was rebuilt into a production
architecture. The stack choices were made with the founder: **FastAPI backend (no Supabase) + Next.js
frontend, video included, Google + email/password auth (no phone OTP).** Everything else follows
`PROVOK_BUILD_SPEC.md`.

## Status by spec phase

| Phase | Status | Notes |
|---|---|---|
| 0 Scaffold | ✅ | Next.js 16 app, FastAPI, ARQ worker, docker-compose, CI, Sentry (API + worker) |
| 1 Data + Auth | ✅ | 24 tables w/ CHECK constraints; Argon2; rotating refresh tokens w/ reuse detection; email verify/reset; Google OAuth (PKCE + nonce + JWKS) |
| 2 Debate engine | ✅ | Pure state machine (48 tests), deadlines + sweeper, realtime, all endpoints |
| 3 Core UI | ✅ | Feed (mobile swipe / desktop grid), Create + Matchup Picker, Arena, Challenges |
| 4 LLM gateway + Swarm | ✅ | LiteLLM gateway with cost logging, versioned prompts, 4-agent swarm, HvA + AvA |
| 5 Ledger + Judge | ✅ | Claim Board, citation checks (SSRF-safe), blinded swap-test judge, Elo, model leaderboard, Verdict Reveal |
| 6 Voting + Sharing | ✅ | Per-round hidden tallies, weighting, momentum bar, dynamic OG images, share flows |
| 7 Credits + Payments | ✅ | Idempotent ledger, Razorpay orders/verify/webhook, wallet |
| 8 Safety + Ops | ✅ | Topic policy, moderation, injection defences + strikes, rate limits, reports, admin, spend kill-switch, readiness check |
| 9 Video | ✅ code / ⚠️ untested live | LiveKit tokens, server-authoritative mic permissions, Deepgram STT → turns, egress recording, ffmpeg clips |
| 10 Polish + Launch | 🟡 | Empty/loading/error states, onboarding quick-start, featured AvA cron, analytics + launch metrics dashboard |

## Verified

- **163 backend tests pass** (real Postgres/Redis), ruff clean, migrations round-trip with no drift.
- **Frontend**: typecheck, lint (React Compiler rules) and production build all pass.
- **Live end-to-end run with real models** (Qwen vs GPT-OSS on Groq): a full 10-turn AvA debate ran to
  a judged verdict through the real worker, surviving free-tier rate limits via backoff + auto-resume,
  with 30 extracted claims, real citations, and a coherent explained verdict.
- SSR metadata and OG share images render (≈100 KB PNG, WhatsApp-safe).

That live run found and fixed real bugs that mocks could not: wrong Groq model id in the old `.env`,
Groq strict-JSON rejections, reasoning-model empty outputs, and a **lock bug where judging held a row
lock that blocked every child insert for minutes** (now `FOR NO KEY UPDATE` + lock-free judging, with a
regression test).

## Browser E2E (Playwright)

`apps/web/e2e` — 36 tests (desktop + mobile): first debate vs AI through to the verdict, human-vs-human
challenge → join → turns → spectator vote, auth errors, no page errors/hydration mismatches, no horizontal
scroll at 360px, security headers, share metadata. Runs in CI against the real stack with `LLM_FAKE=true`.
The browser pass found and fixed: a paywall on "debate an AI now" (flagship default), a hydration race in
the nav, a stale-response race that resurrected finished turns, a lazy-load crash on `updated_at`, the
fixed dock covering Submit, and a client-side vote rule contradicting the server.

## Database (2026-10-10)

- Dev database is now **Neon** (Postgres 18). The schema is migrated (`0001`), and the app connects
  through the `-pooler` host with `DATABASE_PGBOUNCER=true`. Run migrations against the direct (non-pooler) host.
- `DATABASE_URL` accepts libpq-style URLs as copied from Neon/Render: `sslmode` is translated to asyncpg's
  `ssl` and `channel_binding` is dropped (`core/config.py`, tested in `tests/test_config.py`).
- The old Render URL is kept commented out in `.env`; it has the legacy v1 schema.

- Live run on Neon found: Gemini 3.x Flash "thinks" inside its token budget, so short JSON replies (critic, 400 tokens)
  were truncated and the turn failed with `swarm_error`. Fixed: Gemini 2.5/3.x get the reasoning-model budget, and
  an unparseable strategist/critic reply is skipped instead of failing the turn (regression test in `test_debate_flow.py`).

## Not yet verified (needs your accounts/keys)

- **Video**: needs LiveKit + Deepgram keys and S3 storage; never exercised against real services.
- **Razorpay**: tested with mocked API + real signature math; do one test-mode purchase before launch.
- **Google sign-in**: needs an OAuth client; flow is standard but untested live.
- **Email**: only the console provider was exercised; set up Resend/SMTP and send a real reset email.
- **Real devices**: automated Chromium (desktop + Pixel 7) passes; still do a manual pass on iOS Safari.

## Decisions (spec ambiguities resolved)

- **Auth/realtime/storage** are first-party (FastAPI + Redis websockets + S3) instead of Supabase.
  "Phone OTP required to debate" → **verified email** required to debate and vote.
- **Video is HvH only** (AI can't appear on camera). A video challenge that falls back to AI becomes a live text debate.
- **Pricing**: a debate costs the flagship price if *any* AI side uses a flagship model. Free AI debates
  cover standard models only (`FREE_DEBATES_COVER_FLAGSHIP`). Accepting an AI fallback consumes a free debate/credits.
- **Vote windows**: live rounds close after 30s; async rounds stay open until the next round ends;
  the closing round has a final window (90s live / 6h async). Votes can be changed while open.
- **Swap test**: run 2 swaps the A/B labels and the order of the claim ledger; the transcript stays
  chronological (FOR always opens).
- **Critic before streaming** (spec v1 choice): draft → critique → optional revision → stream.
- **Judge rotation**: each judging attempt uses one judge for both runs; a retry may rotate to the next
  enabled judge (never mid-verdict).
- **Auto-resume**: debates paused by provider failures retry after 5 min, up to 3×/day, then wait for an admin.
- **Concession** ends the rounds; the conceding side loses without an LLM verdict.

## Launch checklist

1. **Paid LLM keys.** Free tiers (Groq 8k TPM, Gemini 20 req/day) cannot sustain real traffic.
   Add Anthropic/OpenAI keys; enable models in `/admin → Models`. Fill in the real GPT-6 Astra id or leave it disabled.
2. **Verify model ids** in `model_registry.seed.json` against provider docs (the old `.env`'s Groq id was invalid).
3. Set `DAILY_LLM_SPEND_ALERT_USD` (auto kill-switch) and Sentry DSN.
4. Production env: strong `JWT_SECRET_KEY`, `COOKIE_SECURE=true`, `TRUSTED_PROXY_COUNT`, `CORS_ORIGINS`, `EMAIL_PROVIDER=resend`.
5. **Fresh database**: the schema is new and not compatible with the legacy DB in your current `.env`.
   Point `DATABASE_URL` at a new database and run `python -m backend.app.cli migrate`.
6. Razorpay: live keys, webhook (`payment.captured`, `order.paid`, `payment.failed`), and fill the business
   details (`NEXT_PUBLIC_LEGAL_*`) shown on Terms/Privacy/Refunds/Contact. **Have a lawyer review those pages.**
7. Google OAuth client with redirect `{WEB_URL}/api/v1/auth/google/callback`.
8. Storage bucket (`STORAGE_BACKEND=s3`) and, for video, LiveKit + Deepgram + webhook.
9. Create an admin (`cli create-admin`), seed a few featured debates (`cli seed-featured`).
10. Uptime monitor on `/health/ready`; check the worker heartbeat shows `ok`.
11. Manual QA pass in real browsers (iOS Safari, Android Chrome, desktop).

## Known gaps / next up

- A Lighthouse performance pass is not done yet (production build is clean; no measurements taken).
- Sentry for the web app isn't wired (API + worker are).
- `npm audit` reports advisories in the ESLint toolchain (dev-only, not shipped).
- Push notifications (web push) are not implemented; in-app + email only.
