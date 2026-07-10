"""
app/services/stage_machine.py — Adaptive conversation stage resolver.

resolve_stage: reads GraphState, returns current stage string.
determine_action: takes stage, returns (action, payload) for the frontend.

Both are imported by responder.py and intent.py. Nothing else should
define conversation stage logic.
"""
import asyncio
import json
import os
import aiohttp

from app.services.tavily_client import tavily_search
from app.services.geo_utils import get_origin, resolve_origin_coords, geocode, batch_driving_times
from app.utils.place_photos import fetch_place_photos
from app.utils.logger import get_logger

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

_CATEGORY_DESCRIPTIONS = {
    "beach_coast":     "beaches, coastal towns, sea, islands, water sports",
    "hills_nature":    "hill stations, mountains, forests, trekking, altitude, valleys",
    "small_town":      "heritage towns, rural areas, off-beat villages, quaint places",
    "festival_events": "music concerts, cultural festivals, nightlife, events",
    "new_city":        "urban exploration, metro cities, modern attractions, city breaks",
    "retreat_rest":    "wellness retreats, spas, spiritual places, peaceful getaways",
}


# ── Private Groq helpers ───────────────────────────────────────────────────────

async def _groq_json(prompt: str, max_tokens: int = 500) -> dict | list | None:
    """Send a prompt to Groq expecting a JSON response. Returns parsed result or None."""
    if not GROQ_API_KEY:
        return None
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                text = result["choices"][0]["message"]["content"].strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                return json.loads(text)
    except Exception as e:
        logger.error(f"[Groq/_groq_json] failed: {e}")
        return None


async def _classify_destinations(
    tavily_results: list[dict], origin: str
) -> dict[str, list[str]]:
    """
    Groq: classify destination names from Tavily results into 6 category IDs.
    Returns {category_id: [destination_names]} — only non-empty categories.
    """
    if not tavily_results:
        return {}
    snippets = " ".join(r.get("content", "")[:300] for r in tavily_results[:8])
    cats = "\n".join(f"- {k}: {v}" for k, v in _CATEGORY_DESCRIPTIONS.items())
    prompt = (
        f"From these search results about weekend trips from {origin}:\n\n{snippets}\n\n"
        f"Extract specific destination names and classify each into one of:\n{cats}\n\n"
        'Return ONLY valid JSON (no markdown): {"beach_coast": ["Alibaug"], "hills_nature": ["Lonavala"]}\n'
        "Only include categories with at least one destination. Omit empty categories."
    )
    result = await _groq_json(prompt)
    if isinstance(result, dict):
        return {
            k: [str(v) for v in vals]
            for k, vals in result.items()
            if k in _CATEGORY_DESCRIPTIONS and isinstance(vals, list)
        }
    return {}


async def _extract_live_hooks(event_results: list[dict]) -> dict[str, str]:
    """
    Groq: extract one live event hook per chip category from events search results.
    Returns {chip_id: hook_string} — only categories with found events.
    """
    if not event_results:
        return {}
    snippets = " ".join(r.get("content", "")[:200] for r in event_results[:5])
    cats = ", ".join(_CATEGORY_DESCRIPTIONS.keys())
    prompt = (
        f"From these search results about events:\n\n{snippets}\n\n"
        f"Extract a short event hook (max 60 chars) for any of: {cats}\n\n"
        'Return ONLY valid JSON (no markdown): {"hills_nature": "Kasol Nomad Festival this weekend"}\n'
        "Only include categories where you found a clear event. Omit if none found."
    )
    result = await _groq_json(prompt)
    if isinstance(result, dict):
        return {
            k: str(v)[:70]
            for k, v in result.items()
            if k in _CATEGORY_DESCRIPTIONS
        }
    return {}


async def _generate_destination_hooks(
    destinations: list[str],
    trip_who: str | None,
    trip_season: str | None,
    experience_types: list[str],
) -> list[str]:
    """
    Groq: generate one evocative one-line hook per destination.
    Returns list in same order as input; falls back to "Explore [name]" on failure.
    """
    if not destinations:
        return []
    who = trip_who or "travellers"
    season = trip_season or "any season"
    exp = ", ".join(experience_types) if experience_types else "travel"
    prompt = (
        f"Write a short evocative travel hook for each destination (10-15 words max).\n"
        f"Context: {who}, {season} trip, interested in {exp}\n\n"
        f"Destinations: {destinations}\n\n"
        "Return ONLY a valid JSON array of strings matching the input order (no markdown):\n"
        '["Monsoon turns the valleys electric green — strawberry season peak", "Sea breeze and empty beaches"]'
    )
    result = await _groq_json(prompt, max_tokens=300)
    if isinstance(result, list) and len(result) == len(destinations):
        return [str(h) for h in result]
    return [f"Explore {d}" for d in destinations]


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

BASE_CHIPS = [
    {"id": "beach_coast",     "label": "Beach & Coast",    "description": "Sea, sun, slow days, coastal towns"},
    {"id": "hills_nature",    "label": "Hills & Nature",   "description": "Altitude, trails, forests, quiet"},
    {"id": "small_town",      "label": "Small Town",       "description": "Local life, heritage, no tourist strip"},
    {"id": "festival_events", "label": "Festival & Events","description": "Something happening, cultural moment"},
    {"id": "new_city",        "label": "New City",         "description": "Explore an unfamiliar urban place"},
    {"id": "retreat_rest",    "label": "Retreat & Rest",   "description": "Absolute stillness, wellness, nothing planned"},
]


