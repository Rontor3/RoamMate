"""Sprint 6 — day planner tests."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.graph.state import GraphState


# ── Task 1: selected_places state field ──────────────────────────────────────

def test_graphstate_has_selected_places():
    state: GraphState = {}
    state["selected_places"] = ["chapora_fort", "baga_beach"]
    assert state["selected_places"] == ["chapora_fort", "baga_beach"]


def test_graphstate_selected_places_defaults_to_none():
    state: GraphState = {}
    assert state.get("selected_places") is None


# ── Task 1: activities_confirmed saves selected_places ───────────────────────

@pytest.mark.asyncio
async def test_activities_confirmed_saves_selected_places():
    from app.graph.nodes.intent import detect_intent
    state: GraphState = {
        "card_action": "activities_confirmed",
        "card_data": {},
        "pending_activities": {
            "chapora_fort": ["Sunrise Trek"],
            "baga_beach": ["Beach Volleyball"],
        },
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.intent.resolve_stage", return_value="activities_selected"):
        mock_action.return_value = ("show_pace_options", {})
        result = await detect_intent(state)
    assert set(result["selected_places"]) == {"chapora_fort", "baga_beach"}
    assert result["pending_activities"] == {}
    assert set(result["selected_activities"]) == {"Sunrise Trek", "Beach Volleyball"}


# ── Task 1: trip_duration_set handler ────────────────────────────────────────

@pytest.mark.asyncio
async def test_trip_duration_set_handler():
    from app.graph.nodes.intent import detect_intent
    state: GraphState = {
        "card_action": "trip_duration_set",
        "card_data": {"days": 3},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.intent.resolve_stage", return_value="places_shown"):
        mock_action.return_value = ("show_activity_options", {"activities": []})
        result = await detect_intent(state)
    assert result["trip_duration"] == 3
    assert result["skip_graph"] is True


@pytest.mark.asyncio
async def test_trip_duration_set_defaults_to_3_when_missing():
    from app.graph.nodes.intent import detect_intent
    state: GraphState = {
        "card_action": "trip_duration_set",
        "card_data": {},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.intent.resolve_stage", return_value="places_shown"):
        mock_action.return_value = ("show_activity_options", {"activities": []})
        result = await detect_intent(state)
    assert result["trip_duration"] == 3


# ── Task 2: generate_route_arcs ───────────────────────────────────────────────

def _make_session_mock(content: str):
    """Build aiohttp.ClientSession mock returning fixed JSON content."""
    def fake_post(*args, **kwargs):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.json = AsyncMock(return_value={"choices": [{"message": {"content": content}}]})
        return resp
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(side_effect=fake_post)
    return MagicMock(return_value=session)


_BASE_STATE = {
    "destination": "Goa",
    "selected_area": "north_goa",
    "selected_places": ["chapora_fort"],
    "place_cards": [{"category": "Forts", "places": [{"id": "chapora_fort", "name": "Chapora Fort"}]}],
    "experience_types": ["beach_coast"],
    "trip_who": "solo",
    "trip_duration": 3,
}


@pytest.mark.asyncio
async def test_generate_route_arcs_returns_groq_arcs():
    from app.services.day_planner import generate_route_arcs
    groq_arcs = [{"id": "north_to_south", "label": "North → South", "description": "Classic flow", "place_order": ["Chapora Fort"]}]
    with patch("app.services.day_planner.aiohttp.ClientSession", _make_session_mock(json.dumps(groq_arcs))):
        result = await generate_route_arcs(_BASE_STATE)
    assert isinstance(result, list) and len(result) >= 1
    assert result[0]["id"] == "north_to_south"
    assert "place_order" in result[0]


@pytest.mark.asyncio
async def test_generate_route_arcs_fallback_on_groq_failure():
    from app.services.day_planner import generate_route_arcs
    bad_session = MagicMock()
    bad_session.__aenter__ = AsyncMock(side_effect=Exception("Groq down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=bad_session)):
        result = await generate_route_arcs(_BASE_STATE)
    assert len(result) == 2
    assert result[0]["id"] == "selection_order"
    assert result[1]["id"] == "reverse_order"


@pytest.mark.asyncio
async def test_generate_route_arcs_filters_by_selected_places():
    """Only place names matching selected_places IDs are passed to Groq."""
    from app.services.day_planner import generate_route_arcs
    captured = []

    def fake_post(url, headers=None, json=None, **kwargs):
        captured.append(json["messages"][0]["content"])
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.json = AsyncMock(return_value={"choices": [{"message": {"content": "[]"}}]})
        return resp

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(side_effect=fake_post)

    state = {
        **_BASE_STATE,
        "selected_places": ["chapora_fort"],
        "place_cards": [{"category": "All", "places": [
            {"id": "chapora_fort", "name": "Chapora Fort"},
            {"id": "baga_beach", "name": "Baga Beach"},   # NOT selected
        ]}],
    }
    with patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=session)):
        await generate_route_arcs(state)

    assert captured, "Groq was never called"
    assert "Chapora Fort" in captured[0]
    assert "Baga Beach" not in captured[0]


@pytest.mark.asyncio
async def test_generate_route_arcs_fallback_uses_all_place_cards_when_selected_places_empty():
    from app.services.day_planner import generate_route_arcs
    state = {
        **_BASE_STATE,
        "selected_places": [],  # empty — fall back to all place_cards
        "place_cards": [{"category": "All", "places": [
            {"id": "chapora_fort", "name": "Chapora Fort"},
            {"id": "baga_beach", "name": "Baga Beach"},
        ]}],
    }
    bad_session = MagicMock()
    bad_session.__aenter__ = AsyncMock(side_effect=Exception("Groq down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=bad_session)):
        result = await generate_route_arcs(state)
    assert result[0]["place_order"] == ["Chapora Fort", "Baga Beach"]
    assert result[1]["place_order"] == ["Baga Beach", "Chapora Fort"]


# ── Task 3: generate_day_plan ─────────────────────────────────────────────────

_PLAN_STATE = {
    "destination": "Goa",
    "route_arc": {"place_order": ["Chapora Fort"]},
    "selected_activities": ["Sunrise Trek", "Sunset Picnic"],
    "selected_pace": "mix",
    "trip_duration": 3,
    "place_cards": [],
    "travel_intent": None,
}

_GROQ_PLAN = json.dumps([
    {"day": 1, "title": "Fort Day", "activities": [{"time": "7:00 AM", "activity": "Sunrise Trek", "place": "Chapora Fort", "duration": "2h"}], "note": "Start early."},
    {"day": 2, "title": "Chill Day", "activities": [{"time": "5:00 PM", "activity": "Sunset Picnic", "place": "Chapora Fort", "duration": "1h"}], "note": "Easy day."},
    {"day": 3, "title": "Wrap Up", "activities": [], "note": "Check out."},
])


@pytest.mark.asyncio
async def test_generate_day_plan_returns_groq_plan():
    from app.services.day_planner import generate_day_plan
    with patch("app.services.day_planner.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.day_planner.aiohttp.ClientSession", _make_session_mock(_GROQ_PLAN)):
        result = await generate_day_plan(_PLAN_STATE)
    assert isinstance(result, list) and len(result) > 0
    assert result[0]["day"] == 1
    assert "activities" in result[0]
    assert "note" in result[0]


@pytest.mark.asyncio
async def test_generate_day_plan_fallback_distributes_evenly():
    from app.services.day_planner import generate_day_plan
    state = {**_PLAN_STATE, "selected_activities": ["A", "B", "C"], "trip_duration": 3}
    bad_session = MagicMock()
    bad_session.__aenter__ = AsyncMock(side_effect=Exception("Groq down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.day_planner.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=bad_session)):
        result = await generate_day_plan(state)
    assert len(result) == 3
    assert all("day" in d and "activities" in d for d in result)


@pytest.mark.asyncio
async def test_generate_day_plan_uses_cached_activity_objects():
    """Redis-cached full activity objects (with duration/time/vibe) are sent to Groq."""
    from app.services.day_planner import generate_day_plan
    cached_activities = [{"id": "sunrise_trek", "label": "Sunrise Trek", "duration": "2h", "time": "morning", "vibe": "adventure"}]
    state = {
        **_PLAN_STATE,
        "place_cards": [{"category": "Forts", "places": [{"id": "chapora_fort"}]}],
    }
    captured = []

    def fake_post(url, headers=None, json=None, **kwargs):
        captured.append(json["messages"][0]["content"])
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.json = AsyncMock(return_value={"choices": [{"message": {"content": _GROQ_PLAN}}]})
        return resp

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(side_effect=fake_post)

    with patch("app.services.day_planner.get_cached", new_callable=AsyncMock, return_value=cached_activities), \
         patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=session)):
        await generate_day_plan(state)

    assert captured, "Groq was never called"
    assert "morning" in captured[0]  # duration/time from cached objects reached the prompt


@pytest.mark.asyncio
async def test_generate_day_plan_trip_duration_zero_defaults_to_one():
    from app.services.day_planner import generate_day_plan
    state = {**_PLAN_STATE, "trip_duration": 0, "selected_activities": ["A"]}
    bad_session = MagicMock()
    bad_session.__aenter__ = AsyncMock(side_effect=Exception("Groq down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.day_planner.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=bad_session)):
        result = await generate_day_plan(state)
    assert len(result) == 1  # trip_duration defaults to 1
    assert result[0]["day"] == 1
