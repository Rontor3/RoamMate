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
