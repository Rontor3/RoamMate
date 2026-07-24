"""Sprint 8 — place card vibe_id, vibe_hint, and area field tests."""
import pytest
from unittest.mock import AsyncMock, patch


def _make_place(place_id: str, name: str, rating: float = 4.5) -> dict:
    """Helper — raw Maps dict."""
    return {"place_id": place_id, "name": name, "rating": rating, "user_ratings_total": 100,
            "types": ["tourist_attraction"], "photo_url": None, "lat": 15.6, "lng": 73.7}


@pytest.mark.asyncio
async def test_fetch_place_cards_includes_vibe_id_and_vibe_hint():
    """Groq returns new {hook, vibe_id, vibe_hint} shape — place dicts include all three."""
    from app.services.stage_machine import fetch_place_cards
    from app.models import TravelIntent, Destination

    state = {
        "destination": "Goa",
        "selected_areas": ["vagator"],
        "selected_vibe_ids": ["adv"],
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
        "experience_types": [],
        "travel_intent": TravelIntent(destination=Destination(city="Goa")),
        "reddit_signals": {},
        "blog_signals": {},
    }
    mock_cats = [{"label": "Beaches", "query": "beach surf water"}]
    mock_places = [_make_place("baga", "Baga Beach", 4.5)]
    mock_hooks = {
        "baga": {
            "hook": "Party meets the sea",
            "vibe_id": "adv",
            "vibe_hint": "surfing, swimming, beach volleyball",
        }
    }

    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock,
               side_effect=[mock_cats, mock_hooks]), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock,
               return_value=mock_places), \
         patch("app.services.stage_machine.asyncio.create_task"):
        result = await fetch_place_cards(state, area_id="vagator")

    assert result, "Expected non-empty result"
    place = result[0]["places"][0]
    assert place["vibe_id"] == "adv"
    assert place["vibe_hint"] == "surfing, swimming, beach volleyball"
    assert place["hook"] == "Party meets the sea"


@pytest.mark.asyncio
async def test_fetch_place_cards_backwards_compat_flat_hook():
    """Groq returns old flat-string hook — hook preserved, vibe_id defaults to 'adv', vibe_hint to ''."""
    from app.services.stage_machine import fetch_place_cards
    from app.models import TravelIntent, Destination

    state = {
        "destination": "Goa",
        "selected_areas": ["vagator"],
        "selected_vibe_ids": [],
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
        "experience_types": [],
        "travel_intent": TravelIntent(destination=Destination(city="Goa")),
        "reddit_signals": {},
        "blog_signals": {},
    }
    mock_cats = [{"label": "Beaches", "query": "beach"}]
    mock_places = [_make_place("baga", "Baga Beach", 4.5)]
    mock_hooks = {"baga": "Party meets the sea"}  # old flat string format

    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock,
               side_effect=[mock_cats, mock_hooks]), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock,
               return_value=mock_places), \
         patch("app.services.stage_machine.asyncio.create_task"):
        result = await fetch_place_cards(state, area_id="vagator")

    place = result[0]["places"][0]
    assert place["hook"] == "Party meets the sea"
    assert place["vibe_id"] == "adv"
    assert place["vibe_hint"] == ""


@pytest.mark.asyncio
async def test_fetch_place_cards_includes_area_name():
    """Each place dict includes 'area' set to the human-readable area display name."""
    from app.services.stage_machine import fetch_place_cards
    from app.models import TravelIntent, Destination

    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa"],
        "selected_vibe_ids": ["hid"],
        "area_cards": [{"id": "north_goa", "name": "North Goa"}],
        "experience_types": [],
        "travel_intent": TravelIntent(destination=Destination(city="Goa")),
        "reddit_signals": {},
        "blog_signals": {},
    }
    mock_cats = [{"label": "Forts", "query": "fort historical landmark"}]
    mock_places = [_make_place("chapora", "Chapora Fort", 4.5)]
    mock_hooks = {
        "chapora": {
            "hook": "Dil Chahta Hai fort",
            "vibe_id": "hid",
            "vibe_hint": "photography, history walks, sunset views",
        }
    }

    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock,
               side_effect=[mock_cats, mock_hooks]), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock,
               return_value=mock_places), \
         patch("app.services.stage_machine.asyncio.create_task"):
        result = await fetch_place_cards(state, area_id="north_goa")

    assert result[0]["places"][0]["area"] == "North Goa"
