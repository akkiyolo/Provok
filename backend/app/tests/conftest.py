import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac
