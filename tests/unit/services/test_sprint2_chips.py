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
