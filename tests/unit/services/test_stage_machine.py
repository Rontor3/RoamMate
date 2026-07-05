"""Unit tests for stage_machine resolve_stage and determine_action."""
import pytest
from app.graph.state import GraphState
from app.services.stage_machine import resolve_stage, determine_action


def test_graphstate_has_trip_mode():
    state: GraphState = {}
    state["trip_mode"] = "now"
    assert state["trip_mode"] == "now"


def test_graphstate_has_experience_types():
    state: GraphState = {}
    state["experience_types"] = ["hills_nature"]
    assert state["experience_types"] == ["hills_nature"]


def test_graphstate_has_skip_graph():
    state: GraphState = {}
    state["skip_graph"] = True
    assert state["skip_graph"] is True


def test_chat_request_accepts_phase0_fields():
    from app.api.schemas import ChatRequest
    req = ChatRequest(
        message="Going soon, solo",
        thread_id="t1",
        trip_mode="now",
        trip_who="solo",
        trip_season="winter",
    )
    assert req.trip_mode == "now"
    assert req.trip_who == "solo"
    assert req.trip_season == "winter"


def test_chat_request_phase0_fields_optional():
    from app.api.schemas import ChatRequest
    req = ChatRequest(message="hello", thread_id="t1")
    assert req.trip_mode is None
    assert req.trip_who is None
    assert req.trip_season is None


# ── resolve_stage tests ────────────────────────────────────────────────────────

def test_resolve_stage_no_context_returns_experience_type_unknown():
    assert resolve_stage({}) == "experience_type_unknown"


def test_resolve_stage_experience_types_set_returns_known():
    state = {"experience_types": ["hills_nature"]}
    assert resolve_stage(state) == "experience_type_known"


def test_resolve_stage_destination_known_skips_experience():
    state = {"destination": "Goa"}
    assert resolve_stage(state) == "destination_known"


def test_resolve_stage_destination_and_vibes_confirmed():
    state = {"destination": "Goa", "vibes_confirmed": True}
    assert resolve_stage(state) == "vibe_selected"


def test_resolve_stage_places_shown_no_duration():
    state = {"destination": "Goa", "vibes_confirmed": True, "places_shown": True}
    assert resolve_stage(state) == "duration_pending"


def test_resolve_stage_places_shown_with_duration():
    state = {
        "destination": "Goa",
        "vibes_confirmed": True,
        "places_shown": True,
        "trip_duration": 3,
    }
    assert resolve_stage(state) == "places_shown"


def test_resolve_stage_activities_selected():
    state = {
        "destination": "Goa",
        "vibes_confirmed": True,
        "places_shown": True,
        "trip_duration": 3,
        "selected_activities": ["beach", "nightlife"],
    }
    assert resolve_stage(state) == "activities_selected"


def test_resolve_stage_pace_selected():
    state = {
        "destination": "Goa",
        "vibes_confirmed": True,
        "places_shown": True,
        "trip_duration": 3,
        "selected_activities": ["beach"],
        "selected_pace": "mix",
    }
    assert resolve_stage(state) == "pace_selected"


def test_resolve_stage_route_arc_selected():
    state = {
        "destination": "Goa",
        "route_arc": {"direction": "south_to_north"},
    }
    assert resolve_stage(state) == "route_arc_selected"


def test_resolve_stage_destination_known_beats_experience_type():
    # destination takes priority over experience_type_known
    state = {"destination": "Coorg", "experience_types": ["hills_nature"]}
    assert resolve_stage(state) == "destination_known"


# ── determine_action tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_determine_action_experience_type_unknown_returns_chips():
    action, payload = await determine_action("experience_type_unknown", {})
    assert action == "show_experience_chips"
    assert "chips" in payload
    assert isinstance(payload["chips"], list)
    assert len(payload["chips"]) > 0


@pytest.mark.asyncio
async def test_determine_action_destination_known_returns_vibe_cards():
    action, payload = await determine_action("destination_known", {"destination": "Goa"})
    assert action == "show_vibe_cards"
    assert "vibes" in payload


@pytest.mark.asyncio
async def test_determine_action_duration_pending_returns_ask():
    action, payload = await determine_action("duration_pending", {})
    assert action == "ask_trip_duration"
    assert payload == {}


@pytest.mark.asyncio
async def test_determine_action_unknown_stage_returns_none():
    action, payload = await determine_action("nonexistent_stage", {})
    assert action is None
    assert payload is None


@pytest.mark.asyncio
async def test_determine_action_vibe_selected_returns_place_cards():
    from app.services.stage_machine import determine_action
    state = {
        "ranked_places": [
            {"name": "Palolem Beach", "rating": 4.5, "place_id": "p1",
             "explanation": {"top_factor": "authenticity"}}
        ]
    }
    action, payload = await determine_action("vibe_selected", state)
    assert action == "show_place_cards"
    assert payload["places"][0]["name"] == "Palolem Beach"


def test_should_clarify_returns_skip_when_skip_graph_set():
    from app.graph.nodes.intent import should_clarify
    state = {"skip_graph": True}
    assert should_clarify(state) == "skip_to_responder"


def test_should_clarify_returns_route_phase_normally():
    from app.graph.nodes.intent import should_clarify
    state = {"skip_graph": False, "missing_info": False}
    assert should_clarify(state) == "route_phase"
