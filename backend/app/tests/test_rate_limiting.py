"""Test rate limiting on sensitive routes."""
import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.config import get_settings

@pytest.mark.asyncio
async def test_rate_limiting_trigger():
    """Verify that hammering an endpoint triggers 429 Too Many Requests."""
    settings = get_settings()
    # We test on /api/v1/auth/login with invalid creds in rapid succession
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Settings rate_limit_login is 10/minute
        hit_429 = False
        for i in range(15):
            res = await client.post(
                "/api/v1/auth/login",
                data={"username": "attacker@test.com", "password": "wrongpassword"},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if res.status_code == 429:
                hit_429 = True
                break
        
        assert hit_429, "Rate limiter did not throttle excessive login requests!"
