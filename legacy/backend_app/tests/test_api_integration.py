import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.database.core import get_db

# We'll create a mock DB session to prevent writing to production Neon database
from unittest.mock import AsyncMock, MagicMock
from backend.app.models.user import User
import uuid
from datetime import datetime, timezone
from backend.app.auth.security import get_password_hash

async def override_get_db():
    # Provide a fully mocked AsyncSession
    mock_session = AsyncMock()
    
    # Mocking the `scalar` result for login
    mock_user = User(
        id=uuid.uuid4(),
        email="integration@example.com",
        username="integration",
        password_hash=get_password_hash("testpass"),
        is_active=True,
        created_at=datetime.now(timezone.utc)
    )
    
    # Just return this user for any select
    mock_session.scalar.return_value = mock_user
    mock_session.scalars.return_value.all.return_value = []
    
    yield mock_session

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac

@pytest.mark.asyncio
async def test_login_integration(client: AsyncClient):
    """Test actual login route with mocked database."""
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "integration@example.com", "password": "testpass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

@pytest.mark.asyncio
async def test_invalid_login(client: AsyncClient):
    """Test login with wrong password."""
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "integration@example.com", "password": "wrongpassword"},
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    assert response.status_code == 400
    assert "Incorrect email or password" in response.json()["detail"]

@pytest.mark.asyncio
async def test_get_live_feed(client: AsyncClient):
    """Test the feed endpoint without auth."""
    # This hits /api/v1/live which we implemented
    response = await client.get("/api/v1/live")
    
    assert response.status_code == 200
    assert "debates" in response.json()
    assert isinstance(response.json()["debates"], list)

@pytest.mark.asyncio
async def test_poll_endpoints():
    """Test audience poll calculation logic."""
    from backend.app.api.debates import _get_poll_tally
    from backend.app.models.debate import Verdict

    mock_db = AsyncMock()

    # 1. Empty tally
    mock_db.scalar.return_value = None
    empty_tally = await _get_poll_tally(uuid.uuid4(), mock_db)
    assert empty_tally["total_votes"] == 0
    assert empty_tally["pct_for"] == 50.0
    assert empty_tally["pct_against"] == 50.0
    assert empty_tally["winner_side"] == "TIE"

    # 2. Tally with votes
    mock_verdict = Verdict(details_json={"audience_poll": {"for_votes": 8, "against_votes": 2}})
    mock_db.scalar.return_value = mock_verdict
    tally_for = await _get_poll_tally(uuid.uuid4(), mock_db)
    assert tally_for["total_votes"] == 10
    assert tally_for["pct_for"] == 80.0
    assert tally_for["pct_against"] == 20.0
    assert tally_for["winner_side"] == "FOR"

    mock_verdict_against = Verdict(details_json={"audience_poll": {"for_votes": 1, "against_votes": 3}})
    mock_db.scalar.return_value = mock_verdict_against
    tally_against = await _get_poll_tally(uuid.uuid4(), mock_db)
    assert tally_against["total_votes"] == 4
    assert tally_against["pct_for"] == 25.0
    assert tally_against["pct_against"] == 75.0
    assert tally_against["winner_side"] == "AGAINST"

def test_dialectical_badges_logic():
    """Verify dialectical badge assignment across phases."""
    from backend.app.api.debates import _get_dialectical_badges

    badges_r1 = _get_dialectical_badges(1, "OPENING", "FOR")
    assert "Core Thesis" in badges_r1
    assert "Empirical Baseline" in badges_r1

    badges_r2 = _get_dialectical_badges(2, "REBUTTAL", "AGAINST")
    assert "Logical Scrutiny" in badges_r2 or "Fallacy Exposure" in badges_r2

    badges_r3 = _get_dialectical_badges(3, "CROSS_EXAMINATION", "AGAINST")
    assert "Cross-Defense" in badges_r3 or "Clarification" in badges_r3

    badges_r4 = _get_dialectical_badges(4, "CLOSING", "FOR")
    assert "Closing Synthesis" in badges_r4

