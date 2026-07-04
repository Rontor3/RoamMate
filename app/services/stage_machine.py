"""
app/services/stage_machine.py — Adaptive conversation stage resolver.

resolve_stage: reads GraphState, returns current stage string.
determine_action: takes stage, returns (action, payload) for the frontend.

Both are imported by responder.py and intent.py. Nothing else should
define conversation stage logic.
"""
from typing import Any


# ── Stage resolution ───────────────────────────────────────────────────────────

def resolve_stage(state: dict) -> str:
    """
    Read current state and return the conversation stage.
    Does not care about the path — only what context currently exists.
    Priority: route_arc > pace > activities > places > vibes > destination > experience > unknown
    """
    if not state.get("destination"):
        if state.get("experience_types"):
            return "experience_type_known"
        return "experience_type_unknown"

    # Destination is known from here
    if state.get("route_arc"):
        return "route_arc_selected"
    if state.get("selected_pace"):
        return "pace_selected"
    if state.get("selected_activities"):
        return "activities_selected"
    if state.get("places_shown"):
        if not state.get("trip_duration"):
            return "duration_pending"
        return "places_shown"
    if state.get("vibes_confirmed"):
        return "vibe_selected"

    return "destination_known"


# ── Action determination ───────────────────────────────────────────────────────

async def determine_action(stage: str, state: dict) -> tuple[str | None, dict | None]:
    """
    Given a stage, return (action, payload) to send to the frontend.
    Helper functions are stubs — filled in Sprint 2+.
    """
    if stage == "experience_type_unknown":
        chips = await build_experience_chips(state)
        return "show_experience_chips", {"chips": chips}

    if stage == "experience_type_known":
        destinations = await fetch_destination_suggestions(state)
        return "show_destination_chips", {"destinations": destinations}

    if stage == "destination_known":
        vibes = await fetch_vibe_cards(state)
        return "show_vibe_cards", {"vibes": vibes}

    if stage == "vibe_selected":
        places = _build_place_cards(state)
        return "show_place_cards", {"places": places}

    if stage == "duration_pending":
        return "ask_trip_duration", {}

    if stage == "places_shown":
        activities = await build_activity_options(state)
        return "show_activity_options", {"activities": activities}

    if stage == "activities_selected":
        return "show_pace_options", {}

    if stage == "pace_selected":
        arcs = await build_route_arcs(state)
        return "show_route_arcs", {"arcs": arcs}

    if stage == "route_arc_selected":
        plan = await build_day_plan(state)
        brief = await build_destination_brief(state)
        return "open_day_planner", {"plan": plan, "brief": brief}

    return None, None


# ── Inline helpers (no external calls) ────────────────────────────────────────

_VIBE_COLOR = {
    "adventure": "adv", "cultural": "spt",
    "chill": "loc", "romantic": "loc",
    "party": "adv", "family": "spt",
}

_FACTOR_PHRASES = {
    "quality": "known for excellent quality and reviews",
    "intent_match": "matches your vibe perfectly",
    "authenticity": "a local favourite, not a tourist trap",
    "crowd_fit": "has the kind of crowd you prefer",
}


def _build_place_cards(state: dict) -> list[dict]:
    """Build place card payload from ranked_places already in state."""
    ranked = state.get("ranked_places") or []
    intent = state.get("travel_intent")
    vibe_id = "adv"
    if intent and getattr(intent, "vibe", None):
        vibe_id = _VIBE_COLOR.get(intent.vibe[0].value, "adv")

    places = []
    for p in ranked[:6]:
        expl = p.get("explanation", {})
        factor = expl.get("top_factor", "")
        places.append({
            "id": p.get("place_id", p.get("name", "")),
            "name": p.get("name", ""),
            "area": p.get("area", ""),
            "hook": p.get("hook") or _FACTOR_PHRASES.get(factor, "A great option"),
            "vibe_id": vibe_id,
            "rating": p.get("rating"),
        })
    return places


# ── Sprint 2+ stubs — return valid empty data so the system keeps running ──────

async def build_experience_chips(state: dict) -> list[dict]:
    """Sprint 2: geo-filter base categories + Tavily live_hook fetch."""
    return [
        {"id": "beach_coast",     "label": "Beach & Coast",    "description": "Sea, sun, slow days, coastal towns"},
        {"id": "hills_nature",    "label": "Hills & Nature",   "description": "Altitude, trails, forests, quiet"},
        {"id": "small_town",      "label": "Small Town",       "description": "Local life, heritage, no tourist strip"},
        {"id": "festival_events", "label": "Festival & Events","description": "Something happening, cultural moment"},
        {"id": "new_city",        "label": "New City",         "description": "Explore an unfamiliar urban place"},
        {"id": "retreat_rest",    "label": "Retreat & Rest",   "description": "Absolute stillness, wellness, nothing planned"},
    ]


async def fetch_destination_suggestions(state: dict) -> list[dict]:
    """Sprint 2: Tavily + Reddit fetch using origin + experience_types + season + who."""
    return []


async def fetch_vibe_cards(state: dict) -> list[dict]:
    """Sprint 3: destination-specific vibe descriptions from blog signals."""
    return []


async def build_activity_options(state: dict) -> list[dict]:
    """Sprint 4: live activity suggestions per selected place."""
    return []


async def build_route_arcs(state: dict) -> list[dict]:
    """Sprint 6: geographic journey arc generation."""
    return []


async def build_day_plan(state: dict) -> list[dict]:
    """Sprint 6: day-by-day plan generation from route arc + activities + pace."""
    return []


async def build_destination_brief(state: dict) -> dict:
    """Sprint 6: weather + events + permits + local language tips."""
    return {}
