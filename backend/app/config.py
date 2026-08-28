"""
PROVOK — Application Configuration

Pydantic Settings sourced from environment variables / .env file.
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # provok/
BACKEND_DIR = BASE_DIR / "backend"
FRONTEND_DIR = BASE_DIR / "frontend"
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    """Central configuration — every value maps to an env var."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────
    app_name: str = "PROVOK"
    app_env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    api_v1_prefix: str = "/api/v1"

    # ── Database (Neon PostgreSQL) ─────────────────────────────
    database_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 10

    # ── Redis ──────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"
    redis_cache_url: str = "redis://redis:6379/1"
    redis_pubsub_url: str = "redis://redis:6379/2"

    # ── Celery ─────────────────────────────────────────────────
    celery_broker_url: str = "redis://redis:6379/3"
    celery_result_backend: str = "redis://redis:6379/4"

    # ── Auth / JWT ─────────────────────────────────────────────
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    # ── Google OAuth ───────────────────────────────────────────
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/google/callback"

    # ── AI / LLM ──────────────────────────────────────────────
    mistral_api_key: str = ""
    zai_api_key: str = ""

    research_provider: str = "mistral"
    expert_provider: str = "zai"
    skeptic_provider: str = "zai"
    strategist_provider: str = "mistral"
    judge_provider: str = "zai"

    llm_model: str = "mistral-medium-latest"
    research_model: str = "mistral-small-latest"
    expert_model: str = "glm-5.1"
    skeptic_model: str = "glm-5.1"
    strategist_model: str = "mistral-medium-latest"
    judge_model: str = "glm-5.1"

    llm_temperature: float = 0.4
    llm_max_tokens: int = 4000
    llm_request_timeout: int = 60
    llm_max_retries: int = 3

    # ── Embeddings ─────────────────────────────────────────────
    embedding_provider: str = "Google"
    google_api_key: str = ""
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 1536

    # ── Search ─────────────────────────────────────────────────
    search_provider: str = "TAVILY"
    search_api_key: str = ""
    max_search_results: int = 5
    max_source_length: int = 12000

    # ── AWS S3 ─────────────────────────────────────────────────
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_bucket_name: str = "provok-dev"
    s3_upload_prefix: str = "uploads/"

    # ── WebSocket ──────────────────────────────────────────────
    websocket_path: str = "/ws"
    websocket_heartbeat_seconds: int = 30
    websocket_reconnect_seconds: int = 3

    # ── Debate ─────────────────────────────────────────────────
    default_rounds: int = 4
    round_1_max_contributions: int = 3
    round_2_max_contributions: int = 3
    round_3_max_questions: int = 3
    round_4_max_contributions: int = 2

    live_opening_timeout_seconds: int = 180
    live_rebuttal_timeout_seconds: int = 180
    live_cross_exam_timeout_seconds: int = 90
    live_closing_timeout_seconds: int = 180

    async_default_response_hours: int = 24
    async_min_response_hours: int = 1
    async_max_response_hours: int = 168

    # ── Audience ───────────────────────────────────────────────
    audience_voting_duration_seconds: int = 60
    max_audience_challenges_per_round: int = 20
    viewer_count_update_seconds: int = 5

    # ── Recommendation ─────────────────────────────────────────
    recommendation_enabled: bool = True
    recommendation_candidate_limit: int = 200
    recommendation_result_limit: int = 20
    recommendation_cache_seconds: int = 300

    # ── Rate Limiting ──────────────────────────────────────────
    rate_limit_enabled: bool = True
    rate_limit_login: str = "10/minute"
    rate_limit_register: str = "5/minute"
    rate_limit_create_debate: str = "10/hour"
    rate_limit_argument: str = "30/hour"
    rate_limit_vote: str = "60/hour"
    rate_limit_challenge: str = "30/hour"
    rate_limit_search: str = "120/minute"

    # ── Development ────────────────────────────────────────────
    seed_database: bool = True
    enable_swagger: bool = True
    enable_debug_routes: bool = False

    # ── Helpers ────────────────────────────────────────────────

    @property
    def async_database_url(self) -> str:
        """Convert postgres:// to postgresql+asyncpg:// for SQLAlchemy."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        # asyncpg doesn't support channel_binding param — strip it
        if "channel_binding=" in url:
            import re
            url = re.sub(r"[&?]channel_binding=[^&]*", "", url)
        return url

    @property
    def sync_database_url(self) -> str:
        """For Alembic migrations — use psycopg sync driver."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