async def build_experience_chips(state: dict) -> list[dict]:
    """Return geo-filtered experience chips with live event hooks.

    plan mode: all 6 chips returned immediately.
    now mode: Tavily pre-fetch + Groq classification filters to nearby categories.
    Falls back to all 6 if Tavily or Groq fails.
    Mutates state["destination_candidates"] as a side-effect for the next turn.
    """
    if state.get("trip_mode") not in ("now", None):
        return [dict(c) for c in BASE_CHIPS]

    origin = get_origin(state)
    origin_name = origin.get("name", "") if origin else ""
    if not origin_name:
        return [dict(c) for c in BASE_CHIPS]

    dest_results, event_results = await asyncio.gather(
        tavily_search(f"weekend getaway road trip destinations from {origin_name}", max_results=10),
        tavily_search(f"events festivals concerts near {origin_name} this month", max_results=5),
        return_exceptions=True,
    )
    if isinstance(dest_results, Exception):
        dest_results = []
    if isinstance(event_results, Exception):
        event_results = []

    classified, live_hooks = await asyncio.gather(
        _classify_destinations(dest_results, origin_name),
        _extract_live_hooks(event_results),
        return_exceptions=True,
    )
    if isinstance(classified, Exception):
        classified = {}
    if isinstance(live_hooks, Exception):
        live_hooks = {}

    if classified:
        state["destination_candidates"] = classified

    chips = []
    for chip in BASE_CHIPS:
        if classified and chip["id"] not in classified:
            continue
        chip_out = dict(chip)
        chip_out["live_hook"] = (live_hooks.get(chip["id"]) if isinstance(live_hooks, dict) else None) or None
        chips.append(chip_out)

    return chips or [dict(c) for c in BASE_CHIPS]


async def fetch_destination_suggestions(state: dict) -> list[dict]:
    """Return destination cards with road travel time, hook, and photo.

    Reads destination_candidates cached in state by build_experience_chips.
    Falls back to a new Tavily search if cache is empty (plan mode path).
    OSRM filters to destinations reachable within 12 hours by road.
    """
    experience_types = state.get("experience_types") or []
    trip_who = state.get("trip_who")
    trip_season = state.get("trip_season")

    # Step 1: gather candidate names from cache
    cached = state.get("destination_candidates") or {}
    candidate_names: list[str] = []
    candidate_type: dict[str, str] = {}

    for exp_type in experience_types:
        for name in cached.get(exp_type, []):
            if name not in candidate_type:
                candidate_names.append(name)
                candidate_type[name] = exp_type

    # Fallback: plan mode has no cache — search now
    if not candidate_names and experience_types:
        exp_str = " ".join(experience_types)
        season_str = trip_season or ""
        results = await tavily_search(
            f"{exp_str} destinations {season_str} India road trip".strip(),
            max_results=10,
        )
        if results:
            fallback = await _classify_destinations(results, "India")
            for exp_type in experience_types:
                for name in fallback.get(exp_type, []):
                    if name not in candidate_type:
                        candidate_names.append(name)
                        candidate_type[name] = exp_type

    if not candidate_names:
        return []

    # Step 2: resolve origin coordinates (geocodes city name if needed)
    origin = await resolve_origin_coords(state)

    # Step 3: geocode all candidates in parallel
    geocoded_coords = await asyncio.gather(
        *[geocode(name) for name in candidate_names],
        return_exceptions=True,
    )
    geocoded: list[tuple[str, dict]] = [
        (name, coords)
        for name, coords in zip(candidate_names, geocoded_coords)
        if isinstance(coords, dict) and coords
    ]

    if not geocoded:
        return []

    # Step 4: OSRM road filter — keep only ≤720 mins (12 hours)
    filtered: list[tuple[str, int, int, str]] = []  # (name, dist_km, dur_mins, travel_time)

    if origin and "lat" in origin:
        times = await batch_driving_times(origin, [c for _, c in geocoded])
        for (name, _), time_data in zip(geocoded, times):
            if time_data and time_data["duration_mins"] <= 720:
                filtered.append((name, time_data["distance_km"], time_data["duration_mins"], time_data["travel_time"]))
    else:
        # No origin coords — include all without distance data
        for name, _ in geocoded:
            filtered.append((name, 0, 0, ""))

    if not filtered:
        return []

    # Sort closer first, take top 10
    filtered.sort(key=lambda x: x[2])
    filtered = filtered[:10]
    names_filtered = [f[0] for f in filtered]

    # Step 5: Groq hook generation (one batch call)
    hooks = await _generate_destination_hooks(names_filtered, trip_who, trip_season, experience_types)

    # Step 6: Google Places photos (capped at 5 by fetch_place_photos)
    GOOGLE_MAPS_KEY = os.getenv("GOOGLE_API_KEY", "")
    photos_raw = await fetch_place_photos(names_filtered[:5], GOOGLE_MAPS_KEY)
    photo_by_name = {p["name"]: p["url"] for p in photos_raw if isinstance(p, dict)}

    # Step 7: assemble cards
    cards = []
    for i, (name, dist_km, dur_mins, travel_time) in enumerate(filtered):
        cards.append({
            "name": name,
            "experience_type": candidate_type.get(name, experience_types[0] if experience_types else ""),
            "distance_km": dist_km or None,
            "travel_time": travel_time or None,
            "hook": hooks[i] if i < len(hooks) else f"Explore {name}",
            "photo_url": photo_by_name.get(name),
        })

    return cards


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
