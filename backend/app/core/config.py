"""
Provok — application configuration.

Every tunable (limits, prices, timings, model keys, feature defaults) is sourced
from the environment. Nothing in the codebase hardcodes these values; read them
from `get_settings()`.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]  # repo root
BACKEND_DIR = BASE_DIR / "backend"
APP_DIR = BACKEND_DIR / "app"

_WEAK_SECRETS = {"", "changeme", "secret", "your-secret-key-here", "dev-secret-change-me"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ─────────────────────────────────────────────────────────────
    app_name: str = "Provok"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_prefix: str = "/api/v1"
    # Public URL of the web app (used in emails, OAuth redirects, share links).
    web_url: str = "http://localhost:3000"
    # Public URL of this API (used for OAuth callback + websocket URL hints).
    api_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:3000"
    # Number of trusted reverse proxies in front of the API (for X-Forwarded-For).
    trusted_proxy_count: int = 0
    max_request_body_bytes: int = 1_000_000
    max_upload_bytes: int = 5_000_000
    enable_docs: bool = True
    release: str = "dev"

    # ── Database / Redis ────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://provok@localhost:54329/provok_dev"
    database_pool_size: int = 10
    database_max_overflow: int = 10
    database_statement_timeout_ms: int = 15_000
    # Set true when connecting through PgBouncer in transaction mode (disables prepared stmt cache).
    database_pgbouncer: bool = False
    redis_url: str = "redis://localhost:6379/0"

    # ── Auth ────────────────────────────────────────────────────────────
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_issuer: str = "provok"
    jwt_audience: str = "provok-web"
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_days: int = 30
    ws_ticket_ttl_seconds: int = 60
    email_token_ttl_minutes: int = 60 * 24
    password_reset_ttl_minutes: int = 30
    refresh_cookie_name: str = "provok_rt"
    cookie_domain: str | None = None
    cookie_secure: bool = False
    require_verified_email_to_debate: bool = True
    google_client_id: str = ""
    google_client_secret: str = ""

    # ── Email ───────────────────────────────────────────────────────────
    email_provider: Literal["console", "smtp", "resend", "ses"] = "console"
    email_from: str = "Provok <no-reply@provok.app>"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    resend_api_key: str = ""
    # Amazon SES (email_provider=ses): credentials come from the instance/task role, never from env.
    ses_region: str = "ap-south-1"

    # ── LLM providers (LiteLLM reads these from the environment) ────────
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    google_api_key: str = ""  # legacy alias for gemini_api_key
    groq_api_key: str = ""
    mistral_api_key: str = ""
    # Amazon Bedrock: many model families through the server's own AWS role (no API key). Empty = off.
    bedrock_region: str = ""
    model_registry_seed_path: str = str(APP_DIR / "llm" / "model_registry.seed.json")
    utility_model_key: str = "gemini_flash"
    utility_fallback_model_keys: str = "groq_gpt_oss_small,claude_haiku"
    judge_model_keys: str = "judge_primary,judge_secondary,judge_groq"  # ordered preference list
    default_swarm_model_key: str = "gemini_flash"
    llm_timeout_seconds: int = 60
    llm_max_output_tokens: int = 900
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""
    daily_llm_spend_alert_usd: float | None = None
    # Deterministic fake model for local dev and browser E2E (no provider keys, no cost). Refused in production.
    llm_fake: bool = False

    # ── Research ────────────────────────────────────────────────────────
    tavily_api_key: str = ""
    search_api_key: str = ""  # legacy alias for tavily_api_key
    research_max_results: int = 5
    research_max_facts: int = 12
    citation_fetch_timeout_seconds: int = 8
    citation_fetch_max_bytes: int = 400_000

    # ── Debate engine ───────────────────────────────────────────────────
    default_word_limit: int = 200
    min_word_limit: int = 50
    max_word_limit: int = 500
    cross_exam_answer_word_limit: int = 80
    live_turn_seconds: int = 120
    video_turn_seconds: int = 90
    async_turn_seconds: int = 24 * 3600
    swarm_turn_timeout_seconds: int = 240
    live_challenge_timeout_seconds: int = 15 * 60
    async_challenge_timeout_seconds: int = 48 * 3600
    fallback_offer_timeout_seconds: int = 7 * 24 * 3600
    video_lobby_timeout_seconds: int = 10 * 60
    live_round_vote_window_seconds: int = 30
    async_final_vote_window_seconds: int = 6 * 3600
    live_final_vote_window_seconds: int = 90
    close_margin: float = 0.5
    elo_k_factor: int = 32
    new_account_vote_weight: float = 0.5
    new_account_days: int = 7
    question_min_chars: int = 10
    question_max_chars: int = 280

    # ── Monetisation ────────────────────────────────────────────────────
    free_ai_debates: int = 3
    standard_credit_cost: int = 1
    flagship_credit_cost: int = 4
    free_debates_cover_flagship: bool = False
    credit_packs_json: str = (
        '[{"id":"starter","credits":5,"amount_inr":99,"label":"Starter"},'
        '{"id":"regular","credits":15,"amount_inr":249,"label":"Regular"},'
        '{"id":"pro","credits":40,"amount_inr":549,"label":"Pro"}]'
    )
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # ── Video ───────────────────────────────────────────────────────────
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    video_free_minutes_per_month: int | None = None
    video_recording_enabled: bool = True
    clip_min_seconds: int = 30
    clip_max_seconds: int = 60

    # ── Android app (Trusted Web Activity) ──────────────────────────────
    # Served as /.well-known/assetlinks.json so Android opens the site full-screen inside the app.
    android_package: str = ""  # e.g. in.provok.app (staging builds use in.provok.app.staging)
    android_cert_sha256: str = ""  # comma-separated signing-cert SHA-256 fingerprints (upload key + Play app signing)

    # ── Storage (S3-compatible: AWS S3, R2, Supabase Storage …) ─────────
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_dir: str = str(BASE_DIR / "var" / "uploads")
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_endpoint_url: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_public_base_url: str = ""

    # ── Safety ──────────────────────────────────────────────────────────
    blocked_topic_categories: str = "politics,religion,caste"
    injection_strikes_to_restrict: int = 3
    moderation_enabled: bool = True

    # ── Rate limits ("<count>/<seconds>") ───────────────────────────────
    rate_limit_enabled: bool = True
    rl_login_ip: str = "10/60"
    rl_login_account: str = "8/900"
    rl_signup_ip: str = "5/3600"
    rl_password_reset: str = "5/3600"
    rl_debate_create_user: str = "10/3600"
    rl_ai_debates_user_day: str = "15/86400"
    rl_turn_user: str = "6/60"
    rl_vote_user: str = "20/60"
    rl_report_user: str = "20/3600"
    rl_topic_check_user: str = "30/60"
    rl_general_ip: str = "300/60"
    rl_ws_reactions: str = "10/10"
    rl_events_ip: str = "120/60"

    # ── Observability ───────────────────────────────────────────────────
    sentry_dsn_api: str = ""
    sentry_traces_sample_rate: float = 0.1
    log_level: str = "INFO"

    # ── Worker ──────────────────────────────────────────────────────────
    embedded_worker: bool = False
    # Featured AI-vs-AI debates created automatically (UTC hours; empty disables).
    featured_ava_hours_utc: str = "4,13"
    featured_ava_per_run: int = 1
    sweeper_interval_seconds: int = 5
    # Debates paused by an AI provider failure retry themselves after this delay (max attempts per day).
    auto_resume_after_seconds: int = 300
    auto_resume_max_attempts: int = 3

    # ── Validators ──────────────────────────────────────────────────────

    @field_validator("database_url")
    @classmethod
    def _normalise_db_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://") :]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://") :]
        # Hosted Postgres (Neon, Render, ...) hands out libpq-style URLs. asyncpg takes `ssl` instead of
        # `sslmode` and has no `channel_binding` option, so translate/drop those query params.
        parts = urlsplit(v)
        if parts.query:
            params: list[tuple[str, str]] = []
            for key, value in parse_qsl(parts.query, keep_blank_values=True):
                if key == "sslmode":
                    params.append(("ssl", value))
                elif key != "channel_binding":
                    params.append((key, value))
            v = urlunsplit(parts._replace(query=urlencode(params)))
        return v

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.app_env == "production":
            problems: list[str] = []
            if self.debug:
                problems.append("DEBUG must be false in production")
            if self.jwt_secret_key in _WEAK_SECRETS or len(self.jwt_secret_key) < 32:
                problems.append("JWT_SECRET_KEY must be a random string of at least 32 chars")
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true in production")
            if "*" in self.cors_origins:
                problems.append("CORS_ORIGINS may not contain '*' in production")
            if self.llm_fake:
                problems.append("LLM_FAKE must be false in production")
            if self.email_provider == "console":
                problems.append("EMAIL_PROVIDER must not be 'console' in production")
            if self.razorpay_key_id and self.razorpay_key_secret and not self.razorpay_webhook_secret:
                # Without it every webhook is rejected, so a payment whose browser never returns is never credited.
                problems.append("RAZORPAY_WEBHOOK_SECRET is required when Razorpay keys are set")
            if problems:
                raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    # ── Derived helpers ─────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def android_cert_fingerprints(self) -> list[str]:
        return [f.strip().upper() for f in self.android_cert_sha256.split(",") if f.strip()]

    @property
    def blocked_categories(self) -> set[str]:
        return {c.strip().lower() for c in self.blocked_topic_categories.split(",") if c.strip()}

    @property
    def credit_packs(self) -> list[dict[str, Any]]:
        packs = json.loads(self.credit_packs_json)
        for p in packs:
            if not {"id", "credits", "amount_inr"} <= p.keys():
                raise ValueError(f"Invalid credit pack: {p}")
        return packs

    @property
    def utility_fallbacks(self) -> list[str]:
        return [k.strip() for k in self.utility_fallback_model_keys.split(",") if k.strip()]

    @property
    def judge_keys(self) -> list[str]:
        return [k.strip() for k in self.judge_model_keys.split(",") if k.strip()]

    @property
    def tavily_key(self) -> str:
        return self.tavily_api_key or self.search_api_key

    @property
    def gemini_key(self) -> str:
        return self.gemini_api_key or self.google_api_key

    @property
    def google_oauth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def razorpay_enabled(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    @property
    def livekit_enabled(self) -> bool:
        return bool(self.livekit_url and self.livekit_api_key and self.livekit_api_secret)

    def export_provider_keys(self) -> None:
        """LiteLLM reads provider keys from os.environ; mirror configured keys there."""
        mapping = {
            "OPENAI_API_KEY": self.openai_api_key,
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "GEMINI_API_KEY": self.gemini_key,
            "GROQ_API_KEY": self.groq_api_key,
            "MISTRAL_API_KEY": self.mistral_api_key,
            "LANGFUSE_PUBLIC_KEY": self.langfuse_public_key,
            "LANGFUSE_SECRET_KEY": self.langfuse_secret_key,
            "LANGFUSE_HOST": self.langfuse_host,
        }
        if self.bedrock_region:
            mapping["AWS_REGION_NAME"] = self.bedrock_region
        for k, v in mapping.items():
            if v and not os.environ.get(k):
                os.environ[k] = v
        # LiteLLM otherwise loads the nearest .env file on import, which can carry unrelated AWS keys.
        os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

    def provider_configured(self, provider: str, litellm_id: str = "") -> bool:
        """Can we reach this model? Bedrock models go through the AWS role whatever their maker (`provider`)."""
        if litellm_id.startswith("bedrock/"):
            return bool(self.bedrock_region)
        return bool(
            {
                "openai": self.openai_api_key,
                "anthropic": self.anthropic_api_key,
                "gemini": self.gemini_key,
                "groq": self.groq_api_key,
                "mistral": self.mistral_api_key,
            }.get(provider)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()

