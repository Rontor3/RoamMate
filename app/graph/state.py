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
