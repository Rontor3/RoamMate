"""Integration tests for the FastAPI /chat and /reverse-geocode endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_chat_endpoint_returns_response():
    pytest.skip("Requires full env (Groq API, Redis, SQLite)")


@pytest.mark.asyncio
async def test_reverse_geocode_returns_label():
    pytest.skip("Requires GOOGLE_MAPS_KEY in env")


@pytest.mark.asyncio
async def test_health_endpoint():
    from app.api.server import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
