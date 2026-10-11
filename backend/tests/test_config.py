"""Settings normalisation."""
from __future__ import annotations

import pytest

from backend.app.core.config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        (
            "postgresql://u:p@h.neon.tech/db?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@h.neon.tech/db?ssl=require",
        ),
        ("postgresql+asyncpg://u:p@h/db?ssl=require", "postgresql+asyncpg://u:p@h/db?ssl=require"),
    ],
)
def test_database_url_is_normalised_for_asyncpg(raw: str, expected: str) -> None:
    assert Settings(database_url=raw).database_url == expected


def test_production_refuses_razorpay_without_webhook_secret() -> None:
    safe = {"app_env": "production", "jwt_secret_key": "x" * 48, "cookie_secure": True, "cors_origins": "https://provok.app",
            "email_provider": "resend", "razorpay_key_id": "rzp_live_x", "razorpay_key_secret": "secret"}
    with pytest.raises(ValueError, match="RAZORPAY_WEBHOOK_SECRET"):
        Settings(**safe, razorpay_webhook_secret="")
    assert Settings(**safe, razorpay_webhook_secret="whsec").razorpay_enabled


def test_bedrock_models_are_reachable_through_the_region_not_a_maker_key() -> None:
    qwen = "bedrock/converse/qwen.qwen3-235b-a22b-2507-v1:0"
    off, on = Settings(bedrock_region=""), Settings(bedrock_region="ap-south-1")
    assert not off.provider_configured("qwen", qwen)
    assert on.provider_configured("qwen", qwen)
    # A Bedrock-hosted Claude needs no Anthropic key, and a direct Anthropic model still does.
    assert on.provider_configured("anthropic", "bedrock/converse/in.anthropic.claude-haiku-4-5-20251001-v1:0")
    assert not on.provider_configured("anthropic", "anthropic/claude-sonnet-5-5")


def test_every_bedrock_seed_model_has_a_known_price_or_is_disabled() -> None:
    """The daily spend kill-switch relies on LiteLLM pricing each call; an unpriced model would log $0."""
    import json
    from pathlib import Path

    import litellm

    seed = json.loads((Path(__file__).parents[1] / "app" / "llm" / "model_registry.seed.json").read_text("utf-8"))
    for m in seed:
        if not m["litellm_id"].startswith("bedrock/") or m.get("enabled", True) is False:
            continue
        model_id = m["litellm_id"].removeprefix("bedrock/converse/")
        assert model_id in litellm.model_cost, f"{m['key']}: LiteLLM has no price for {model_id}"
