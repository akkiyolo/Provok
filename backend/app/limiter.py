"""
PROVOK — Rate Limiting Infrastructure.

Uses SlowAPI for IP-based / user-based rate limiting to prevent API abuse,
brute-force login attempts, and LLM cost drainage.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.app.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
    default_limits=[],
    headers_enabled=False,
)
