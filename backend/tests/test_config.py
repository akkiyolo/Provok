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
