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


# ── fetch_vibe_cards ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_vibe_cards_returns_base_when_no_destination():
    from app.services.stage_machine import fetch_vibe_cards
    result = await fetch_vibe_cards({})
    assert len(result) == 4
    assert {c["id"] for c in result} == {"adv", "loc", "spt", "hid"}
    for card in result:
        assert "label" in card and "eyebrow" in card and "description" in card and "tags" in card


@pytest.mark.asyncio
async def test_fetch_vibe_cards_returns_cache_hit():
    from app.services.stage_machine import fetch_vibe_cards
    cached = [{"id": "adv", "description": "cached hook"}]
    with patch("app.services.stage_machine.get_cached", return_value=cached):
        result = await fetch_vibe_cards({"destination": "Goa"})
    assert result == cached


@pytest.mark.asyncio
async def test_fetch_vibe_cards_attaches_groq_destination_hook():
    from app.services.stage_machine import fetch_vibe_cards
    hooks = {
        "adv": "Cliff jumps at Vagator, paragliding at Arambol",
        "loc": "Spice farms in Ponda, Portuguese churches",
        "spt": "Sunset at Chapora Fort, night bazaar at Arpora",
        "hid": "Turtle nesting at Morjim, secluded Cola beach",
    }
    with patch("app.services.stage_machine.get_cached", return_value=None):
        with patch("app.services.stage_machine.set_cached", new_callable=AsyncMock):
            with patch("app.services.stage_machine._groq_json", return_value=hooks):
                result = await fetch_vibe_cards({"destination": "Goa"})
    adv = next(c for c in result if c["id"] == "adv")
    assert adv["description"] == "Cliff jumps at Vagator, paragliding at Arambol"


@pytest.mark.asyncio
async def test_fetch_vibe_cards_falls_back_to_base_on_groq_failure():
    from app.services.stage_machine import fetch_vibe_cards, BASE_VIBE_CARDS
    with patch("app.services.stage_machine.get_cached", return_value=None):
        with patch("app.services.stage_machine.set_cached", new_callable=AsyncMock):
            with patch("app.services.stage_machine._groq_json", return_value=None):
                result = await fetch_vibe_cards({"destination": "Goa"})
    assert len(result) == 4
    adv = next(c for c in result if c["id"] == "adv")
    base_adv = next(c for c in BASE_VIBE_CARDS if c["id"] == "adv")
    assert adv["description"] == base_adv["description"]
