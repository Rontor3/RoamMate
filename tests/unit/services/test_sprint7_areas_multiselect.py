# tests/unit/services/test_sprint7_areas_multiselect.py
"""Unit tests for Sprint 7: multi-select area selection."""
import pytest
from unittest.mock import AsyncMock, patch


def test_resolve_stage_selected_areas_returns_areas_selected():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_areas": ["north_goa"]}
    assert resolve_stage(state) == "areas_selected"


def test_resolve_stage_multiple_areas():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_areas": ["north_goa", "south_goa"]}
    assert resolve_stage(state) == "areas_selected"


def test_resolve_stage_empty_selected_areas_does_not_fire():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_areas": []}
    # Empty list is falsy — should fall through to destination_known
    assert resolve_stage(state) == "destination_known"


def test_resolve_stage_pending_activities_returns_areas_selected():
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
        "selected_activities": ["Sunrise Walk"],
    }
    assert resolve_stage(state) == "areas_selected"


@pytest.mark.asyncio
async def test_determine_action_areas_selected_calls_fetch_per_area():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa", "south_goa"],
        "pending_activities": {},
    }
    cat_north = [{"label": "Beaches", "places": [{"id": "baga", "name": "Baga Beach", "hook": "Party beach", "photo_url": None}]}]
    cat_south = [{"label": "Peaceful", "places": [{"id": "palolem", "name": "Palolem Beach", "hook": "Calm cove", "photo_url": None}]}]

    call_count = 0

    async def fake_fetch(state_arg, area_id=None):
        nonlocal call_count
        call_count += 1
        return cat_north if area_id == "north_goa" else cat_south

    with patch("app.services.stage_machine.fetch_place_cards", side_effect=fake_fetch):
        action, payload = await determine_action("areas_selected", state)

    assert call_count == 2
    assert action == "show_place_cards"
    # state["place_cards"] must keep the categorized shape
    assert all("places" in cat for cat in state["place_cards"]), \
        "state['place_cards'] must be a list of category dicts with a 'places' key"
    # payload["places"] is the flat list for the frontend
    assert len(payload["places"]) == 2
    place_ids = {p["id"] for p in payload["places"]}
    assert place_ids == {"baga", "palolem"}


@pytest.mark.asyncio
async def test_determine_action_areas_selected_deduplicates_places():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa", "central_goa"],
        "pending_activities": {},
    }
    shared_place = {"id": "chapora_fort", "name": "Chapora Fort", "hook": "Famous fort", "photo_url": None}
    cats = [{"label": "Forts", "places": [shared_place]}]

    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = cats
        action, payload = await determine_action("areas_selected", state)

    # Same place from two areas must appear only once
    assert len(payload["places"]) == 1
    assert payload["places"][0]["id"] == "chapora_fort"


@pytest.mark.asyncio
async def test_determine_action_areas_selected_includes_pending_activities():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa"],
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"label": "Forts", "places": []}]
        action, payload = await determine_action("areas_selected", state)

    assert action == "show_place_cards"
    assert payload["pending_activities"] == {"chapora_fort": ["Sunrise Trek"]}


@pytest.mark.asyncio
async def test_determine_action_areas_selected_pending_activities_defaults_empty():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa"],
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        action, payload = await determine_action("areas_selected", state)

    assert action == "show_place_cards"
    assert payload["pending_activities"] == {}


@pytest.mark.asyncio
async def test_intent_areas_selected_stores_area_ids():
    from app.graph.nodes.intent import detect_intent
    state = {
        "card_action": "areas_selected",
        "card_data": {"area_ids": ["north_goa", "south_goa"]},
        "destination": "Goa",
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_place_cards", {"places": [], "pending_activities": {}})
        result = await detect_intent(state)

    assert result["selected_areas"] == ["north_goa", "south_goa"]


@pytest.mark.asyncio
async def test_intent_areas_selected_skips_graph():
    from app.graph.nodes.intent import detect_intent
    state = {
        "card_action": "areas_selected",
        "card_data": {"area_ids": ["north_goa"]},
        "destination": "Goa",
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_place_cards", {"places": [], "pending_activities": {}})
        result = await detect_intent(state)

    assert result["skip_graph"] is True
    assert result["action"] == "show_place_cards"
