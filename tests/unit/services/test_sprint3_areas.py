"""Unit tests for Sprint 3 area cards + vibe card content."""
import json
import pytest
from unittest.mock import AsyncMock, patch


# ── area_cache ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_cached_returns_none_on_miss():
    from app.services.area_cache import get_cached
    mock_r = AsyncMock()
    mock_r.get.return_value = None
    with patch("app.services.area_cache._get_redis", return_value=mock_r):
        result = await get_cached("area_cards:goa:beach_coast")
    assert result is None


@pytest.mark.asyncio
async def test_get_cached_returns_parsed_list_on_hit():
    from app.services.area_cache import get_cached
    data = [{"id": "vagator", "name": "Vagator"}]
    mock_r = AsyncMock()
    mock_r.get.return_value = json.dumps(data)
    with patch("app.services.area_cache._get_redis", return_value=mock_r):
        result = await get_cached("area_cards:goa:beach_coast")
    assert result == data


@pytest.mark.asyncio
async def test_get_cached_returns_none_when_redis_unavailable():
    from app.services.area_cache import get_cached
    with patch("app.services.area_cache._get_redis", return_value=None):
        result = await get_cached("area_cards:goa:beach_coast")
    assert result is None


@pytest.mark.asyncio
async def test_set_cached_writes_to_redis_with_correct_ttl():
    from app.services.area_cache import set_cached
    data = [{"id": "vagator", "name": "Vagator"}]
    mock_r = AsyncMock()
    with patch("app.services.area_cache._get_redis", return_value=mock_r):
        await set_cached("area_cards:goa:beach_coast", data)
    mock_r.setex.assert_called_once()
    args = mock_r.setex.call_args[0]
    assert args[0] == "area_cards:goa:beach_coast"
    assert args[1] == 86400
    assert json.loads(args[2]) == data


@pytest.mark.asyncio
async def test_set_cached_is_silent_when_redis_unavailable():
    from app.services.area_cache import set_cached
    with patch("app.services.area_cache._get_redis", return_value=None):
        await set_cached("area_cards:goa:beach_coast", [{"id": "vagator"}])  # must not raise
