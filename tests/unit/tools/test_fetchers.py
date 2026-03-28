"""Unit tests for fetchers — tests each fetcher with mock call_tool responses."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_places_fetcher_returns_list():
    mock_result = {"places": [{"name": "Test Cafe", "rating": 4.5}]}
    with patch("app.tools.registry.call_tool", new=AsyncMock(return_value=mock_result)):
        from app.tools.fetchers.places import search_places
        result = await search_places("Goa")
        assert isinstance(result, list)


@pytest.mark.asyncio
async def test_weather_fetcher_returns_dict():
    mock_result = {"temperature": 28, "description": "sunny"}
    with patch("app.tools.registry.call_tool", new=AsyncMock(return_value=mock_result)):
        from app.tools.fetchers.weather import get_current_weather
        result = await get_current_weather("Goa")
        assert result.get("temperature") == 28


@pytest.mark.asyncio
async def test_blogs_fetcher_returns_list():
    mock_result = {"sources": [{"url": "https://lonelyplanet.com", "snippet": "...", "final_score": 0.8}]}
    with patch("app.tools.registry.call_tool", new=AsyncMock(return_value=mock_result)):
        from app.tools.fetchers.blogs import search_travel_blogs
        result = await search_travel_blogs("Goa")
        assert isinstance(result, list)


@pytest.mark.asyncio
async def test_hotels_fetcher_returns_list():
    mock_result = {"hotels": [{"name": "Beach Resort", "price": 5000}]}
    with patch("app.tools.registry.call_tool", new=AsyncMock(return_value=mock_result)):
        from app.tools.fetchers.hotels_flights import search_hotels
        result = await search_hotels("Goa")
        assert isinstance(result, list)
        assert result[0]["name"] == "Beach Resort"
