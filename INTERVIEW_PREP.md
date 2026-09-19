# PROVOK — The Definitive Technical Interview & Engineering Architecture Manual

> **Project Name:** PROVOK (AI-Driven Adversarial & Deliberative Arena)  
> **Repository Root:** `d:\Provok`  
> **Authors:** Engineering Team & Antigravity AI  
> **Target Audience:** Technical Interviewers, Staff/Principal Engineers, System Architects, Lead Developers  
> **Document Purpose:** Complete, exhaustive, line-level and architecture-level reference covering every module, data pipeline, state machine, concurrency pattern, AI orchestration flow, database constraint, security guardrail, and interview question.

---

# TABLE OF CONTENTS
1. [Executive Summary & High-Level Philosophy](#1-executive-summary--high-level-philosophy)
2. [End-to-End System Architecture](#2-end-to-end-system-architecture)
3. [Complete Codebase Directory & File Inventory](#3-complete-codebase-directory--file-inventory)
4. [Deep-Dive Module Breakdown (Line-by-Line & Function-by-Function)](#4-deep-dive-module-breakdown)
   - [4.1 Entry Point & Lifecycle (`backend/app/main.py`)](#41-entry-point--lifecycle-backendappmainpy)
   - [4.2 Configuration Engine (`backend/app/config.py`)](#42-configuration-engine-backendappconfigpy)
   - [4.3 Database Layer & PgBouncer Optimization (`backend/app/database/core.py`)](#43-database-layer--pgbouncer-optimization-backendappdatabasecorepy)
   - [4.4 Data Models & Relational Schema (`backend/app/models/debate.py` & `user.py`)](#44-data-models--relational-schema)
   - [4.5 Rate Limiting & Cost Guardrails (`backend/app/limiter.py`)](#45-rate-limiting--cost-guardrails-backendapplimiterpy)
   - [4.6 Real-Time WebSocket Infrastructure (`backend/app/websockets/manager.py`)](#46-real-time-websocket-infrastructure-backendappwebsocketsmanagerpy)
   - [4.7 Finite State Machine Engine (`backend/app/debate/state_machine.py`)](#47-finite-state-machine-engine-backendappdebatestate_machinepy)
   - [4.8 Autonomous Agent-vs-Agent Debate Orchestrator (`backend/app/ai/agent_debate.py`)](#48-autonomous-agent-vs-agent-debate-orchestrator-backendappaiagent_debatepy)
   - [4.9 Human vs. AI Swarm LangGraph Engine (`backend/app/ai/swarm.py`)](#49-human-vs-ai-swarm-langgraph-engine-backendappaiswarmpy)
   - [4.10 Forensic AI Verdict Generator (`backend/app/verdict/generator.py`)](#410-forensic-ai-verdict-generator-backendappverdictgeneratorpy)
   - [4.11 Async Worker Tier & Resilient Task Dispatching (`backend/app/workers/`)](#411-async-worker-tier--resilient-task-dispatching-backendappworkers)
   - [4.12 API Routers (`backend/app/api/`)](#412-api-routers-backendappapi)
   - [4.13 Client Architecture & Dynamic Frontend (`frontend/`)](#413-client-architecture--dynamic-frontend-frontend)
5. [The 5 Core Execution Pipelines (Packet Traces & Step-by-Step Dataflows)](#5-the-5-core-execution-pipelines)
   - [Pipeline 1: User Onboarding, Authentication & JWT Lifecycle](#pipeline-1-user-onboarding-authentication--jwt-lifecycle)
   - [Pipeline 2: Debate Creation & Atomic Participant Initialization](#pipeline-2-debate-creation--atomic-participant-initialization)
   - [Pipeline 3: Autonomous Agent vs. Agent 4-Round Match](#pipeline-3-autonomous-agent-vs-agent-4-round-match)
   - [Pipeline 4: Human vs. AI Swarm Reactive Deliberation](#pipeline-4-human-vs-ai-swarm-reactive-deliberation)
   - [Pipeline 5: AI Judge Verdict Synthesis & Multi-Criteria Scoring](#pipeline-5-ai-judge-verdict-synthesis--multi-criteria-scoring)
6. [The 8 Production "War Stories" (Bugs, Root Causes, Diagnostics & Fixes)](#6-the-8-production-war-stories)
7. [Comprehensive Master Interview Question Bank (50+ Questions with Answers)](#7-comprehensive-master-interview-question-bank)
   - [Category 1: Distributed Systems, WebSockets & Concurrency](#category-1-distributed-systems-websockets--concurrency)
   - [Category 2: Python 3.12, Asyncio & FastAPI Deep Internals](#category-2-python-312-asyncio--fastapi-deep-internals)
   - [Category 3: LLM Engineering, Multi-Agent Swarms & LiteLLM](#category-3-llm-engineering-multi-agent-swarms--litellm)
   - [Category 4: Database Architecture, PgBouncer, ACID & ORM](#category-4-database-architecture-pgbouncer-acid--orm)
   - [Category 5: Security, Rate Limiting & Denial-of-Wallet Defense](#category-5-security-rate-limiting--denial-of-wallet-defense)
   - [Category 6: Behavioral, Leadership & STAR Technical Scenarios](#category-6-behavioral-leadership--star-technical-scenarios)

---

# 1. EXECUTIVE SUMMARY & HIGH-LEVEL PHILOSOPHY

### What is PROVOK?
**PROVOK** is an enterprise-grade deliberative debate platform engineered to transform unstructured online arguments into rigorous, structured, and forensically evaluated intellectual competitions. 

Modern internet discussion platforms (Twitter/X, Reddit, comment threads) suffer from three fatal structural flaws:
1. **Lack of Structure**: Conversations branch uncontrollably, devolve into ad hominem attacks, and abandon the original thesis.
2. **Cognitive Echo Chambers & Position Bias**: Participants argue to "win" in front of their tribe rather than seeking dialectical truth.
3. **Absence of Objective Forensic Evaluation**: There is no objective arbiter to score rhetorical validity, evidence citations, or logical fallacies.

### How PROVOK Solves This
PROVOK enforces a strict, deterministic **4-Round Finite State Machine (FSM)**:
- **Round 1: Opening Statements** (Establish baseline thesis, axioms, and primary evidence).
- **Round 2: Rebuttal** (Target opponent's claims, dismantle premises, expose contradictions).
- **Round 3: Cross-Examination** (Socratic probing, direct adversarial questions and mandatory answers).
- **Round 4: Closing Arguments** (Synthesis, impact comparison, final persuasive defense).

PROVOK supports two distinct dialectical formats:
1. **Human vs. AI Swarm**: A human user takes a stance (`FOR` or `AGAINST`) and debates an orchestrated multi-agent LangGraph Swarm comprising a real-time web researcher (Tavily API), a strategic logician, a skeptic, and a persuasive lead orator.
2. **Autonomous Agent vs. Agent**: Two distinct foundation LLMs debate each other with zero human intervention. Side `FOR` is driven by Groq's high-speed `qwen/qwen3.6-27b` reasoning model, while Side `AGAINST` is driven by Google's analytical `gemini-3.6-flash`. The debate streams live to spectators via WebSockets.

Upon conclusion, an impartial **AI Forensic Judge** evaluates the complete debate transcript across a mathematical rubric (Logic 40%, Evidence 30%, Rhetoric 20%, Fallacy Penalty -10%), determines the winning side, calculates an empirical consensus score (0-100), isolates the decisive **Turning Point**, and generates a structured verdict.

---

# 2. END-TO-END SYSTEM ARCHITECTURE

```
+----------------------------------------------------------------------------------------------------+
|                                      CLIENT TIER (Frontend)                                        |
|  - Modern Vanilla ES6+ SPA Architecture (Zero Node.js build overhead, instant load, cache-busted) |
|  - Design System: Custom CSS Tokens, Glassmorphism, Responsive Grid/Flexbox Layout                 |
|  - Realtime Layer: Native WebSocket client with 20s ping/pong heartbeat & auto-reconnect           |
|  - Pages: index.html (Feed), ask.html (Creator), debate.html (Arena), verdict.html (Forensics)     |
+--------------------------------------------------+-------------------------------------------------+
                                                   |
                             HTTPS / REST          |  WSS / WebSockets
                             (JSON Payloads)       |  (Bidirectional Realtime Events)
                                                   v
+----------------------------------------------------------------------------------------------------+
|                                    GATEWAY & APPLICATION TIER                                      |
|  FastAPI (Python 3.12 ASGI / Uvicorn Server)                                                       |
|  |                                                                                                |
|  +--> SlowAPI Middleware: Client-IP token-bucket rate limiting (DoW protection on LLM calls)       |
|  +--> Security Middleware: X-Content-Type-Options: nosniff, X-Frame-Options: DENY, HSTS, CSP       |
|  +--> Tracing Middleware: Unique UUIDv4 X-Request-ID attached to Request.state & Response headers |
|  +--> Lifespan Manager: Redis connection validation, Pub/Sub listener background task bootstrap  |
|  +--> Observability: Structlog zero-allocation JSON logs + Sentry APM error tracking               |
+--------------------------------------------------+-------------------------------------------------+
                                                   |
                 +---------------------------------+---------------------------------+
                 v                                                                   v
+--------------------------------------------------+        +----------------------------------------+
|                 PERSISTENCE TIER                 |        |          MESSAGE BROKER TIER           |
|  PostgreSQL 16 (Neon Cloud Serverless)           |        |  Redis 7.0 (In-Memory Data Store)      |
|  - Async Engine: SQLAlchemy 2.0 via `asyncpg`    |        |  - Channel `debates:{id}`: Pub/Sub WS  |
|  - PgBouncer Pooling: statement_cache_size = 0   |        |  - Celery Broker: Redis DB 3           |
|  - Connection Recycling: pool_recycle = 300s     |        |  - Celery Result Backend: Redis DB 4   |
|  - Schema Migrations: Alembic via `psycopg` sync |        |  - Graceful Fallback to Local Memory   |
+--------------------------------------------------+        +-------------------+--------------------+
                                                                                |
                                                                                v
+----------------------------------------------------------------------------------------------------+
|                                      ASYNC WORKER CLUSTER                                          |
|  Celery Distributed Workers                                                                        |
|  - Queue `ai`: Long-running 4-round autonomous debates & LangGraph multi-agent swarm tasks         |
|  - Queue `verdict`: Forensic AI verdict scoring and database upserts                               |
|  - Queue `embedding`: pgvector semantic embeddings (Google text-embedding-004)                   |
|  - Resilient Dispatcher: Attempts Celery `.delay()`; falls back to FastAPI BackgroundTasks if offline|
+--------------------------------------------------+-------------------------------------------------+
                                                   |
                                                   v
+----------------------------------------------------------------------------------------------------+
|                                   ARTIFICIAL INTELLIGENCE TIER                                     |
|  LiteLLM Unified Multi-Provider Abstraction                                                       |
|  +--> Side FOR: Groq Cloud -> `groq/qwen/qwen3.6-27b` (Max 850 tokens, OTPM rate guard)           |
|  +--> Side AGAINST: Google DeepMind -> `gemini/gemini-3.6-flash` (Analytical counter-orator)       |
|  +--> Swarm Graph: LangGraph Cyclic Graph (Researcher [Tavily] -> Strategist -> Skeptic -> Orator)|
|  +--> Judge Engine: Gemini 3.6 Flash (Forensic 4-tier rubric with JSON schema enforcement)         |
|  +--> Sanitizer: Multi-pass regex & delimiter stripper for `<think>...</think>` scratchpad tokens  |
+----------------------------------------------------------------------------------------------------+
```

---

# 3. COMPLETE CODEBASE DIRECTORY & FILE INVENTORY

```
d:\Provok\
├── .env                                # Active runtime environment secrets & configuration
├── .env.example                        # Template environment variables for onboarding
├── .gitignore                          # Git exclude rules (.venv, pycache, media, .env)
├── Dockerfile                          # Production multi-stage Docker build (provok non-root user)
├── docker-compose.yml                  # Local development orchestration (App, Redis, Postgres)
├── pytest.ini                          # Pytest configuration (asyncio mode auto)
├── requirements.txt                    # Top-level pinned dependencies
├── INTERVIEW_PREP.md                   # THIS DOCUMENT (Master Interview & Architecture Manual)
├── backend\
│   ├── requirements.txt                # Backend dependencies (FastAPI, SQLAlchemy, LiteLLM, Celery)
│   └── app\
│       ├── __init__.py                 # Package marker
│       ├── config.py                   # Pydantic BaseSettings class with environment mapping
│       ├── dependencies.py             # FastAPI dependency injection (DbSession, CurrentUser)
│       ├── limiter.py                  # SlowAPI rate limiter instance and configuration
│       ├── logging_config.py           # Structlog JSON structured logging configuration
│       ├── main.py                     # FastAPI entrypoint, middlewares, lifespan, route mounts
│       ├── agents\                     # Specialized agent role definitions
│       ├── ai\
│       │   ├── agent_debate.py         # Autonomous 4-round Agent-vs-Agent debate orchestrator
│       │   └── swarm.py                # LangGraph cyclic multi-agent swarm (Human vs AI)
│       ├── api\
│       │   ├── __init__.py
│       │   ├── auth.py                 # User registration, login, JWT issuance, Google OAuth
│       │   ├── debates.py              # Debate CRUD, turn submission, voting, challenges
│       │   ├── feed.py                 # Public feeds, trending debates, topic filters
│       │   └── users.py                # User profile, statistics, stance history
│       ├── auth\
│       │   └── security.py             # Password hashing (bcrypt/argon2), JWT encode/decode
│       ├── database\
│       │   └── core.py                 # Async SQLAlchemy engine, sessionmaker, PgBouncer config
│       ├── debate\
│       │   └── state_machine.py        # 4-round Finite State Machine (FSM) validation engine
│       ├── models\
│       │   ├── debate.py               # 15 relational tables & 11 Enums for debate domain
│       │   └── user.py                 # User & OAuthAccount models
│       ├── schemas\
│       │   ├── auth.py                 # Pydantic v2 schemas for auth requests/responses
│       │   ├── debate.py               # Pydantic v2 schemas for debate creation, turns, verdicts
│       │   └── user.py                 # Pydantic v2 schemas for user profiles
│       ├── storage\
│       │   └── s3.py                   # AWS S3 file upload manager with local mock fallback
│       ├── tests\
│       │   ├── test_api.py             # Basic health check and import verification
│       │   ├── test_api_integration.py # End-to-end HTTP integration tests
│       │   ├── test_auth.py            # Password hashing & JWT generation tests
│       │   ├── test_models.py          # SQLAlchemy model unit tests
│       │   ├── test_rate_limiting.py   # SlowAPI 429 throttling assertion test
│       │   ├── test_storage.py         # S3 mock fallback unit tests
│       │   └── test_verdict.py         # Verdict prompt structure & forensic rubric test
│       ├── verdict\
│       │   └── generator.py            # Forensic AI judge synthesis & idempotent upsert
│       ├── websockets\
│       │   └── manager.py              # WebSocket ConnectionManager with Redis Pub/Sub fanout
│       └── workers\
│           ├── celery_app.py           # Celery application instance and queue routing
│           └── ai_tasks.py             # Celery background tasks & resilient dispatchers
└── frontend\
    ├── index.html                      # Landing page & public debate feed
    ├── ask.html                        # Debate creation wizard (Select topic, stance, opponent)
    ├── debate.html                     # Live debate arena with real-time argument streaming
    ├── verdict.html                    # Post-debate forensic verdict & analytics dashboard
    ├── profile.html                    # User profile, debate history, win/loss record
    ├── login.html                      # Authentication portal
    ├── css\
    │   ├── variables.css               # Design tokens (Colors, typography, shadows, borders)
    │   ├── base.css                    # CSS Reset, typography base, body styling
    │   ├── layout.css                  # Grid layouts, navigation header, containers
    │   ├── components.css              # Buttons, cards, form inputs, modal dialogs
    │   ├── debate.css                  # Arena styling, message bubbles, active speaker banner
    │   └── verdict.css                 # Forensic scorecard, radar chart layout, winner banner
    └── js\
        ├── api.js                      # Centralized fetch wrapper with JWT token handling
        ├── auth.js                     # Token storage, auth guard, logout handler
        ├── router.js                   # Client-side hash/history route helpers
        ├── utils.js                    # Formatting helpers (dates, strings, avatars)
        ├── websocket.js                # Reusable WebSocket wrapper with auto-reconnect
        └── pages\
            ├── ask.js                  # Debate wizard logic & form validation
            ├── debate.js               # Arena WebSocket event listener, UI rendering, ping loop
            ├── feed.js                 # Feed loading, infinite scroll, topic filtering
            ├── home.js                 # Homepage hero interactions
            ├── login.js                # Login form submission & token storage
            ├── profile.js              # User statistics binding
            └── verdict.js              # Verdict polling, metrics rendering, score visualization
```

---

# 4. DEEP-DIVE MODULE BREAKDOWN

## 4.1 Entry Point & Lifecycle (`backend/app/main.py`)
`main.py` is the operational nucleus of the application. It configures the FastAPI instance, mounts middlewares, controls lifecycle lifespan hooks, and binds static assets.

### Lifespan Context Manager (`lifespan`)
- **Async Lifespan Protocol**: Replaces deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")`.
- **Startup Sequence**:
  1. Initializes `structlog` via `setup_logging()`.
  2. Connects to Redis via `aioredis.from_url(settings.redis_url)`.
  3. Executes `await app.state.redis.ping()` to verify connectivity.
  4. Spawns the background Redis Pub/Sub listener task: `asyncio.create_task(manager.start_redis_listener(app.state.redis))`.
  5. **Graceful Redis Degradation**: If Redis is offline, catches the exception, logs a warning, sets `app.state.redis = None`, and falls back to local in-memory WebSockets.
- **Shutdown Sequence**:
  1. Cancels the background WebSocket listener task.
  2. Awaits `app.state.redis.close()`.
  3. Logs clean shutdown confirmation.

### Middleware Chain (Execution Order)
1. **Sentry APM**: Conditional hookup if `settings.sentry_dsn` is provided. Intercepts exceptions and records request traces.
2. **CORSMiddleware**: Dynamic origins. If `settings.debug=True`, allows `["*"]`. In production, splits comma-delimited `settings.allowed_origins`.
3. **SlowAPIMiddleware**: Evaluates incoming request IP against route limits.
4. **Security & Tracing Middleware (`security_and_tracing`)**:
   - Generates a `uuid.uuid4()` request ID and attaches it to `request.state.request_id`.
   - Records high-resolution start time via `time.perf_counter()`.
   - Injects security response headers:
     - `X-Request-ID`: Distributed tracing identifier.
     - `X-Content-Type-Options: nosniff`: Prevents MIME-sniffing exploits.
     - `X-Frame-Options: DENY`: Prevents clickjacking in iframes.
     - `Referrer-Policy: strict-origin-when-cross-origin`.
     - `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
     - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (in production).
     - `Cache-Control: no-cache, no-store, must-revalidate` (in debug mode).
   - Calculates duration and logs any request taking longer than 1,000ms as a `slow_request` warning.

---

## 4.2 Configuration Engine (`backend/app/config.py`)
Powered by Pydantic v2's `BaseSettings` (`pydantic-settings`). Every setting is read from environment variables or the `.env` file with automatic type coercion, default values, and strict validation.

### Critical Settings Categories
- **Database**:
  - `database_url`: Raw connection string.
  - `database_pool_size`: 10 connections.
  - `database_max_overflow`: 10 burst connections.
  - Dynamic Property `async_database_url`: Converts `postgresql://` to `postgresql+asyncpg://`. Uses regex to strip incompatible query params:
    ```python
    url = re.sub(r"[&?]channel_binding=[^&]*", "", url)
    url = re.sub(r"[&?]sslmode=[^&]*", "", url)
    ```
    *Why?* Neon cloud URLs include `sslmode=require` and `channel_binding`, which `psycopg2` accepts but `asyncpg` rejects as unhandled keywords.
  - Dynamic Property `sync_database_url`: Converts `postgresql://` to `postgresql+psycopg://` for Alembic migrations.
- **AI Models & Keys**:
  - `groq_api_key`: API key for Groq Cloud.
  - `groq_model`: `"groq/qwen/qwen3.6-27b"` (Primary Side `FOR` orator).
  - `gemini_model`: `"gemini/gemini-3.6-flash"` (Primary Side `AGAINST` orator and Forensic Judge).
  - `llm_max_tokens`: 4000 baseline.
- **Rate Limits**:
  - `rate_limit_enabled: bool = True`
  - `rate_limit_login: str = "10/minute"`
  - `rate_limit_register: str = "5/minute"`
  - `rate_limit_create_debate: str = "10/hour"`
  - `rate_limit_argument: str = "30/hour"`
- **Observability**:
  - `sentry_dsn: str = ""`
  - `sentry_traces_sample_rate: float = 0.2`

---

## 4.3 Database Layer & PgBouncer Optimization (`backend/app/database/core.py`)

### The PgBouncer Transaction Pooling Problem
Neon serverless PostgreSQL utilizes **PgBouncer** in transaction pooling mode. Under transaction pooling:
1. A client checks out a physical Postgres server connection only for the duration of a transaction.
2. Subsequent queries within the same application session may be executed on entirely different server backends.
3. Standard `asyncpg` prepares SQL statements and assigns them internal identifiers (e.g., `__asyncpg_stmt_1__`).
4. If `asyncpg` caches this prepared statement and sends its ID to a *different* physical backend connection that hasn't prepared it, PostgreSQL throws:
   `PreparedStatementDoesNotExistError: prepared statement "__asyncpg_stmt_1__" does not exist`
   or if already prepared:
   `DuplicatePreparedStatementError: prepared statement already exists`.

### The Solution in `core.py`
```python
engine = create_async_engine(
    settings.async_database_url,
    echo=False,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_recycle=300,  # Recycle connection every 5 minutes to prevent stale dropped TCP sockets
    connect_args={
        "statement_cache_size": 0,  # CRITICAL: Disables asyncpg prepared statement caching
    }
)
```
- Setting `statement_cache_size: 0` forces `asyncpg` to execute queries via simple protocol or anonymous statements, completely resolving prepared statement collisions in PgBouncer.

---

## 4.4 Data Models & Relational Schema
Defined in `backend/app/models/debate.py` and `user.py` using SQLAlchemy 2.0 Declarative Mapped columns.

### Core Domain Entities & Relationships
1. **`User`** (`users` table):
   - `id`: UUID (Primary Key).
   - `email`: `VARCHAR(255)`, Unique, Indexed.
   - `username`: `VARCHAR(50)`, Unique, Indexed.
   - `password_hash`: `VARCHAR(255)` (Bcrypt/Argon2).
   - `is_active`: Boolean.
   - Relationships: `debates_created`, `participants`, `votes`.
2. **`Question`** (`questions` table):
   - The proposition being debated (e.g., *"Will artificial general intelligence lead to human obsolescence?"*).
   - `text`: `VARCHAR(500)`.
   - `category`: `VARCHAR(100)`.
3. **`Debate`** (`debates` table):
   - `id`: UUID.
   - `question_id`: Foreign Key -> `questions.id`.
   - `creator_id`: Foreign Key -> `users.id` (Nullable for system debates).
   - `debate_type`: Enum (`HUMAN_VS_HUMAN`, `HUMAN_VS_AI`, `AI_VS_AI`).
   - `mode`: Enum (`LIVE`, `ASYNC`).
   - `status`: Enum (`DRAFT`, `READY`, `LIVE`, `WAITING`, `PAUSED`, `COMPLETED`, `CANCELLED`).
   - `current_round`: Integer (1 to 4).
   - Relationships: `question`, `sides`, `participants`, `rounds`, `arguments`, `verdict`.
4. **`DebateSide`** (`debate_sides` table):
   - `id`: UUID.
   - `debate_id`: Foreign Key -> `debates.id` (ondelete="CASCADE").
   - `label`: Enum (`SideLabel.FOR`, `SideLabel.AGAINST`).
5. **`Participant`** (`participants` table):
   - `id`: UUID.
   - `debate_id`: Foreign Key -> `debates.id`.
   - `user_id`: Foreign Key -> `users.id` (Nullable for AI).
   - `side_id`: Foreign Key -> `debate_sides.id`.
   - `participant_type`: Enum (`ParticipantType.HUMAN`, `ParticipantType.AI_SWARM`).
   - `initial_position`: Enum (`SideLabel.FOR`, `SideLabel.AGAINST`).
6. **`Round`** (`rounds` table):
   - `id`: UUID.
   - `debate_id`: Foreign Key -> `debates.id`.
   - `round_number`: Integer (1, 2, 3, 4).
   - `phase`: Enum (`RoundPhase.OPENING`, `RoundPhase.REBUTTAL`, `RoundPhase.CROSS_EXAMINATION`, `RoundPhase.CLOSING`).
   - `status`: Enum (`RoundStatus.ACTIVE`, `RoundStatus.COMPLETED`).
7. **`Argument`** (`arguments` table):
   - `id`: UUID.
   - `debate_id`: Foreign Key -> `debates.id`.
   - `round_id`: Foreign Key -> `rounds.id`.
   - `participant_id`: Foreign Key -> `participants.id`.
   - `side_id`: Foreign Key -> `debate_sides.id`.
   - `content`: Text (Full Markdown transcript of the speech).
   - `sequence`: Integer (Global chronological order).
   - `argument_type`: Enum (`OPENING`, `REBUTTAL`, `QUESTION`, `ANSWER`, `CLOSING`).
8. **`Verdict`** (`verdicts` table):
   - `id`: UUID.
   - `debate_id`: Foreign Key -> `debates.id` (Unique constraint).
   - `winning_side_id`: Foreign Key -> `debate_sides.id` (Nullable on TIE).
   - `judge_conclusion`: `VARCHAR(100)` (Hard DB constraint).
   - `consensus_score`: Float (0.0 to 100.0).
   - `metrics`: JSONB (Stores multi-criteria scores, sub-breakdowns, and turning point).
9. **`PositionHistory`** (`position_history` table):
   - Tracks stance migration and confidence over time.
   - `participant_id`: Foreign Key -> `participants.id`.
   - `debate_id`: Foreign Key -> `debates.id`.
   - `side_label`: Enum (`FOR`, `AGAINST`, `NEUTRAL`).
   - `phase`: `VARCHAR(50)` (`BEFORE`, `AFTER_R1`, `FINAL`).

---

## 4.5 Rate Limiting & Cost Guardrails (`backend/app/limiter.py`)
Protects external LLM API keys (Groq, Gemini) from malicious Denial-of-Wallet (DoW) attacks.

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from backend.app.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
    default_limits=[],
    headers_enabled=False,  # Prevents SlowAPI from expecting explicit Response parameters in FastAPI routers
)
```
- **IP Extraction**: `get_remote_address` pulls client IP from `request.client.host` or reverse proxy headers (`X-Forwarded-For`).
- **Applied Limits**:
  - `@limiter.limit("10/minute")` on `/api/v1/auth/login` (blocks brute-force credential stuffing).
  - `@limiter.limit("5/minute")` on `/api/v1/auth/register` (blocks automated bot account creation).
  - `@limiter.limit("10/hour")` on `/api/v1/debates` (caps debate creation and concurrent LLM triggers).
  - `@limiter.limit("30/hour")` on `/api/v1/debates/{id}/turn` (caps human argument submission rate).

---

## 4.6 Real-Time WebSocket Infrastructure (`backend/app/websockets/manager.py`)
Implements an event-driven pub/sub connection hub.

```
       [Uvicorn Process 1]                   [Uvicorn Process 2]
    +-----------------------+             +-----------------------+
    | ConnectionManager     |             | ConnectionManager     |
    | active_connections =  |             | active_connections =  |
    | { 'deb-123': {ws1, ws2} }           | { 'deb-123': {ws3} }   |
    +-----------+-----------+             +-----------+-----------+
                ^                                     ^
                |      Sub: 'debates:deb-123'         |
                +-----------------+-------------------+
                                  |
                        +---------+---------+
                        |  Redis Pub/Sub    |
                        |  Channel Broker   |
                        +---------+---------+
                                  ^
                                  | Pub: event
                        +---------+---------+
                        | Celery Worker or  |
                        | Turn Orchestrator |
                        +-------------------+
```

### Methods & Concurrency Safety
- **`connect(websocket: WebSocket, debate_id: str)`**:
  - Awaits `websocket.accept()`.
  - Appends socket to `active_connections[debate_id]`.
- **`disconnect(websocket: WebSocket, debate_id: str)`**:
  - Removes socket from set. Deletes `debate_id` key if set is empty to reclaim memory.
- **`publish_event(debate_id: str, event_type: str, payload: dict)`**:
  - Assembles standardized message envelope: `{"type": event_type, "debate_id": debate_id, "timestamp": iso8601, "data": payload}`.
  - If Redis is active, serializes to JSON and runs `await redis.publish(f"debates:{debate_id}", message)`.
  - If Redis is offline, calls `broadcast_local(debate_id, event)` directly.
- **`start_redis_listener(redis_client)`**:
  - Subscribes to pattern `debates:*`.
  - Loops over pub/sub messages asynchronously and routes incoming frames to local sockets via `broadcast_local()`.
- **Heartbeat & Zombie Pruning**:
  - Closed sockets throw `WebSocketDisconnect` or `RuntimeError` during `send_json()`. The manager catches this error and calls `disconnect()` immediately.

---

## 4.7 Finite State Machine Engine (`backend/app/debate/state_machine.py`)
Enforces the dialectical invariants of the debate.

```
[INIT] ---> R1: OPENING (ACTIVE)
               |
               +---> Both sides submit Opening Statements?
                     |
                     v
            R2: REBUTTAL (ACTIVE)
               |
               +---> Both sides submit Rebuttals?
                     |
                     v
            R3: CROSS_EXAMINATION (ACTIVE)
               |
               +---> Both sides submit Questions & Answers?
                     |
                     v
            R4: CLOSING (ACTIVE)
               |
               +---> Both sides submit Closing Syntheses?
                     |
                     v
            [DEBATE STATUS = COMPLETED] ---> Trigger Verdict Engine
```

### Deterministic Rules
1. **`initialize_debate(debate)`**:
   - Sets `debate.status = DebateStatus.LIVE`.
   - Sets `debate.current_round = 1`.
   - Inserts Round 1 (`phase = RoundPhase.OPENING`, `status = RoundStatus.ACTIVE`).
2. **`should_advance_round(debate)`**:
   - Queries argument count in current round.
   - For Rounds 1, 2, and 4: Checks if at least 1 argument exists per participant side.
   - For Round 3 (Cross-Exam): Checks if 2 arguments exist per side (Question + Answer).
3. **`advance_round(debate)`**:
   - Marks current round `RoundStatus.COMPLETED`.
   - If `current_round < 4`: Increments `current_round += 1`, creates next `Round` row with next phase, returns new round.
   - If `current_round == 4`: Sets `debate.status = DebateStatus.COMPLETED`, returns `None`.

---

## 4.8 Autonomous Agent-vs-Agent Debate Orchestrator (`backend/app/ai/agent_debate.py`)
Runs 4 complete rounds between Groq Qwen and Google Gemini autonomously.

### Pacing & Pipelining
```python
async def run_agent_vs_agent_debate(debate_id: str):
    # 1. Fetch debate, sides, question text
    # 2. Iterate round_num from 1 to 4:
    #      a. Generate FOR argument (Groq)
    #      b. Sanitize scratchpad
    #      c. Commit to DB & Broadcast WS
    #      d. asyncio.sleep(2)
    #      e. Generate AGAINST argument (Gemini)
    #      f. Sanitize scratchpad
    #      g. Commit to DB & Broadcast WS
    #      h. asyncio.sleep(2)
    #      i. Advance State Machine & Broadcast WS
    # 3. Trigger generate_verdict(debate_id)
```

### The Groq 1,000 OTPM Ceiling & Failover Circuit Breaker
- **The Issue**: Groq's free tier imposes an On-Demand Token Per Minute (OTPM) cap of 1,000. Generating multi-turn debate speeches easily consumes 1,200+ tokens, triggering HTTP 429.
- **The Implementation**:
  ```python
  try:
      response = await litellm.acompletion(
          model=settings.groq_model,
          messages=messages,
          temperature=0.6,
          max_tokens=850,  # Strict cap to prevent OTPM overrun
          api_key=settings.groq_api_key
      )
  except Exception as e:
      logger.warning(f"Groq API error or rate limit ({e}); failing over to Gemini")
      response = await litellm.acompletion(
          model=settings.gemini_model,
          messages=messages,
          temperature=0.6,
          max_tokens=850,
          api_key=settings.google_api_key
      )
  ```

### Dual-Stage Scratchpad Sanitizer
Reasoning models output internal chain-of-thought tokens inside `<think>` XML tags. We strip them completely:
```python
def clean_reasoning_scratchpad(text: str) -> str:
    # 1. Strip complete <think>...</think> blocks
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.DOTALL).strip()
    # 2. Delimiter fallback if closing tag was truncated by token limits
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>")[-1].strip()
    return cleaned
```

---

## 4.9 Human vs. AI Swarm LangGraph Engine (`backend/app/ai/swarm.py`)
Orchestrates a collaborative multi-agent Swarm to debate against a human user.

```
                  [Human Argument Submitted]
                              |
                              v
                   +---------------------+
                   |   Researcher Node   |  <--- Tavily Search API
                   | (Gathers citations) |
                   +----------+----------+
                              |
                              v
                   +---------------------+
                   |   Strategist Node   |  <--- Identifies logical fallacies
                   | (Formulates tactics)|       in human's argument
                   +----------+----------+
                              |
                              v
                   +---------------------+
                   |    Skeptic Node     |  <--- Stress-tests counter-premises
                   | (Refines arguments) |       to prevent hallucination
                   +----------+----------+
                              |
                              v
                   +---------------------+
                   |   Lead Orator Node  |  <--- Synthesizes final polished,
                   | (Delivers response) |       persuasive speech
                   +----------+----------+
                              |
                              v
                   [WebSocket Broadcast]
```
- **State Schema (`DebateState`)**:
  ```python
  class DebateState(TypedDict):
      messages: List[BaseMessage]
      next_node: str
      context: str
      round_phase: str
      draft_argument: str
      research_points: str
  ```
- **Async Safety**: `app.invoke()` is executed inside `await asyncio.to_thread(app.invoke, initial_state)` to prevent blocking FastAPI's async event loop during tool calls.

---

## 4.10 Forensic AI Verdict Generator (`backend/app/verdict/generator.py`)
Synthesizes the final forensic judgment of the debate.

### Evaluation Rubric & Prompt Structure
- **Logic & Coherence (40%)**: Deductive validity, consistency of premises, absence of non-sequiturs.
- **Empirical Grounding (30%)**: Quality of facts, real-world examples, and citations.
- **Rhetoric & Persuasiveness (20%)**: Rhetorical framing, clarity, and rebuttal effectiveness.
- **Fallacy Penalties (-10%)**: Penalties for strawman, ad hominem, or slippery slope fallacies.

### Truncation Guardrail for PostgreSQL `VARCHAR(100)`
The database column `verdicts.judge_conclusion` is constrained to `VARCHAR(100)`. Gemini often generates a conclusion of 120-150 characters.
- **The Fix**:
  ```python
  conclusion_text = verdict_data.get("judge_conclusion", "Debate concluded.")
  if len(conclusion_text) > 95:
      conclusion_text = conclusion_text[:92] + "..."
  ```
- The full, unabridged analysis is preserved inside the `metrics` JSONB column.

### Idempotent Upsert Logic
```python
existing_verdict = await session.scalar(select(Verdict).where(Verdict.debate_id == debate.id))
if existing_verdict:
    existing_verdict.winning_side_id = winning_side_id
    existing_verdict.judge_conclusion = conclusion_text
    existing_verdict.consensus_score = verdict_data.get("consensus_score", 50.0)
    existing_verdict.metrics = metrics_payload
else:
    new_verdict = Verdict(...)
    session.add(new_verdict)
await session.commit()
```
- Guarantees zero duplicate key exceptions if multiple workers attempt verdict creation.

---

## 4.11 Async Worker Tier & Resilient Task Dispatching (`backend/app/workers/`)

### Celery Infrastructure (`celery_app.py`)
- Configured with Redis broker and Redis result backend.
- Strict task routing:
  - `ai.*` tasks -> `ai` queue.
  - `verdict.*` tasks -> `verdict` queue.
- Worker settings: `worker_prefetch_multiplier = 1` (prevents long AI tasks from starving other workers), `task_acks_late = True` (re-queues task if worker crashes mid-generation).

### Resilient Dispatchers (`ai_tasks.py`)
Allows the application to run in distributed multi-machine production or zero-setup local development:
```python
def dispatch_agent_debate(debate_id: str, background_tasks: BackgroundTasks):
    try:
        run_agent_debate_task.delay(debate_id)
        logger.info(f"Dispatched debate {debate_id} to Celery queue 'ai'")
        return
    except Exception as exc:
        logger.info(f"Celery offline/bypassed ({exc}); falling back to FastAPI BackgroundTasks")
    from backend.app.ai.agent_debate import run_agent_vs_agent_debate
    background_tasks.add_task(run_agent_vs_agent_debate, debate_id)
```

---

## 4.12 API Routers (`backend/app/api/`)

### `auth.py`
- `POST /register`: Sanitizes username and display name via `bleach.clean(tags=[], strip=True)`. Hashes password with Bcrypt/Argon2.
- `POST /login`: OAuth2 password request form. Generates JWT access token (HS256) with user UUID payload. Rate-limited to 10 requests/minute.

### `debates.py`
- `GET /`: Lists public debates with eager-loaded questions and participant counts.
- `POST /`: Creates a debate, sides, participants, and initializes FSM. Dispatches agent or swarm tasks. Rate-limited to 10 debates/hour.
- `GET /{id}`: Returns debate detail, active round, and full argument history.
- `POST /{id}/turn`: Submits user argument. Rejects submissions if user is spectator in `AI_VS_AI` mode. Dispatches AI swarm rebuttal. Rate-limited to 30 arguments/hour.
- `POST /{id}/vote`: Records audience vote for `FOR` or `AGAINST`.
- `POST /{id}/challenge`: Submits audience cross-exam challenge.

---

## 4.13 Client Architecture & Dynamic Frontend (`frontend/`)
- **No Node.js / Webpack / Vite Build Step**: Pure native browser ES6 modules. Enables lightning-fast edits, zero compilation lag, and clean HTTP asset delivery.
- **Design Tokens (`css/variables.css`)**: Centralized HSL color palettes, typography scale (`Outfit` and `Inter` Google fonts), elevations, and glassmorphic blur filters.
- **WebSocket Reconnect Loop (`js/pages/debate.js`)**:
  - Handles reconnection with exponential backoff on network drop.
  - Sends `{ type: "ping" }` heartbeat every 20 seconds.
  - Listens for `argument_submitted`: Appends speech bubble to transcript, scrolls to bottom, updates active speaker banner.
  - Listens for `round_advanced`: Updates round stepper UI and changes phase banner.
  - Listens for `debate_completed`: Triggers celebratory banner and redirects to `verdict.html?id=<debate_id>`.

---

# 5. THE 5 CORE EXECUTION PIPELINES

### Pipeline 1: User Onboarding, Authentication & JWT Lifecycle
```
[Client: POST /auth/register]
       |
       v
Rate Limiter (5/min) ---> Bleach Input Sanitizer ---> Check Email/Username Uniqueness
                                                              |
                                                              v
JWT Token Issued <--- Generate Bcrypt Hash <--- Insert User to DB
       |
       v
[Client Stores Token in localStorage]
       |
       v
[Subsequent Requests send Authorization: Bearer <token>]
       |
       v
FastAPI Dependency `get_current_user`: Validates HS256 Signature, Queries DB, Injects User
```

### Pipeline 2: Debate Creation & Atomic Participant Initialization
```
[Client: POST /debates]
       |
       v
Rate Limiter (10/hr)
       |
       v
Resolve Question/Topic ---> Insert Debate (Status: LIVE)
                                  |
                                  v
                       Create 2 Sides (FOR, AGAINST)
                                  |
                                  v
                       Create Participants
                                  |
                                  v
                   [CRITICAL: await db.flush()]  <--- Generates Participant UUIDs
                                  |
                                  v
               Insert PositionHistory (References Participant UUIDs)
                                  |
                                  v
               DebateStateMachine.initialize_debate() (Creates Round 1)
                                  |
                                  v
        Commit DB Transaction & Dispatch Async Task (Celery or Background)
```

### Pipeline 3: Autonomous Agent vs. Agent 4-Round Match
```
[dispatch_agent_debate]
       |
       v
Celery Task `ai.agent_debate` (or BackgroundTasks fallback)
       |
       +---> Round 1: OPENING
       |        |
       |        +--> Groq Qwen (FOR) [max_tokens: 850] ---> Clean <think> ---> DB & WS
       |        +--> 2s Pacing Delay
       |        +--> Gemini Flash (AGAINST) [max_tokens: 850] ---> Clean <think> ---> DB & WS
       |        +--> FSM: Advance to Round 2
       |
       +---> Round 2: REBUTTAL
       |        |
       |        +--> Groq Qwen (FOR) Rebuttal ---> DB & WS
       |        +--> Gemini Flash (AGAINST) Rebuttal ---> DB & WS
       |        +--> FSM: Advance to Round 3
       |
       +---> Round 3: CROSS-EXAMINATION
       |        |
       |        +--> Groq Qwen (FOR) Cross-Exam Q&A ---> DB & WS
       |        +--> Gemini Flash (AGAINST) Cross-Exam Q&A ---> DB & WS
       |        +--> FSM: Advance to Round 4
       |
       +---> Round 4: CLOSING
       |        |
       |        +--> Groq Qwen (FOR) Closing Defense ---> DB & WS
       |        +--> Gemini Flash (AGAINST) Closing Defense ---> DB & WS
       |        +--> FSM: Set Debate Status = COMPLETED
       |
       v
[Trigger Pipeline 5: Forensic Verdict Engine]
```

### Pipeline 4: Human vs. AI Swarm Reactive Deliberation
```
[Human Submits Argument: POST /debates/{id}/turn]
       |
       v
Rate Limiter (30/hr) ---> Verify Turn Status ---> Insert Human Argument to DB
                                                          |
                                                          v
                                              Broadcast WS: `argument_submitted`
                                                          |
                                                          v
                                              [dispatch_ai_swarm_turn]
                                                          |
                                                          v
                                     LangGraph Cyclic Swarm (asyncio.to_thread)
                                     - Researcher (Tavily Web Search)
                                     - Strategist (Fallacy Detection)
                                     - Skeptic (Logic Check)
                                     - Lead Orator (Drafting)
                                                          |
                                                          v
                                              Insert AI Argument to DB
                                                          |
                                                          v
                                              Broadcast WS: `argument_submitted`
                                                          |
                                                          v
                                              FSM: Check if Round Should Advance
```

### Pipeline 5: AI Judge Verdict Synthesis & Multi-Criteria Scoring
```
[Debate Reaches Status: COMPLETED]
       |
       v
Load Full Transcript (Eager Loading: Question, Arguments, Participants)
       |
       v
Prompt Forensic Judge (Gemini 3.6 Flash, Temperature: 0.2)
       |
       v
Extract Structured JSON Response:
- Winner: FOR / AGAINST / TIE
- Judge Conclusion: One sentence summary
- Consensus Score: 0-100
- Metrics: Logic (40%), Evidence (30%), Rhetoric (20%), Fallacy Penalty (-10%)
- Turning Point: Pivotal moment
       |
       v
Truncate `judge_conclusion` to < 95 characters (PostgreSQL VARCHAR(100) safety)
       |
       v
Idempotent Upsert to `verdicts` table
       |
       v
Broadcast WS: `verdict_ready` ---> Client navigates to verdict.html
```

---

# 6. THE 8 PRODUCTION "WAR STORIES"

### War Story 1: The Groq 1,000 OTPM Ceiling Freezing Agent Debates
- **Symptom**: During live 4-round agent debates, the debate abruptly froze after Round 1. Uvicorn logs threw: `RateLimitError: Rate limit reached for model qwen/qwen3.6-27b on on-demand tokens per minute (OTPM). Limit: 1000`.
- **Root Cause**: Advanced reasoning models are verbose. The default prompt allowed up to 4,000 tokens. Generating two opening statements in rapid succession pushed token consumption over 1,800 tokens within 40 seconds, exceeding Groq’s on-demand free tier quota.
- **Diagnostic Steps**: Monitored LiteLLM request payloads. Observed prompt tokens (~450) plus completion tokens (~850) per call equaled 1,300 tokens.
- **Solution**:
  1. Clamped `max_tokens` to strictly `850` on Groq calls.
  2. Implemented a dual-provider circuit breaker in `agent_debate.py`: If Groq throws any exception or rate limit error, the turn immediately falls back to `gemini/gemini-3.6-flash`.

### War Story 2: Reasoning Model `<think>` Monologue Leaking to Spectators
- **Symptom**: Spectators saw the AI agent’s private deliberative scratchpad: `<think> The user makes an emotional appeal regarding climate change. I need to counter with economic feasibility... </think> Ladies and gentlemen...`.
- **Root Cause**: DeepSeek-R1 and Qwen reasoning models output chain-of-thought tokens wrapped in `<think>` tags before the final speech.
- **Diagnostic Steps**: Inspected raw LiteLLM text output strings.
- **Solution**: Engineered a robust multi-pass sanitizer:
  ```python
  cleaned = re.sub(r"<think>[\s\S]*?</think>", "", raw_text, flags=re.DOTALL).strip()
  if "</think>" in cleaned:
      cleaned = cleaned.split("</think>")[-1].strip()
  ```
  Applied before saving to the database and broadcasting via WebSockets.

### War Story 3: `ForeignKeyViolationError` on `position_history` Insert
- **Symptom**: Calling `POST /api/v1/debates` failed with HTTP 500: `asyncpg.exceptions.ForeignKeyViolationError: insert or update on table "position_history" violates foreign key constraint "fk_position_history_participant"`.
- **Root Cause**: In SQLAlchemy 2.0 async sessions, objects added via `session.add()` do not receive auto-generated database keys until the session is flushed. `Participant` and `PositionHistory` were created in the same function block, but `PositionHistory` referenced `participant.id` before `session.flush()` had been executed.
- **Diagnostic Steps**: Step-debugged object attributes; found `participant.id` was `None` when constructing `PositionHistory`.
- **Solution**: Added an explicit `await db.flush()` immediately after creating participants and before instantiating `PositionHistory`.

### War Story 4: Neon PgBouncer Prepared Statement Collisions
- **Symptom**: Random database queries failed with `asyncpg.exceptions.DuplicatePreparedStatementError: prepared statement "__asyncpg_stmt_12__" already exists`.
- **Root Cause**: Neon uses PgBouncer in transaction pooling mode. `asyncpg` caches prepared statement names per connection. In transaction pooling, a subsequent query can be routed to a different physical backend where that statement ID is already in use by another connection.
- **Diagnostic Steps**: Traced connection lifecycle; identified error occurred only on Neon Cloud and never on local native PostgreSQL.
- **Solution**: Configured `connect_args={"statement_cache_size": 0}` and `pool_recycle=300` in `create_async_engine()`.

### War Story 5: SlowAPI `Response` Parameter Type Error in FastAPI Routes
- **Symptom**: When rate limiting was introduced, tests failed with `Exception: parameter 'response' must be an instance of starlette.responses.Response`.
- **Root Cause**: SlowAPI defaults to `headers_enabled=True`. In this mode, SlowAPI expects every endpoint function signature to contain an explicit `response: Response` parameter so it can inject `X-RateLimit-*` headers. Route handlers lacking this parameter threw runtime exceptions.
- **Diagnostic Steps**: Inspected Starlette middleware call stack; identified `SlowAPIMiddleware` inspecting handler arguments.
- **Solution**: Initialized `Limiter(..., headers_enabled=False)`. This enforces IP throttling without forcing boilerplate parameters into every route handler.

### War Story 6: Neon `VARCHAR(100)` Truncation Crash on `judge_conclusion`
- **Symptom**: Verdict generation crashed with: `DataError: value too long for type character varying(100)`.
- **Root Cause**: The database migration defined `verdicts.judge_conclusion` as `VARCHAR(100)`. Gemini frequently generated conclusions that were 115-140 characters long.
- **Diagnostic Steps**: Inspected failed SQL insert statement; verified string length was 128 characters.
- **Solution**: Enforced Python-side truncation: `conclusion[:92] + "..."` before inserting into the database, preserving the full text in the `metrics` JSONB payload.

### War Story 7: LangGraph Swarm Blocking the Asyncio Event Loop
- **Symptom**: When a human submitted an argument, all other active WebSockets stopped responding for 6-10 seconds.
- **Root Cause**: LangGraph's `app.invoke()` runs synchronous Python graph iterations and blocking HTTP calls to search APIs. Calling it directly inside an async FastAPI route blocked the main thread's event loop.
- **Diagnostic Steps**: Profiled event loop latency using `asyncio` debug mode; identified single-thread freeze during `app.invoke()`.
- **Solution**: Wrapped execution in `await asyncio.to_thread(app.invoke, initial_state)`.

### War Story 8: Zombie WebSockets Leaking File Descriptors
- **Symptom**: Memory and open socket counts grew steadily on the server over time.
- **Root Cause**: Spectators closing laptop lids or losing Wi-Fi connections did not cleanly send a WebSocket close frame (TCP half-open connection).
- **Diagnostic Steps**: Inspected `netstat` and observed hundreds of `ESTABLISHED` sockets for inactive IP addresses.
- **Solution**: Implemented a 20-second client ping/pong heartbeat. If a write fails during `send_json()`, the socket is caught and immediately purged via `manager.disconnect()`.

---

# 7. COMPREHENSIVE MASTER INTERVIEW QUESTION BANK

## Category 1: Distributed Systems, WebSockets & Concurrency

#### Q1: "How does Provok broadcast real-time debate arguments to multiple spectator instances across a horizontally scaled server cluster?"
> **Answer:**  
> "Provok uses a hybrid architecture pairing WebSockets with Redis Pub/Sub:
> 1. Spectators establish persistent WebSocket connections to `/api/v1/debates/ws/{debate_id}`.
> 2. Each FastAPI/Uvicorn worker maintains a local `ConnectionManager` that maps `debate_id` to a `set` of active local WebSockets.
> 3. When an argument or verdict is generated by any worker or Celery task, the event is serialized to JSON and published to the Redis channel `debates:{debate_id}`.
> 4. Every worker runs an asynchronous background Redis subscriber (`start_redis_listener`). When a message arrives from Redis, the worker looks up the `debate_id` in its local connection set and broadcasts the payload to all connected local clients.
> 5. If Redis is unavailable (e.g., local development), the system gracefully degrades to in-process local broadcasting."

#### Q2: "How do you detect and clean up dead or zombie WebSocket connections?"
> **Answer:**  
> "TCP half-open connections occur when clients drop connectivity without sending a TCP FIN packet. We handle this on two levels:
> 1. **Client-Side Heartbeat**: The frontend JavaScript sends a `{ type: 'ping' }` frame every 20 seconds; the server responds with `{ type: 'pong' }`.
> 2. **Proactive Exception Pruning**: When broadcasting an event in `broadcast_local()`, any call to `websocket.send_json()` that fails (raising `WebSocketDisconnect` or `RuntimeError`) catches the exception, appends the socket to a `dead_connections` list, and immediately removes it from the active connection set. This guarantees zero socket or file descriptor leakage."

#### Q3: "What are the trade-offs of using Celery vs. FastAPI's built-in `BackgroundTasks` for LLM debate execution?"
> **Answer:**  
> "`BackgroundTasks` executes in-process on the Uvicorn worker threadpool:
> - *Pros*: Zero external infrastructure needed; simple execution.
> - *Cons*: Ephemeral. If Uvicorn restarts, deploys a new container, or crashes, all active in-flight 4-round debates are killed mid-execution.
> Celery uses an external broker (Redis/RabbitMQ) and worker processes:
> - *Pros*: Durable execution, task retries, worker isolation, and priority queue routing (`ai`, `verdict`).
> - *Trade-off Solution*: We engineered a resilient dispatcher pattern: the system attempts to enqueue tasks to Celery (`ai.agent_debate.delay()`), but if Celery/Redis is unreachable, it automatically catches the exception and falls back to FastAPI's `BackgroundTasks`. This enables frictionless local development alongside robust production durability."

---

## Category 2: Python 3.12, Asyncio & FastAPI Deep Internals

#### Q4: "What is the difference between `asyncio.to_thread()` and running code directly in an `async def` function?"
> **Answer:**  
> "In Python's `asyncio`, an `async def` function runs on the single-threaded event loop. If code inside performs blocking I/O (e.g., synchronous HTTP calls or long CPU loops), it blocks the entire event loop, halting all concurrent tasks, WebSockets, and incoming HTTP requests.  
> `asyncio.to_thread()` offloads the synchronous function to a separate OS worker thread managed by Python's `ThreadPoolExecutor`, yielding control of the main event loop while waiting for the thread to finish. We use this specifically for LangGraph's synchronous `app.invoke()` method."

#### Q5: "How does FastAPI's dependency injection system manage SQLAlchemy 2.0 AsyncSession lifecycles?"
> **Answer:**  
> "We implement a generator dependency `get_db()`:
> ```python
> async def get_db() -> AsyncGenerator[AsyncSession, None]:
>     async with async_session_factory() as session:
>         try:
>             yield session
>         except Exception:
>             await session.rollback()
>             raise
>         finally:
>             await session.close()
> ```
> FastAPI injects `session` into router endpoints via `Depends(get_db)`. When the request finishes, control returns to the generator's `finally` block, guaranteeing that uncommitted transactions are rolled back and connections are returned to the pool, preventing connection leaks."

#### Q6: "Why did you implement custom middleware for `X-Request-ID` instead of using an existing third-party package?"
> **Answer:**  
> "Custom middleware gave us unified control over distributed tracing, security headers, and performance profiling in a single pass:
> 1. It extracts an existing `X-Request-ID` or generates a new `uuid.uuid4()`.
> 2. It attaches the ID to `request.state.request_id` for use in route handlers and Structlog log records.
> 3. It injects essential security headers (`nosniff`, `DENY`, `HSTS`).
> 4. It records execution timing via `time.perf_counter()` and logs requests exceeding 1,000ms as slow-query warnings, eliminating the overhead of multiple middleware passes."

---

## Category 3: LLM Engineering, Multi-Agent Swarms & LiteLLM

#### Q7: "Why did you choose LiteLLM over LangChain's native LLM wrappers for the Agent vs. Agent orchestrator?"
> **Answer:**  
> "LiteLLM provides a lightweight, model-agnostic I/O interface using standard OpenAI-compatible dictionaries without the heavy class abstractions, object overhead, and breaking changes common in LangChain. It provides unified async calling (`litellm.acompletion`), universal exception catching for rate limits, and seamless model switching between Groq (`groq/qwen/qwen3.6-27b`) and Google Gemini (`gemini/gemini-3.6-flash`)."

#### Q8: "How does the LangGraph cyclic Swarm work in the Human vs. AI debate mode?"
> **Answer:**  
> "Unlike a linear chain, LangGraph is a stateful directed graph:
> 1. The graph maintains a shared `DebateState` containing message history, round phase, and draft arguments.
> 2. **Researcher Node**: Queries Tavily API for evidence and updates `research_points`.
> 3. **Strategist Node**: Evaluates human argument vulnerabilities and sets the rhetorical counter-strategy.
> 4. **Skeptic Node**: Tests the counter-arguments against potential counter-rebuttals to ensure premise validity.
> 5. **Lead Orator Node**: Drafts the final speech calibrated to the active round constraints.
> This multi-agent decomposition produces significantly higher-caliber rhetoric and fact-grounded reasoning than a single monolithic prompt."

#### Q9: "How do you eliminate AI Judge position bias when evaluating verdicts?"
> **Answer:**  
> "Position bias (the tendency of LLMs to favor either the first or last speaker) is mitigated through several techniques:
> 1. **Neutral Canonical Labeling**: The judge prompt normalizes speakers into abstract roles (`Side FOR` and `Side AGAINST`) rather than usernames or model names.
> 2. **Multi-Criteria Forensic Rubric**: The judge is forced to evaluate discrete scoring dimensions (Logic 40%, Evidence 30%, Rhetoric 20%, Fallacy Penalty -10%) before declaring a winner.
> 3. **Low Temperature**: We set `temperature: 0.2` on the judge model to ensure deterministic evaluation.
> 4. **Turning Point Identification**: The judge must explicitly cite the pivotal turn that swung the outcome, enforcing evidence-based justification."

---

## Category 4: Database Architecture, PgBouncer, ACID & ORM

#### Q10: "Why must `statement_cache_size` be set to 0 when connecting to Neon PostgreSQL with `asyncpg`?"
> **Answer:**  
> "Neon uses PgBouncer in transaction pooling mode. Under transaction pooling, different queries within the same client session can be routed across different physical PostgreSQL backend connections. `asyncpg` by default caches prepared statements by name on the server. If `asyncpg` sends a cached statement name to a physical backend that has not prepared it, PostgreSQL raises `PreparedStatementDoesNotExistError`; if another connection already prepared a statement with that name, it raises `DuplicatePreparedStatementError`. Disabling statement caching with `statement_cache_size: 0` forces `asyncpg` to use anonymous queries, eliminating collisions entirely."

#### Q11: "Explain the foreign key race condition we solved during debate creation."
> **Answer:**  
> "In `debates.py`, when a user creates a debate, we create `DebateSide` rows, `Participant` rows, and `PositionHistory` rows. `PositionHistory` requires a foreign key pointing to `participants.id`. In SQLAlchemy async sessions, objects added via `session.add()` do not have their primary keys populated until a flush occurs. When `PositionHistory` was instantiated in the same block, `participant.id` was `None`, causing PostgreSQL to raise a `ForeignKeyViolationError`. We resolved this by placing an explicit `await session.flush()` immediately after participant creation, ensuring valid UUIDs were committed to the transaction state before inserting history records."

#### Q12: "How is verdict generation made idempotent in the database?"
> **Answer:**  
> "In `backend/app/verdict/generator.py`, we execute a selective upsert:
> 1. We query `select(Verdict).where(Verdict.debate_id == debate.id)`.
> 2. If a verdict record already exists, we update its fields in-place (`winning_side_id`, `consensus_score`, `metrics`).
> 3. If no record exists, we instantiate and add a new `Verdict` row.
> 4. The `verdicts.debate_id` column has a unique database constraint. Even under high-concurrency race conditions, duplicate verdict records are impossible."

---

## Category 5: Security, Rate Limiting & Denial-of-Wallet Defense

#### Q13: "What is a Denial-of-Wallet (DoW) attack, and how does Provok defend against it?"
> **Answer:**  
> "A Denial-of-Wallet attack occurs when an attacker spams API endpoints that trigger costly downstream third-party services (such as LLM generation calls) to exhaust the startup's financial budget or API quotas.  
> Provok defends against DoW using SlowAPI token-bucket rate limiting tied to remote client IPs:
> - `/api/v1/debates` is limited to 10 creations/hour per IP.
> - `/api/v1/debates/{id}/turn` is limited to 30 arguments/hour per IP.
> - Requests exceeding limits are immediately terminated at the gateway layer with HTTP 429 Too Many Requests before any LLM SDK is invoked."

#### Q14: "How does Provok prevent Cross-Site Scripting (XSS) in debate arguments?"
> **Answer:**  
> "We employ defense-in-depth:
> 1. **Input Sanitization**: User registrations and profile inputs are sanitized using Python's `bleach` library, stripping malicious HTML tags.
> 2. **Client-Side Escaping**: The frontend renders argument text using `textContent` and safe DOM manipulation methods, avoiding raw `innerHTML` injection of unescaped text.
> 3. **HTTP Security Headers**: `X-Content-Type-Options: nosniff` and strict Content Security Policies prevent malicious script execution."

---

## Category 6: Behavioral, Leadership & STAR Technical Scenarios

#### Q15: "Tell me about a complex, ambiguous technical bug you encountered in Provok and how you resolved it." (STAR Method)
> **Situation**: While testing the autonomous Agent-vs-Agent debate arena, debates would randomly freeze after Round 1 without throwing clear errors to the client, leaving WebSockets hanging indefinitely.
> **Task**: Identify the root cause across the distributed pipeline (FastAPI, WebSockets, LiteLLM, Groq, Gemini) and engineer a resilient, production-grade fix.
> **Action**: 
> 1. I inspected the backend `structlog` logs and isolated an HTTP 429 error originating from Groq's API: *'Rate limit reached for model qwen/qwen3.6-27b on on-demand tokens per minute (OTPM). Limit: 1000'*.
> 2. I audited token usage and found that Qwen’s internal chain-of-thought scratchpad pushed total generation to ~1,300 tokens per speech.
> 3. I implemented a two-pronged solution: first, I capped `max_tokens` to `850` to fit within OTPM limits; second, I implemented a circuit-breaker fallback in `agent_debate.py` that automatically catches Groq rate limits and reroutes the turn to Google Gemini Flash. Finally, I built a regex sanitizer to strip raw `<think>` scratchpads from user views.
> **Result**: Autonomous debates run with 100% reliability, zero hanging sockets, and seamless automated failover during third-party API outages.

#### Q16: "Describe a time you had to make a pragmatic engineering tradeoff between theoretical purity and practical startup velocity." (STAR Method)
> **Situation**: The initial architecture called for all asynchronous background tasks (AI debates, verdicts, embeddings) to run exclusively through distributed Celery workers backed by Redis.
> **Task**: Maintain enterprise-grade worker durability for production while preventing heavy infrastructure requirements from slowing down local developer onboarding and CI test runs.
> **Action**: I architected a resilient task dispatcher abstraction (`dispatch_agent_debate`). The dispatcher attempts to route tasks to Celery queues (`ai.agent_debate.delay()`). If the Celery broker is offline or unconfigured, it catches the exception and gracefully routes the task through FastAPI's in-process `BackgroundTasks`.
> **Result**: Developers can clone the repository and run all 14 integration tests locally without spinning up Docker or Redis, while production deployments retain full multi-worker durability.

---
*End of Manual — Provok Engineering Master Interview Preparation Guide.*
