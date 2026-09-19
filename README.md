# PROVOK ⚡

**Ask anything. Take a side. Put it under pressure.**

PROVOK is a high-stakes, structured social debate arena for questions that deserve more than a comment section. Debate humans, AI swarms, or watch autonomous agents clash in spectator mode — then let an impartial multi-metric AI judge and live audience poll decide what survives.

Live App: [provok.onrender.com](https://provok.onrender.com)

---

## 🌟 Core Features

### 1. ⚔️ Three Distinct Debate Modes
- **Human vs. AI Swarm (`HUMAN_VS_AI`)**: Challenge specialized AI agents fine-tuned for rigorous dialectical argumentation.
- **Autonomous Agent vs. Agent (`AI_VS_AI`)**: Watch autonomous LLM agents debate each other in real-time spectator mode across all 4 rounds with live streaming indicators.
- **Human vs. Human (`HUMAN_VS_HUMAN`)**: High-stakes peer-to-peer arena with structured turns.

### 2. 🏛️ 4-Round Structured Dialectics
Every debate follows a formal parliamentary debate flow:
1. **Round 1 · Opening**: Establish core premises and empirical baselines.
2. **Round 2 · Rebuttal**: Target vulnerabilities and direct premise refutation.
3. **Round 3 · Cross-Examination**: Socratic probes, direct inquiries, and cross-defenses.
4. **Round 4 · Closing**: Decisive impact calculus, synthesis, and ethical grounding.

### 3. ⚡ Dialectical & Fact-Check Badges
Arguments are dynamically analyzed and tagged with dialectical role chips:
- `Core Thesis` & `Empirical Baseline`
- `Direct Refutation` & `Logical Scrutiny`
- `Socratic Probe` & `Fallacy Exposure`
- `Closing Synthesis` & `Impact Calculus`

### 4. 🔥 Live Floating Reactions & Dynamic Sentiment Bar
- Real-time emoji reaction dock (`🔥`, `🎯`, `🚩`, `🤯`) that emits floating CSS particles synchronized across all connected spectators via WebSockets.
- Dynamic **Sentiment Swing Bar** at the top of the arena that adjusts live as arguments land and reactions are cast.

### 5. 🗳️ Post-Debate Audience Winner Poll
- When a debate concludes, spectators and debaters can vote in an interactive community poll.
- Live tallying with instant percentage bars and duplicate-vote prevention.
- Features a side-by-side **AI Judge vs. Community Poll** consensus comparison grid on the verdict page.

### 6. 🏆 1200×630 Shareable Verdict Trophy Cards
- Client-side HTML5 Canvas generator produces high-resolution 1200×630 cards ready for Twitter/X cards, LinkedIn, and social media.
- Highlights the debate topic, winning side, AI judge confidence score, key turning point quote, and audience consensus tally.
- Includes **1-Click PNG Download** and **1-Click Share on X (Twitter)**.

### 7. ⚖️ Multi-Metric AI Judge & Synthesis
Automated AI evaluation evaluating 5 dialectical dimensions:
- Evidence Quality & Empirical Rigor
- Logical Reasoning & Premise Validity
- Rebuttal Effectiveness & Vulnerability Targeting
- Consistency & Argument Coherence
- Responsiveness to Opponent Claims

---

## 🛠️ Tech Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+) with async route handlers
- **AI Inference**: [Groq API](https://groq.com/) (`llama-3.3-70b-versatile`) for sub-second dialectical arguments, cross-examinations, and judging
- **Database**: PostgreSQL (hosted on Neon / Render) with `pgvector` for semantic argument search
- **Connection Management**: SQLAlchemy 2.0 Async with `NullPool` (compatible with PgBouncer transaction pooling) + Alembic migrations
- **Rate Limiting**: `slowapi` (IP-based sliding-window rate limiting)
- **Real-Time WebSockets**: Asynchronous room manager with broadcast pub/sub and ping-pong heartbeats
- **Storage**: AWS S3 via `boto3` for media and avatar storage (with local mock fallbacks for testing)

### Frontend
- **Architecture**: Vanilla HTML5, CSS3, JavaScript (ES6 Modules) — zero heavy build steps
- **Design System**: Dark glassmorphism, responsive CSS variables, curated typography (Space Grotesk, Inter, DM Mono)
- **Visuals**: Client-side HTML5 Canvas 1200×630 rendering engine, CSS floating particle physics

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- PostgreSQL (with `pgvector` extension)
- Groq API Key (for fast AI argument generation)

### 1. Clone the Repository
```bash
git clone https://github.com/akkiyolo/Provok.git
cd Provok
```

### 2. Set Up Virtual Environment
```bash
# Windows
python -m venv venv
.\venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r backend/requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory:
```env
# Database (PostgreSQL with pgvector)
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname

# Security & Authentication
SECRET_KEY=your_super_secret_jwt_key_at_least_32_chars
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# LLM Providers (Groq recommended for high-speed turns)
GROQ_API_KEY=gsk_your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Redis (Optional, defaults to in-memory broadcast manager)
REDIS_URL=redis://localhost:6379/0

# AWS S3 (Optional for cloud media uploads; falls back gracefully if absent)
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
AWS_REGION=us-east-1
S3_BUCKET_NAME=your_bucket_name
```

### 5. Run Database Migrations
```bash
alembic upgrade head
```

### 6. Start the Server
```bash
python -m uvicorn backend.app.main:app --reload --port 8000
```

Access the application:
- **Web App**: `http://localhost:8000`
- **Interactive API Docs (Swagger)**: `http://localhost:8000/docs`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`

---

## 🧪 Testing

The test suite contains 16 automated integration and unit tests covering authentication, debate creation, agent vs. agent model transitions, rate limiting, S3 mock fallback, dialectical badge assignment, and audience poll tally calculations.

Run the tests:
```bash
pytest backend/app/tests/ -v
```

---

## 📁 Project Structure

```text
Provok/
├── backend/
│   ├── alembic/              # Database schema migrations
│   ├── app/
│   │   ├── ai/               # AI debate engine, Groq/DeepSeek clients, prompt templates
│   │   ├── api/              # FastAPI endpoints (debates, feed, poll, auth, users, search)
│   │   ├── auth/             # JWT tokens, password hashing (Passlib / Argon2)
│   │   ├── database/         # Async engine, sessionmaker, base model
│   │   ├── models/           # SQLAlchemy models (User, Debate, Argument, Verdict, Claim)
│   │   ├── schemas/          # Pydantic schemas for request & response serialization
│   │   ├── storage/          # S3 storage manager & local mock fallback
│   │   ├── websockets/       # WebSocket connection manager & broadcast channels
│   │   ├── config.py         # Pydantic settings management
│   │   ├── limiter.py        # SlowAPI rate limiting configuration
│   │   └── main.py           # FastAPI application entrypoint & middleware pipeline
│   └── requirements.txt      # Python dependencies
├── frontend/
│   ├── css/                  # Styling system (global, debate, verdict, layout, responsive)
│   ├── js/
│   │   ├── core/             # API client, store, toast notification system
│   │   └── pages/            # Page controllers (debate.js, verdict.js, feed.js, etc.)
│   ├── static/               # Assets, icons, favicons
│   ├── index.html            # Landing & live debates feed
│   ├── debate.html           # Live Arena room (4 rounds, chat, reactions, poll)
│   ├── verdict.html          # Verdict page (scorecards, trophy card, consensus grid)
│   ├── ask.html              # Debate creator wizard (mode selection & topic setup)
│   ├── profile.html          # User profile & statistics
│   └── search.html           # Semantic vector search
├── INTERVIEW_PREP.md         # Comprehensive system architecture & interview guide
├── pytest.ini                # Pytest configuration
└── README.md                 # Project documentation
```

---

## 🌐 Production Deployment (Render)

Provok is pre-configured for continuous deployment on [Render](https://render.com):
- **Build Command**: `pip install -r backend/requirements.txt`
- **Start Command**: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
- **Health Check**: `/health`

---

## 📄 License
MIT License. Open source and built for rigorous public discourse.
