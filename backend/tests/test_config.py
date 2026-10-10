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
