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
