"""
nodes/intent.py — Node 1: detect_intent
Calls IntentExtractor, sets Phase enum, manages routing conditional edges.
"""
import asyncio
from typing import Literal

from app.graph.state import GraphState, Phase
from app.services.intent_extractor import IntentExtractor
from app.utils.logger import get_logger
from app.utils.message_utils import last_user_content, messages_to_dicts

logger = get_logger(__name__)
_intent_extractor = IntentExtractor()


async def detect_intent(state: GraphState) -> GraphState:
    """Extract TravelIntent from latest user message, set phase and routing flags."""
    messages = state.get("messages", [])
    if not messages:
        return state

    # Pass up to last 5 messages as structured dicts to the IntentExtractor
    # so it remembers previous answers and understands follow-up context.
    recent_msgs = messages[-5:]
    # Normalize to plain dicts so the extractor can serialize roles cleanly
    recent_dicts = [
        {"role": m.get("role", "user") if isinstance(m, dict) else getattr(m, "type", "user"),
         "content": m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")}
        for m in recent_msgs
    ]
    
    logger.info(f"detect_intent: processing context length {len(recent_dicts)}")

    try:
        intent = await _intent_extractor.extract(recent_dicts)
    except Exception as e:
        logger.error(f"IntentExtractor failed: {e}")
        state["tool_events"] = state.get("tool_events") or []
        state["tool_events"].append("[Groq/intent] ✗ failed")
        state["needs_quick_setup"] = True
        return state

    # Intelligently merge the newly extracted intent with any previous intent
    # so we never lose fields (like vibe, duration, budget) when old messages
    # fall out of the 5-message context window to the LLM.
    existing_intent = state.get("travel_intent")
    if existing_intent:
        if intent.destination.city:
            existing_intent.destination.city = intent.destination.city
        if intent.destination.country:
            existing_intent.destination.country = intent.destination.country
        if intent.destination.region:
            existing_intent.destination.region = intent.destination.region
        if intent.vibe:
            existing_intent.vibe = list(set(existing_intent.vibe + intent.vibe))
        if intent.crowd_preference:
            existing_intent.crowd_preference = intent.crowd_preference
        if intent.duration:
            existing_intent.duration = intent.duration
        if intent.needs_flight is not None:
            existing_intent.needs_flight = intent.needs_flight
        if intent.needs_hotel is not None:
            existing_intent.needs_hotel = intent.needs_hotel
        if intent.interests:
            existing_intent.interests = list(set(existing_intent.interests + intent.interests))
        if intent.budget:
            existing_intent.budget = intent.budget
            
        intent = existing_intent
    
    state["travel_intent"] = intent

    # Record intent extraction tool event
    events: list = state.get("tool_events") or []
    dest_str = (intent.destination.city or intent.destination.region or intent.destination.country or "unknown")
    vibe_str = ",".join(v.value for v in intent.vibe) if intent.vibe else "none"
    events.append(f"[Groq/intent] dest={dest_str} vibe={vibe_str} confidence={intent.confidence.overall:.2f}")
    state["tool_events"] = events

    # Determine conversation phase from message keywords
    latest_msg = last_user_content(messages)
    msg_lower = latest_msg.lower()
    in_dest_signals = ["i'm in", "i am in", "near me", "nearby", "around here", "i'm at", "currently in"]
    planning_signals = [
        # Explicit planning
        "plan my trip", "plan my", "plan the trip", "plan a trip",
        "end to end", "complete trip", "full trip", "full plan",
        # Itinerary requests
        "itinerary", "day wise", "day by day", "day-by-day", "day-wise",
        "week plan", "week itinerary", "schedule", "agenda",
        "curated list", "curated plan",
        # Logistics
        "book", "hotel", "flight", "where should i stay", "accommodation",
        "how do i get", "transport", "how to reach",
        # Detailed exploration
        "cover each", "cover all", "cover as much", "explore each",
        "detailed plan", "give me a plan", "make a plan",
    ]

    if any(sig in msg_lower for sig in in_dest_signals):
        state["phase"] = Phase.IN_DESTINATION
    elif any(sig in msg_lower for sig in planning_signals):
        state["phase"] = Phase.PLANNING
    else:
        # Default to discovery, promote to planning if destination is already known
        prev_dest = state.get("destination")
        if prev_dest and intent.destination.city:
            state["phase"] = Phase.PLANNING
        else:
            state["phase"] = Phase.DISCOVERY

    # Destination tracking: prefer city, fall back to region
    resolved_dest = intent.destination.city or intent.destination.region
    if resolved_dest:
        state["destination"] = resolved_dest

    # Flag if destination missing — a known region is a valid destination
    missing_dest = not bool(state.get("destination"))

    if state.get("phase") == Phase.IN_DESTINATION and missing_dest:
        state["needs_quick_setup"] = True
    else:
        state["needs_quick_setup"] = False

    # Check for generic "surprise me" style requests
    generic_signals = ["surprise me", "anything", "whatever", "you choose", "don't know"]
    state["is_generic_request"] = any(sig in msg_lower for sig in generic_signals)

    # Missing info flag (for clarification edge)
    state["missing_info"] = missing_dest and not state.get("needs_quick_setup")

    if state["missing_info"]:
        # Use the LLM to generate a warm, conversational question instead of a static fallback
        conversational_q = await _intent_extractor.ask_conversationally(recent_dicts)
        state["clarifying_question"] = conversational_q

    logger.info(f"detect_intent → phase={state.get('phase')}, dest={state.get('destination')}, quick_setup={state.get('needs_quick_setup')}")
    return state


# ─── Conditional edge functions ───────────────────────────────────────────────

def should_clarify(state: GraphState) -> Literal["clarify", "route_phase"]:
    """Return 'clarify' if destination is completely unknown, else proceed."""
    if state.get("missing_info") and not state.get("needs_quick_setup"):
        return "clarify"
    return "route_phase"


def route_to_phase(state: GraphState) -> Literal["discovery", "planning", "in_destination"]:
    """Route to the correct phase node after intent is resolved."""
    phase = state.get("phase", Phase.DISCOVERY)
    if phase == Phase.IN_DESTINATION:
        return "in_destination"
    elif phase == Phase.PLANNING:
        return "planning"
    return "discovery"


async def clarify(state: GraphState) -> dict:
    """Return a conversational clarifying question to append to messages and stop the turn."""
    question = state.get("clarifying_question", "Sounds like a fun trip! Where are you thinking of heading?")
    return {
        "messages": [{"role": "assistant", "content": question}],
        "response": question
    }
