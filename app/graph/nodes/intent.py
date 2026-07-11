"""
nodes/intent.py — Node 1: detect_intent
Calls IntentExtractor, sets Phase enum, manages routing conditional edges.
Phase and proximity detection are fully LLM-driven — no keyword lists.
"""
from typing import Literal

from app.graph.state import GraphState, Phase
from app.services.stage_machine import resolve_stage, determine_action as _stage_determine_action
from app.models import Vibe
from app.services.intent_extractor import IntentExtractor
from app.utils.logger import get_logger

logger = get_logger(__name__)
_intent_extractor = IntentExtractor()

_PHASE_MAP = {
    "discovery": Phase.DISCOVERY,
    "planning": Phase.PLANNING,
    "in_destination": Phase.IN_DESTINATION,
}


async def detect_intent(state: GraphState) -> GraphState:
    """Extract TravelIntent from latest user message, set phase and routing flags."""
    messages = state.get("messages", [])

    # ── Card action handling — short-circuit LLM extraction ──────────────────
    card_action = state.get("card_action")
    card_data = state.get("card_data") or {}

    if card_action == "vibes_selected":
        vibe_ids = card_data.get("vibe_ids", [])
        state["vibes_confirmed"] = True
        state["selected_vibe_ids"] = vibe_ids
        VIBE_MAP = {
            "adv": "adventure", "loc": "cultural",
            "spt": "cultural",  "hid": "adventure",
        }
        intent = state.get("travel_intent")
        if intent:
            try:
                intent.vibe = list({Vibe(VIBE_MAP.get(v, "adventure")) for v in vibe_ids})
                state["travel_intent"] = intent
            except Exception:
                pass
        state["show_scene_strip"] = True
        state["scene_strip_label"] = "Finding your places"
        state["card_action"] = None
        state["skip_graph"] = False   # planning node must run to fetch ranked_places
        state["conversation_stage"] = resolve_stage(state)
        return state

    elif card_action == "experience_type_selected":
        state["experience_types"] = card_data.get("types", [])
        state["card_action"] = None
        state["skip_graph"] = False   # discovery node fetches destination suggestions
        state["conversation_stage"] = resolve_stage(state)
        return state

    elif card_action == "destination_selected":
        state["destination"] = card_data.get("destination", "")
        state["card_action"] = None
        state["skip_graph"] = False   # planning node fetches vibe cards
        state["conversation_stage"] = resolve_stage(state)
        return state

    elif card_action == "places_selected":
        state["selected_place_ids"] = card_data.get("place_ids", [])
        state["card_action"] = None
        state["skip_graph"] = True    # no data fetch needed
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state

    elif card_action == "pace_selected":
        state["selected_pace"] = card_data.get("pace")
        state["card_action"] = None
        state["skip_graph"] = True    # no data fetch needed
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state

    elif card_action == "route_arc_selected":
        state["route_arc"] = card_data.get("arc", {})
        state["card_action"] = None
        state["skip_graph"] = True    # no data fetch needed
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state

    elif card_action == "area_selected":
        state["selected_area"] = card_data.get("area_id", "")
        state["card_action"] = None
        state["skip_graph"] = True    # no data fetch needed
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state

    elif card_action == "place_selected":
        state["selected_place"] = card_data.get("place_id", "")
        state["card_action"] = None
        state["skip_graph"] = True
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state

    elif card_action == "route_selected":
        state["selected_route_id"] = card_data.get("route_id")
        state["card_action"] = None
        state["skip_graph"] = True
        state["conversation_stage"] = resolve_stage(state)
        return state

    if not messages:
        return state

    # Pass up to last 5 messages so the LLM has conversation context
    recent_msgs = messages[-5:]
    recent_dicts = [
        {"role": m.get("role", "user") if isinstance(m, dict) else getattr(m, "type", "user"),
         "content": m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")}
        for m in recent_msgs
    ]

    logger.info(f"detect_intent: processing {len(recent_dicts)} messages")

    try:
        intent, phase_hint = await _intent_extractor.extract(recent_dicts)
    except Exception as e:
        logger.error(f"IntentExtractor failed: {e}")
        state["tool_events"] = state.get("tool_events") or []
        state["tool_events"].append("[Groq/intent] ✗ failed")
        state["needs_quick_setup"] = True
        return state

    # Merge with existing intent so fields don't get lost across turns
    existing = state.get("travel_intent")
    if existing:
        if intent.destination.city:
            existing.destination.city = intent.destination.city
        if intent.destination.country:
            existing.destination.country = intent.destination.country
        if intent.destination.region:
            existing.destination.region = intent.destination.region
        if intent.origin_city:
            existing.origin_city = intent.origin_city
        if intent.vibe:
            existing.vibe = list(set(existing.vibe + intent.vibe))
        if intent.crowd_preference:
            existing.crowd_preference = intent.crowd_preference
        if intent.duration:
            existing.duration = intent.duration
        if intent.needs_flight is not None:
            existing.needs_flight = intent.needs_flight
        if intent.needs_hotel is not None:
            existing.needs_hotel = intent.needs_hotel
        if intent.interests:
            existing.interests = list(set(existing.interests + intent.interests))
        if intent.budget:
            existing.budget = intent.budget
        if intent.accommodation_type:
            existing.accommodation_type = intent.accommodation_type
        # Always carry the latest clarification state forward
        existing.needs_clarification = intent.needs_clarification
        existing.clarification_question = intent.clarification_question
        intent = existing

    state["travel_intent"] = intent

    # ── Phase resolution ────────────────────────────────────────────────────────
    # Use the LLM's phase_hint as the primary signal.
    # Fall back to: if prev destination known + new city → planning; else discovery.
    if phase_hint and phase_hint in _PHASE_MAP:
        phase = _PHASE_MAP[phase_hint]
    elif state.get("destination") and intent.destination.city:
        phase = Phase.PLANNING
    else:
        phase = Phase.DISCOVERY

    state["phase"] = phase

    # ── Destination tracking ────────────────────────────────────────────────────
    resolved_dest = intent.destination.city or intent.destination.region
    if resolved_dest:
        state["destination"] = resolved_dest
    elif intent.origin_city and not state.get("destination"):
        # "from X" / "near X" / "in X" — use origin as the routing anchor.
        # When needs_clarification=True (bare "trip from X"), responder generates
        # destination suggestions instead of asking a generic question.
        state["destination"] = intent.origin_city

    # ── Routing flags ───────────────────────────────────────────────────────────
    missing_dest = not bool(state.get("destination"))

    # quick_setup still set so the GPS/geocode flow runs once location is resolved
    state["needs_quick_setup"] = phase == Phase.IN_DESTINATION and missing_dest
    state["is_generic_request"] = intent.confidence.overall < 0.3

    # Clarification fires ONLY when we have no location signal at all.
    # Vibe, duration, budget are optional — the responder elicits them naturally.
    # "from X" with no destination is handled by needs_clarification on the intent object.
    no_location = missing_dest and not intent.origin_city
    needs_clarify = no_location and not state["needs_quick_setup"]
    first_missing = "destination" if needs_clarify else None

    state["missing_info"] = needs_clarify

    if state["missing_info"]:
        if intent.needs_clarification and intent.clarification_question:
            # LLM-generated question for "from X" with no destination
            state["clarifying_question"] = intent.clarification_question
        else:
            state["clarifying_question"] = await _intent_extractor.ask_conversationally(recent_dicts, intent)

    # Tool event log
    events: list = state.get("tool_events") or []
    dest_str = state.get("destination", "unknown")
    vibe_str = ",".join(v.value for v in intent.vibe) if intent.vibe else "none"
    events.append(f"[Groq/intent] dest={dest_str} origin={intent.origin_city} phase={phase} vibe={vibe_str} conf={intent.confidence.overall:.2f}")
    state["tool_events"] = events

    state["conversation_stage"] = resolve_stage(state)
    logger.info(f"detect_intent → phase={phase} dest={state.get('destination')} origin={intent.origin_city} missing={first_missing or False} stage={state['conversation_stage']}")
    return state


# ─── Conditional edge functions ───────────────────────────────────────────────

def should_clarify(state: GraphState) -> Literal["clarify", "route_phase", "skip_to_responder"]:
    if state.get("skip_graph"):
        return "skip_to_responder"
    if state.get("missing_info") and not state.get("needs_quick_setup"):
        return "clarify"
    return "route_phase"


def route_to_phase(state: GraphState) -> Literal["discovery", "planning", "in_destination"]:
    phase = state.get("phase", Phase.DISCOVERY)
    if phase == Phase.IN_DESTINATION:
        return "in_destination"
    elif phase == Phase.PLANNING:
        return "planning"
    return "discovery"


async def clarify(state: GraphState) -> dict:
    question = state.get("clarifying_question", "Sounds like a fun trip! Where are you thinking of heading?")
    return {
        "messages": [{"role": "assistant", "content": question}],
        "response": question
    }
