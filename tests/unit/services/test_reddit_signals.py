"""Unit tests for reddit_signals."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_build_reddit_queries_generates_queries():
    """build_reddit_queries() returns 1-4 queries for a given intent."""
    from app.services.reddit_signals import build_reddit_queries
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    queries = build_reddit_queries(intent)
    assert isinstance(queries, list)
    assert len(queries) >= 1


@pytest.mark.asyncio
async def test_extract_place_signals_returns_dict():
    """_extract_place_signals() returns dict with place_signals key."""
    from app.services.reddit_signals import _extract_place_signals
    result = await _extract_place_signals("TITLE: Great cafe\nTEXT: Loved it", "Goa")
    assert "place_signals" in result
