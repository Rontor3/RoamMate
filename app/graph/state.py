"""
app/graph/state.py — GraphState TypedDict for RoamMate LangGraph workflow.

messages uses add_messages reducer so LangGraph merges per-turn additions
into the persisted checkpoint automatically (enables multi-turn conversations).
"""
import operator
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langgraph.graph.message import add_messages


class Phase(str, Enum):
    DISCOVERY = "discovery"
    PLANNING = "planning"
    IN_DESTINATION = "in_destination"


class GraphState(TypedDict, total=False):
    # Core identity
    thread_id: str

    # Messages with add_messages reducer — LangGraph accumulates these across turns
    messages: Annotated[List[Dict[str, Any]], add_messages]

    # Intent
    travel_intent: Any  # TravelIntent dataclass
    phase: Phase

    # Destination
    destination: str
    resolved_area: Any  # ResolvedArea dataclass

    # GPS / location
    current_location: Optional[Dict[str, Any]]  # {lat, lng, accuracy, label, source}

    # Phase routing flags
    needs_quick_setup: bool
    quick_setup_done: bool
    needs_vibe_clarification: bool
    is_generic_request: bool
    missing_location: bool
    missing_info: bool
    clarifying_question: str

    # Tool/API usage tracking — reset each turn, attached to conversation JSON
    tool_events: List[str]

    # Raw signal data
    reddit_signals: Dict[str, Any]
    blog_signals: Dict[str, Any]
    weather_data: Dict[str, Any]
    hotel_data: List[Dict[str, Any]]
    flight_data: List[Dict[str, Any]]

    # Processed results
    ranked_places: List[Dict[str, Any]]
    nearby_results: List[Dict[str, Any]]
    place_scores: Dict[str, Any]
    area_scores: Any  # AreaScores dataclass

    # Final response
    response: str

    # ── Card system state ──────────────────────────────────────────────────────
    conversation_stage: str          # see resolve_stage() for values
    card_action: Optional[str]       # incoming from frontend: card interaction type
    card_data: Optional[Dict[str, Any]]  # incoming from frontend: card interaction data
    action: Optional[str]            # outgoing to frontend: what UI to render
    payload: Optional[Dict[str, Any]]    # outgoing to frontend: data for that UI
    vibes_confirmed: bool            # True once user has selected vibe cards
    selected_vibe_ids: List[str]     # e.g. ["adv", "hid"]
    places_shown: bool               # True once place cards have been sent
    selected_place_ids: List[str]    # place ids the user locked in
    pace_shown: bool                 # True once pace cards have been sent
    selected_pace: Optional[str]     # "slow" | "mix" | "power"
    routes_shown: bool               # True once route cards have been sent
    routes: List[Dict[str, Any]]     # route data for route cards
    show_scene_strip: bool           # flag to inject a scene strip next response
    scene_strip_label: Optional[str] # label text for the scene strip

    # ── Phase 0 context — sent as structured fields from frontend ─────────────
    trip_mode: str                    # "plan" | "now"
    trip_who: str                     # "solo" | "couple" | "friends" | "family_kids" | "family_elder"
    trip_season: str                  # "summer" | "monsoon" | "winter" | "flex"

    # ── Experience type — multi-select, dynamic chips ─────────────────────────
    experience_types: List[str]       # e.g. ["hills_nature", "festival_events"]

    # ── Graph short-circuit flag ──────────────────────────────────────────────
    skip_graph: bool                  # True → card action turn, go direct to responder

    # ── Trip planning progression ─────────────────────────────────────────────
    trip_duration: int                # number of days
    selected_activities: List[str]    # activities user confirmed at place level
    route_arc: Dict[str, Any]         # chosen geographic journey direction
    day_plan: List[Dict[str, Any]]    # generated day-by-day outline
    destination_brief: Dict[str, Any] # weather, alerts, events, permits, language tips

    # ── Context buckets — populated in later sprints ──────────────────────────
    card_context_by_vibe: Dict[str, Any]  # { "adv": { "text": "...", "tags": [...] } }
    free_text_context: Dict[str, Any]     # constraints from free text across all turns
    in_destination_saves: List[str]       # place ids saved from in-destination tab


def resolve_stage(state: "GraphState") -> str:
    """Stub: will be replaced by stage_machine.resolve_stage in Task 3.

    Temporary implementation to avoid breaking existing imports.
    Returns 'destination_unknown' as default.
    """
    return "destination_unknown"
