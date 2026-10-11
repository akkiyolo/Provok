"""Health endpoints, as uptime monitors and CI probe them."""
from __future__ import annotations


async def test_health_answers_get_and_head(client) -> None:
    for path in ("/health", "/health/ready"):
        r = await client.get(path)
        assert r.status_code == 200, (path, r.text)
        # Monitors (and wait-on) often send HEAD; a 405 would read as "site down".
        r = await client.head(path)
        assert r.status_code == 200, path
    assert (await client.get("/health/ready")).json()["checks"]["database"] == "ok"
