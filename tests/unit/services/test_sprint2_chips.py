"""Unit tests for Sprint 2 chip + destination functions."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── build_experience_chips ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_chips_plan_mode_returns_all_six():
    from app.services.stage_machine import build_experience_chips
    state = {"trip_mode": "plan"}
    chips = await build_experience_chips(state)
    assert len(chips) == 6
    ids = {c["id"] for c in chips}
    assert ids == {"beach_coast", "hills_nature", "small_town", "festival_events", "new_city", "retreat_rest"}


@pytest.mark.asyncio
async def test_build_chips_plan_mode_has_live_hook_none():
    """Chips returned in plan mode must always include live_hook key (None when no event)."""
    from app.services.stage_machine import build_experience_chips
    state = {"trip_mode": "plan"}
    result = await build_experience_chips(state)
    assert len(result) == 6
    for chip in result:
        assert "live_hook" in chip
        assert chip["live_hook"] is None


@pytest.mark.asyncio
async def test_build_chips_no_origin_returns_all_six():
    from app.services.stage_machine import build_experience_chips
    # no current_location, no travel_intent → no origin → fallback to all 6
    state = {"trip_mode": "now"}
    chips = await build_experience_chips(state)
    assert len(chips) == 6


@pytest.mark.asyncio
async def test_build_chips_now_mode_filters_to_classified_categories():
    from app.services import stage_machine
    classified = {"hills_nature": ["Lonavala", "Mahabaleshwar"], "beach_coast": ["Alibaug"]}

    with patch("app.services.stage_machine.tavily_search", new=AsyncMock(return_value=[])), \
         patch("app.services.stage_machine._classify_destinations", new=AsyncMock(return_value=classified)), \
         patch("app.services.stage_machine._extract_live_hooks", new=AsyncMock(return_value={})):
        intent = MagicMock()
        intent.origin_city = "Mumbai"
        state = {"trip_mode": "now", "current_location": None, "travel_intent": intent}
        chips = await stage_machine.build_experience_chips(state)

    chip_ids = {c["id"] for c in chips}
    assert chip_ids == {"hills_nature", "beach_coast"}
    assert "small_town" not in chip_ids


@pytest.mark.asyncio
async def test_build_chips_attaches_live_hook():
    from app.services import stage_machine
    classified = {"hills_nature": ["Lonavala"]}
    live_hooks = {"hills_nature": "Kasol Festival next weekend"}

    with patch("app.services.stage_machine.tavily_search", new=AsyncMock(return_value=[])), \
         patch("app.services.stage_machine._classify_destinations", new=AsyncMock(return_value=classified)), \
         patch("app.services.stage_machine._extract_live_hooks", new=AsyncMock(return_value=live_hooks)):
        intent = MagicMock()
        intent.origin_city = "Delhi"
        state = {"trip_mode": "now", "current_location": None, "travel_intent": intent}
        chips = await stage_machine.build_experience_chips(state)

    hills_chip = next(c for c in chips if c["id"] == "hills_nature")
    assert hills_chip.get("live_hook") == "Kasol Festival next weekend"


@pytest.mark.asyncio
async def test_build_chips_stores_candidates_in_state():
    from app.services import stage_machine
    classified = {"hills_nature": ["Lonavala"]}

    with patch("app.services.stage_machine.tavily_search", new=AsyncMock(return_value=[])), \
         patch("app.services.stage_machine._classify_destinations", new=AsyncMock(return_value=classified)), \
         patch("app.services.stage_machine._extract_live_hooks", new=AsyncMock(return_value={})):
        intent = MagicMock()
        intent.origin_city = "Mumbai"
        state = {"trip_mode": "now", "current_location": None, "travel_intent": intent}
        await stage_machine.build_experience_chips(state)

    assert state.get("destination_candidates") == classified


@pytest.mark.asyncio
async def test_build_chips_falls_back_to_all_six_when_tavily_fails():
    from app.services import stage_machine

    with patch("app.services.stage_machine.tavily_search", new=AsyncMock(return_value=[])), \
         patch("app.services.stage_machine._classify_destinations", new=AsyncMock(return_value={})), \
         patch("app.services.stage_machine._extract_live_hooks", new=AsyncMock(return_value={})):
        intent = MagicMock()
        intent.origin_city = "Mumbai"
        state = {"trip_mode": "now", "current_location": None, "travel_intent": intent}
        chips = await stage_machine.build_experience_chips(state)

    assert len(chips) == 6


@pytest.mark.asyncio
async def test_build_chips_falls_back_when_tavily_raises():
    from app.services.stage_machine import build_experience_chips
    state = {"trip_mode": "now"}
    with patch("app.services.stage_machine.get_origin", return_value={"name": "Mumbai"}):
        with patch("app.services.stage_machine.tavily_search", side_effect=Exception("timeout")):
            result = await build_experience_chips(state)
    assert len(result) == 6


@pytest.mark.asyncio
async def test_build_chips_none_trip_mode_treated_as_now():
    """trip_mode=None must route to 'now' path, not return all 6 immediately."""
    from app.services.stage_machine import build_experience_chips
    state = {"trip_mode": None}
    with patch("app.services.stage_machine.get_origin", return_value={"name": "Mumbai"}):
        with patch("app.services.stage_machine.tavily_search", new=AsyncMock(return_value=[])):
            with patch("app.services.stage_machine._classify_destinations", new=AsyncMock(return_value={})):
                result = await build_experience_chips(state)
    # With no candidates from Tavily, we fall back to all 6
    assert len(result) == 6


# ── fetch_destination_suggestions ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_suggestions_returns_empty_when_no_candidates():
    """Empty state (no experience_types, no destination_candidates) → []."""
    from app.services.stage_machine import fetch_destination_suggestions
    state = {"experience_types": [], "destination_candidates": {}}
    cards = await fetch_destination_suggestions(state)
    assert cards == []


@pytest.mark.asyncio
async def test_fetch_suggestions_filters_by_12h_limit():
    """One candidate passes OSRM (90 min), one exceeds 720 min → only 1 returned."""
    from app.services import stage_machine

    state = {
        "experience_types": ["hills_nature"],
        "destination_candidates": {"hills_nature": ["Lonavala", "FarAwayPlace"]},
        "current_location": {"lat": 19.076, "lng": 72.877, "label": "Mumbai"},
    }
    osrm_results = [
        {"distance_km": 83, "duration_mins": 90, "travel_time": "1h 30min"},
        {"distance_km": 1200, "duration_mins": 800, "travel_time": "13h 20min"},
    ]

    with patch("app.services.stage_machine.resolve_origin_coords", new=AsyncMock(return_value={"lat": 19.076, "lng": 72.877, "name": "Mumbai"})), \
         patch("app.services.stage_machine.geocode", new=AsyncMock(return_value={"lat": 18.75, "lng": 73.41})), \
         patch("app.services.stage_machine.batch_driving_times", new=AsyncMock(return_value=osrm_results)), \
         patch("app.services.stage_machine._generate_destination_hooks", new=AsyncMock(return_value=["Great trek"])), \
         patch("app.services.stage_machine.fetch_place_photos", new=AsyncMock(return_value=[])):
        cards = await stage_machine.fetch_destination_suggestions(state)

    assert len(cards) == 1
    assert cards[0]["name"] == "Lonavala"


@pytest.mark.asyncio
async def test_fetch_suggestions_skips_filter_when_no_origin():
    """When resolve_origin_coords returns None, all geocoded candidates pass through."""
    from app.services import stage_machine

    state = {
        "experience_types": ["beach_coast"],
        "destination_candidates": {"beach_coast": ["Alibaug", "Goa"]},
    }

    with patch("app.services.stage_machine.resolve_origin_coords", new=AsyncMock(return_value=None)), \
         patch("app.services.stage_machine.geocode", new=AsyncMock(return_value={"lat": 18.64, "lng": 72.87})), \
         patch("app.services.stage_machine.batch_driving_times", new=AsyncMock(return_value=[])), \
         patch("app.services.stage_machine._generate_destination_hooks", new=AsyncMock(return_value=["Sun & sand", "Beaches of Goa"])), \
         patch("app.services.stage_machine.fetch_place_photos", new=AsyncMock(return_value=[])):
        cards = await stage_machine.fetch_destination_suggestions(state)

    # Both candidates should be present (no OSRM filter applied)
    assert len(cards) == 2


@pytest.mark.asyncio
async def test_fetch_suggestions_uses_visit_fallback_on_groq_failure():
    """When _generate_destination_hooks raises or returns wrong count, hook is 'Visit {name}'."""
    from app.services import stage_machine

    state = {
        "experience_types": ["hills_nature"],
        "destination_candidates": {"hills_nature": ["Lonavala"]},
        "current_location": {"lat": 19.076, "lng": 72.877, "label": "Mumbai"},
    }

    # Simulate _groq_json returning None (Groq failure) → _generate_destination_hooks returns fallback
    with patch("app.services.stage_machine.resolve_origin_coords", new=AsyncMock(return_value={"lat": 19.076, "lng": 72.877, "name": "Mumbai"})), \
         patch("app.services.stage_machine.geocode", new=AsyncMock(return_value={"lat": 18.75, "lng": 73.41})), \
         patch("app.services.stage_machine.batch_driving_times", new=AsyncMock(return_value=[{"distance_km": 83, "duration_mins": 90, "travel_time": "1h 30min"}])), \
         patch("app.services.stage_machine._groq_json", new=AsyncMock(return_value=None)), \
         patch("app.services.stage_machine.fetch_place_photos", new=AsyncMock(return_value=[])):
        cards = await stage_machine.fetch_destination_suggestions(state)

    assert len(cards) == 1
    assert cards[0]["hook"] == "Visit Lonavala"


@pytest.mark.asyncio
async def test_fetch_destinations_reads_cached_candidates():
    from app.services import stage_machine

    state = {
        "experience_types": ["hills_nature"],
        "destination_candidates": {"hills_nature": ["Lonavala", "Mahabaleshwar"]},
        "trip_who": "solo",
        "trip_season": "monsoon",
        "current_location": {"lat": 19.076, "lng": 72.877, "label": "Mumbai"},
    }

    with patch("app.services.stage_machine.resolve_origin_coords", new=AsyncMock(return_value={"lat": 19.076, "lng": 72.877, "name": "Mumbai"})), \
         patch("app.services.stage_machine.geocode", new=AsyncMock(return_value={"lat": 18.75, "lng": 73.41})), \
         patch("app.services.stage_machine.batch_driving_times", new=AsyncMock(return_value=[{"distance_km": 83, "duration_mins": 90, "travel_time": "1h 30min"}, {"distance_km": 263, "duration_mins": 330, "travel_time": "5h 30min"}])), \
         patch("app.services.stage_machine._generate_destination_hooks", new=AsyncMock(return_value=["Great monsoon trek", "Strawberry hills"])), \
         patch("app.services.stage_machine.fetch_place_photos", new=AsyncMock(return_value=[{"name": "Lonavala", "url": "http://photo.jpg"}])):
        cards = await stage_machine.fetch_destination_suggestions(state)

    assert len(cards) >= 1
    assert cards[0]["name"] in ("Lonavala", "Mahabaleshwar")
    assert "travel_time" in cards[0]
    assert "hook" in cards[0]
    assert "distance_km" in cards[0]


@pytest.mark.asyncio
async def test_fetch_destinations_filters_over_12h():
    from app.services import stage_machine

    state = {
        "experience_types": ["hills_nature"],
        "destination_candidates": {"hills_nature": ["Lonavala", "FarAwayPlace"]},
        "current_location": {"lat": 19.076, "lng": 72.877, "label": "Mumbai"},
    }
    osrm_results = [
        {"distance_km": 83, "duration_mins": 90, "travel_time": "1h 30min"},
        {"distance_km": 1200, "duration_mins": 800, "travel_time": "13h 20min"},
    ]

    with patch("app.services.stage_machine.resolve_origin_coords", new=AsyncMock(return_value={"lat": 19.076, "lng": 72.877, "name": "Mumbai"})), \
         patch("app.services.stage_machine.geocode", new=AsyncMock(return_value={"lat": 18.75, "lng": 73.41})), \
         patch("app.services.stage_machine.batch_driving_times", new=AsyncMock(return_value=osrm_results)), \
         patch("app.services.stage_machine._generate_destination_hooks", new=AsyncMock(return_value=["Great trek"])), \
         patch("app.services.stage_machine.fetch_place_photos", new=AsyncMock(return_value=[])):
        cards = await stage_machine.fetch_destination_suggestions(state)

    assert len(cards) == 1
    assert cards[0]["name"] == "Lonavala"


@pytest.mark.asyncio
async def test_fetch_destinations_returns_empty_when_no_candidates():
    from app.services.stage_machine import fetch_destination_suggestions
    state = {"experience_types": [], "destination_candidates": {}}
    cards = await fetch_destination_suggestions(state)
    assert cards == []


@pytest.mark.asyncio
async def test_fetch_destinations_card_has_required_fields():
    from app.services import stage_machine

    state = {
        "experience_types": ["beach_coast"],
        "destination_candidates": {"beach_coast": ["Alibaug"]},
        "trip_who": "couple",
        "trip_season": "winter",
        "current_location": {"lat": 19.076, "lng": 72.877, "label": "Mumbai"},
    }

    with patch("app.services.stage_machine.resolve_origin_coords", new=AsyncMock(return_value={"lat": 19.076, "lng": 72.877, "name": "Mumbai"})), \
         patch("app.services.stage_machine.geocode", new=AsyncMock(return_value={"lat": 18.64, "lng": 72.87})), \
         patch("app.services.stage_machine.batch_driving_times", new=AsyncMock(return_value=[{"distance_km": 95, "duration_mins": 120, "travel_time": "2h"}])), \
         patch("app.services.stage_machine._generate_destination_hooks", new=AsyncMock(return_value=["Perfect winter beach"])), \
         patch("app.services.stage_machine.fetch_place_photos", new=AsyncMock(return_value=[{"name": "Alibaug", "url": "http://img.jpg"}])):
        cards = await stage_machine.fetch_destination_suggestions(state)

    assert len(cards) == 1
    card = cards[0]
    assert card["name"] == "Alibaug"
    assert card["experience_type"] == "beach_coast"
    assert card["distance_km"] == 95
    assert card["travel_time"] == "2h"
    assert card["hook"] == "Perfect winter beach"
    assert card["photo_url"] == "http://img.jpg"
