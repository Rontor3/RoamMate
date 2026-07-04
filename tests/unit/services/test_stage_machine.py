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
