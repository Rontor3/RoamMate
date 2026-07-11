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


# ── fetch_area_cards ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_area_cards_returns_empty_when_no_destination():
    from app.services.stage_machine import fetch_area_cards
    result = await fetch_area_cards({})
    assert result == []


@pytest.mark.asyncio
async def test_fetch_area_cards_returns_and_populates_state_on_cache_hit():
    from app.services.stage_machine import fetch_area_cards
    cached = [{"id": "vagator", "name": "Vagator", "zone": "North Goa",
               "teaser": "Rocky cliffs...", "summary": "Full text...",
               "tags": ["cliffs"], "photo_url": None}]
    with patch("app.services.stage_machine.get_cached", return_value=cached):
        state = {"destination": "Goa", "experience_types": ["beach_coast"]}
        result = await fetch_area_cards(state)
    assert result == cached
    assert state["area_cards"] == cached


@pytest.mark.asyncio
async def test_fetch_area_cards_flat_tier_sets_zone_to_none():
    from app.services.stage_machine import fetch_area_cards
    scale_response = {"tier": "flat", "zones": []}
    areas_response = [
        {"id": "bhushi", "name": "Bhushi Dam Area", "zone": "ignored",
         "teaser": "Cascading steps...", "summary": "...", "tags": ["waterfall"]}
    ]
    with patch("app.services.stage_machine.get_cached", return_value=None):
        with patch("app.services.stage_machine.set_cached", new_callable=AsyncMock):
            with patch("app.services.stage_machine._groq_json",
                       side_effect=[scale_response, areas_response]):
                with patch("app.services.stage_machine.tavily_search", return_value=[]):
                    with patch("app.services.stage_machine.fetch_place_photos", return_value=[]):
                        state = {"destination": "Lonavala", "experience_types": ["hills_nature"]}
                        result = await fetch_area_cards(state)
    assert result[0]["zone"] is None


@pytest.mark.asyncio
async def test_fetch_area_cards_returns_empty_when_groq_area_gen_fails():
    from app.services.stage_machine import fetch_area_cards
    scale_response = {"tier": "flat", "zones": []}
    with patch("app.services.stage_machine.get_cached", return_value=None):
        with patch("app.services.stage_machine.set_cached", new_callable=AsyncMock):
            with patch("app.services.stage_machine._groq_json",
                       side_effect=[scale_response, None]):  # area gen returns None
                with patch("app.services.stage_machine.tavily_search", return_value=[]):
                    state = {"destination": "Goa", "experience_types": ["beach_coast"]}
                    result = await fetch_area_cards(state)
    assert result == []


@pytest.mark.asyncio
async def test_fetch_area_cards_uses_branch_b_vibe_ids_for_cache_key():
    from app.services.stage_machine import fetch_area_cards
    cached = [{"id": "vagator", "name": "Vagator", "zone": None,
               "teaser": "...", "summary": "...", "tags": [], "photo_url": None}]
    with patch("app.services.stage_machine.get_cached", return_value=cached) as mock_get:
        state = {"destination": "Goa", "selected_vibe_ids": ["adv", "hid"]}
        result = await fetch_area_cards(state)
    # Cache key must use sorted vibe IDs when no experience_types
    mock_get.assert_called_once_with("area_cards:goa:adv|hid")
    assert result == cached


# ── resolve_stage ─────────────────────────────────────────────────────────────

def test_resolve_stage_returns_area_selected_when_area_set():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_area": "vagator"}
    assert resolve_stage(state) == "area_selected"


def test_resolve_stage_area_selected_takes_priority_over_vibes_confirmed():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "vibes_confirmed": True, "selected_area": "vagator"}
    assert resolve_stage(state) == "area_selected"


def test_resolve_stage_vibe_selected_still_works_without_area():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "vibes_confirmed": True}
    assert resolve_stage(state) == "vibe_selected"


# ── determine_action ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_determine_action_branch_a_shows_area_cards_directly():
    from app.services.stage_machine import determine_action
    areas = [{"id": "vagator", "name": "Vagator"}]
    with patch("app.services.stage_machine.fetch_area_cards",
               new_callable=AsyncMock, return_value=areas):
        action, payload = await determine_action(
            "destination_known",
            {"destination": "Goa", "experience_types": ["beach_coast"]}
        )
    assert action == "show_area_cards"
    assert payload["areas"] == areas


@pytest.mark.asyncio
async def test_determine_action_branch_b_shows_vibe_cards():
    from app.services.stage_machine import determine_action
    vibes = [{"id": "adv", "description": "Cliff jumps at Vagator"}]
    with patch("app.services.stage_machine.fetch_vibe_cards",
               new_callable=AsyncMock, return_value=vibes):
        action, payload = await determine_action(
            "destination_known",
            {"destination": "Goa"}   # no experience_types
        )
    assert action == "show_vibe_cards"
    assert payload["vibes"] == vibes


@pytest.mark.asyncio
async def test_determine_action_vibe_selected_shows_area_cards():
    from app.services.stage_machine import determine_action
    areas = [{"id": "palolem", "name": "Palolem"}]
    with patch("app.services.stage_machine.fetch_area_cards",
               new_callable=AsyncMock, return_value=areas):
        action, payload = await determine_action(
            "vibe_selected",
            {"destination": "Goa", "vibes_confirmed": True, "selected_vibe_ids": ["hid"]}
        )
    assert action == "show_area_cards"
    assert payload["areas"] == areas


@pytest.mark.asyncio
async def test_determine_action_area_selected_returns_stub():
    from app.services.stage_machine import determine_action
    action, payload = await determine_action(
        "area_selected",
        {"destination": "Goa", "selected_area": "vagator"}
    )
    assert action == "show_place_cards"
    assert payload == {"places": []}
