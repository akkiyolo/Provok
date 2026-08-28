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
