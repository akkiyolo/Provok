# PROVOK ⚔️

**Ask anything. Pick your corners. Let the verdict land.**

Provok is a live arena for ideas. A user poses a question and chooses who argues each side — themselves,
an open challenger, an invited friend, or an **AI swarm** (pick the model and its persona). Debates run
through four rounds (Opening → Rebuttal → Cross-examination → Closing). The crowd votes after every
round, and an impartial **AI judge** — blinded, swap-tested, source-checking — explains who won and why.

- **Matchups:** Human vs Human (text or live video), Human vs AI, AI vs AI (model vs model).
- **Timing:** live (2-min turns), async (24h turns), video (spoken turns, live captions, recording + highlight clips).
- **Monetisation:** HvH free; first 3 AI debates free; then credits via Razorpay (UPI/cards).

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?logo=redis&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js_16-000000?logo=nextdotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![LiteLLM](https://img.shields.io/badge/LLM_gateway-LiteLLM-orange)
![License](https://img.shields.io/badge/license-MIT-green)

| Landing | Matchup picker |
|---|---|
| ![Landing page](docs/screenshots/home.png) | ![Choosing who argues each side](docs/screenshots/matchup.png) |
| **Arena (Human vs AI)** | **Verdict reveal** |
| ![Live debate arena](docs/screenshots/arena.png) | ![Round-by-round judge scores](docs/screenshots/verdict.png) |

## Engineering highlights

- **Pure, exhaustively tested state machine.** Every debate mode (live, async, video; human or AI on
  either side) runs through one side-effect-free transition function. Persistence, timers and realtime
  are layered around it, so turn order, deadlines and vote windows are fully server-authoritative.
- **Multi-agent AI debaters.** Each AI turn is a researcher → strategist → writer → critic pipeline
  with live web research; citations are enforced in code, not just by prompting.
- **Bias-resistant AI judge.** The judge is blinded to names, models and humanity, runs twice with the
  sides swapped (position-bias check), verifies cited sources (SSRF-safe fetcher), and its scores are
  aggregated by pure, regression-tested code. Results feed an Elo leaderboard of LLMs.
- **Single LLM gateway** (LiteLLM) with per-call cost logging, a DB-driven model registry, versioned
  prompts, provider fallback for utility roles, and a daily-spend kill switch.
- **Prompt-injection defences.** User text only enters prompts inside delimited, escaped blocks, with
  detection and a strike system.
- **Money-safe payments.** Append-only, idempotent credit ledger; Razorpay checkout and webhooks are
  signature-verified and amount-checked; refunds are automatic when a debate fails.
- **Production-grade auth.** Argon2 hashing, rotating refresh tokens with reuse (theft) detection,
  email verification and reset, and Google OAuth with PKCE and nonce.
- **Live video debates.** LiveKit rooms with server-controlled mic permissions; Deepgram speech-to-text
  feeds spoken turns into the same engine; recordings are cut into highlight clips with ffmpeg.
- **Tested end to end.** 160+ backend tests against real Postgres and Redis, Playwright journeys on
  desktop and mobile, and CI that runs lint, type checks, tests and a migration round-trip on every push.

**Stack:** FastAPI · SQLAlchemy 2 (async) · Alembic · PostgreSQL (Neon) · Redis · ARQ workers ·
LiteLLM · Tavily · LiveKit · Deepgram · Razorpay · Next.js 16 (App Router) · React 19 · Tailwind v4 ·
TanStack Query · Motion · Playwright · GitHub Actions · Docker

---

## Architecture

```
apps/web/            Next.js 16 · TypeScript strict · Tailwind v4 · Motion · TanStack Query
  └─ /api/v1/*  ──rewrite──►  FastAPI (same-origin → first-party refresh cookie)
  └─ wss://api…  ─────────►  FastAPI websockets (arena events, STT stream)

backend/app/
  core/          config (env-only), security (Argon2, JWT), errors, rate limiting, middleware, Redis
  db/ models/    SQLAlchemy 2 async models; Alembic migrations in backend/migrations
  engine/        transitions.py — the PURE debate state machine (no I/O); service.py persists it
  llm/           gateway.py — the ONLY path to any model (LiteLLM), registry (DB), versioned prompts
  swarm/         researcher → strategist → writer → critic (citations enforced in code)
  ledger/        claim extraction + status tracking (Claim Board)
  judge/         citation checks, blinded A/B swap-test judging, pure aggregation, Elo
  moderation/    topic policy, content moderation, prompt-injection defences
  payments/      append-only idempotent credit ledger, Razorpay orders/verify/webhooks
  video/         LiveKit tokens + server-authoritative mic permissions, Deepgram STT, ffmpeg clips
  realtime/      Redis pub/sub fan-out to websockets
  workers/       ARQ jobs: swarm turns, ledger, moderation, judging, deadlines, sweeper, spend kill-switch
  api/           HTTP routes (auth, debates, users, wallet, public, admin, video, websockets)
```

**Key properties**

- **The server is authoritative.** Turn order, deadlines, forfeits, vote windows and who may speak on
  video are decided server-side by `engine/transitions.py`, a pure function with exhaustive tests.
- **Self-healing.** Every timer is also covered by a DB-driven sweeper, every job is idempotent, debates
  paused by an AI-provider outage auto-resume, and the judge rotates to the next healthy judge on retry.
- **Honest AI results.** Debater and judge roles never silently switch models; only utility roles
  (moderation, ledger, research) fall back. The judge never sees names, models, or who is human.
- **Money is exact.** Credits live in an append-only ledger with per-event idempotency keys; payments
  are signature-verified (checkout + webhook) and amount-checked; refunds are automatic on failure.

---

## Quick start (local)

Requirements: Python 3.11+, Node 20.9+, PostgreSQL 15+, Redis 6+ (or just Docker).

### Option A — Docker (everything)

```bash
cp .env.example .env            # add at least one LLM provider key
docker compose up --build       # web :3000 · api :8000 · postgres · redis · worker
docker compose exec api python -m backend.app.cli create-admin --email you@x.com --username you --password '...'
```

### Option B — run services yourself

```bash
python -m venv .venv && .venv/Scripts/activate        # (source .venv/bin/activate on macOS/Linux)
pip install -r backend/requirements-dev.txt
cp .env.example .env                                  # set DATABASE_URL, REDIS_URL, provider keys
python -m backend.app.cli migrate
uvicorn backend.app.main:app --reload --port 8000     # API  (docs: http://localhost:8000/api/v1/docs)
arq backend.app.workers.main.WorkerSettings           # worker (separate terminal)

cd apps/web && cp .env.example .env.local && npm install && npm run dev   # http://localhost:3000
```

Useful CLI commands:

```bash
python -m backend.app.cli create-admin --email you@x.com --username you --password '...'
python -m backend.app.cli promote --username someone
python -m backend.app.cli seed-featured --count 3     # kick off featured AI-vs-AI debates
```

---

## Configuration

Everything is environment-driven — see **`.env.example`** (backend) and **`apps/web/.env.example`**.
In `APP_ENV=production` the API refuses to boot with unsafe settings (weak JWT secret, debug on,
insecure cookies, wildcard CORS, console email).

Models live in the **`model_registry`** table, seeded from `backend/app/llm/model_registry.seed.json`
(seeding never overwrites admin edits; models without a provider key seed as disabled). Manage them
at `/admin → Models`. Prompts are versioned files in `backend/app/llm/prompts/`.

---

## Testing

```bash
# backend: real Postgres + Redis, fake LLM, background jobs executed inline
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/provok_test \
TEST_REDIS_URL=redis://localhost:6379/15 pytest
ruff check backend

# frontend
cd apps/web && npm run lint && npm run typecheck && npm run build
```

The suite covers every state-machine transition, vote rules, credit accounting, judge aggregation
(10 regression fixtures), auth flows (refresh rotation & theft detection, resets), payments
(signatures, webhook idempotency, amount tampering), SSRF guards, injection defences, rate limits,
moderation, admin actions, and full HvH / HvA / AvA debates end to end. CI runs it all on every push
(`.github/workflows/ci.yml`), plus a migration up/check/down round-trip.

---

## Deploying

| Piece | Recommended | Notes |
|---|---|---|
| Web | Vercel or any Node host (`apps/web/Dockerfile`) | set `API_INTERNAL_URL` **at build time** (rewrites are baked in) |
| API | Railway / Fly.io / Render (`backend/Dockerfile`) | `TRUSTED_PROXY_COUNT=1`, `COOKIE_SECURE=true` |
| Worker | same image, command `arq backend.app.workers.main.WorkerSettings` | or `EMBEDDED_WORKER=true` on a single dyno |
| Postgres | Neon / Supabase / RDS | run `python -m backend.app.cli migrate` on each deploy. Neon URLs work as copied (`sslmode`/`channel_binding` are translated for asyncpg); with the `-pooler` host set `DATABASE_PGBOUNCER=true`, and run migrations against the direct host |
| Redis | Upstash / Railway | used for jobs, rate limits, realtime fan-out |
| Storage | S3 / R2 / Supabase Storage | avatars, recordings, clips (`STORAGE_BACKEND=s3`) |

Point an uptime monitor at `GET /health/ready` (checks DB, Redis and worker heartbeat).
Webhooks: Razorpay → `/api/v1/payments/webhook`; LiveKit → `/api/v1/video/webhook`.

See **`PROGRESS.md`** for status, decisions and the launch checklist.

## License

MIT
