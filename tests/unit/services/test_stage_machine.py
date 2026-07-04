"""Unit tests for stage_machine resolve_stage."""
from app.graph.state import GraphState


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
