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
from app.services.area_cache import get_cached, set_cached
from app.utils.place_photos import fetch_place_photos
from app.utils.logger import get_logger
from app.tools.fetchers.places import search_places
from app.services.ranker import Ranker
from app.services.scorer import score_all_places
from app.models import Place, PlaceAreaMapping
from app.services.reddit_signals import get_area_reddit_signals

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

_ranker = Ranker()

DEFAULT_PLACE_CATEGORIES: list[dict] = [
    {"label": "Things to Do", "query": "attractions activities things to do"},
    {"label": "Cafés & Bars", "query": "cafes bars restaurants local food"},
    {"label": "Viewpoints & Nature", "query": "viewpoints nature parks scenic"},
]

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
        classified = {
            k: [str(v) for v in vals]
            for k, vals in result.items()
            if k in _CATEGORY_DESCRIPTIONS and isinstance(vals, list)
        }
        # Cap to 5 per category to limit geocode/OSRM fanout
        classified = {k: v[:5] for k, v in classified.items()}
        return classified
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
    Returns list in same order as input; falls back to "Visit {name}" on failure.
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
    return [f"Visit {d}" for d in destinations]


# ── Sprint 4: place card helpers ──────────────────────────────────────────────

def _rank_places_for_area(
    places_raw: list[dict],
    intent: any,
    reddit_signals: dict,
    blog_signals: dict,
) -> list[dict]:
    """Filter by rating, attach social scores, rank. Returns top-3 minimal dicts."""
    filtered = [p for p in places_raw if (p.get("rating") or 0) >= 4.2]
    if not filtered:
        return []
    score_all_places(filtered, reddit_signals, blog_signals)
    mappings: list[PlaceAreaMapping] = []
    for p in filtered:
        place = Place(
            place_id=p.get("place_id") or p.get("id", ""),
            name=p.get("name", ""),
            place_type=(p.get("types") or p.get("tags") or ["attraction"])[0],
            lat=float(p.get("lat") or 0.0),
            lon=float(p.get("lng") or p.get("lon") or 0.0),
            rating=p.get("rating"),
            review_count=int(p.get("user_ratings_total") or p.get("review_count") or 0),
            tags=p.get("types") or p.get("tags") or [],
        )
        mappings.append(PlaceAreaMapping(place=place))
    ranked = _ranker.rank_places(mappings, intent, area_scores=None) if intent else []
    id_to_raw: dict[str, dict] = {(p.get("place_id") or p.get("id", "")): p for p in filtered}
    result = []
    for rp in ranked[:3]:
        pid = rp.place.place_id
        raw = id_to_raw.get(pid, {})
        result.append({"id": pid, "name": rp.place.name, "photo_url": raw.get("photo_url")})
    return result


async def _prefetch_area_reddit(
    destination: str,
    area_id: str,
    area_name: str,
    experience_types: list[str],
) -> None:
    """Background task: fetch area-level Reddit signals and cache for Sprint 5."""
    cache_key = f"reddit_area:{destination.lower()}:{area_id.lower()}"
    existing = await get_cached(cache_key)
    if existing:
        return
    try:
        signals = await get_area_reddit_signals(area_name, destination, experience_types)
        if signals.get("place_signals"):
            await set_cached(cache_key, [signals], ttl=3600)
    except Exception:
        pass


async def fetch_place_cards(state: dict) -> list[dict]:
    """4-step pipeline: Groq categories → Maps search → rank → Groq hooks. Returns categorised place cards."""
    destination = state.get("destination", "")
    area_id = state.get("selected_area", "")
    experience_types = state.get("experience_types") or []
    selected_vibe_ids = state.get("selected_vibe_ids") or []
    travel_intent = state.get("travel_intent")
    reddit_signals = state.get("reddit_signals") or {}
    blog_signals = state.get("blog_signals") or {}

    area_name = area_id
    for area in (state.get("area_cards") or []):
        if area.get("id") == area_id:
            area_name = area.get("name", area_id)
            break

    exp_key = "|".join(sorted(experience_types)) if experience_types else "|".join(sorted(selected_vibe_ids))
    cache_key = f"place_cards:{destination.lower()}:{area_id.lower()}:{exp_key}"
    cached = await get_cached(cache_key)
    if cached:
        state["place_cards"] = cached
        try:
            asyncio.create_task(_prefetch_area_reddit(destination, area_id, area_name, experience_types))
        except Exception:
            pass
        return cached

    # Step 1 — Category determination
    trip_who = state.get("trip_who") or ""
    trip_season = state.get("trip_season") or ""
    exp_desc = ", ".join(experience_types) if experience_types else ", ".join(selected_vibe_ids)
    cat_prompt = (
        f"You are a travel expert. For {area_name} in {destination}, "
        f"experience types: {exp_desc or 'general'}, group: {trip_who}, season: {trip_season}. "
        f"Return a JSON array of 3-4 category objects with 'label' (display name) and 'query' (Google Maps search terms). "
        f"Always include a food/drink category (Cafés & Bars or Restaurants). "
        f'Example: [{{"label": "Adventure Spots", "query": "trekking viewpoints cliff"}}]. '
        f"Return only valid JSON, no explanation."
    )
    raw_cats = await _groq_json(cat_prompt, max_tokens=250)
    categories: list[dict] = raw_cats if (isinstance(raw_cats, list) and raw_cats) else DEFAULT_PLACE_CATEGORIES

    # Step 2 — Maps search per category (parallel)
    search_tasks = [search_places(f"{area_name}, {destination}", cat["query"]) for cat in categories]
    raw_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    # Step 3 — Score and rank per category
    categories_with_places: list[dict] = []
    for cat, raw in zip(categories, raw_results):
        if isinstance(raw, Exception) or not raw:
            continue
        ranked = _rank_places_for_area(raw, travel_intent, reddit_signals, blog_signals)
        if ranked:
            categories_with_places.append({"label": cat["label"], "places": ranked})

    if not categories_with_places:
        state["place_cards"] = []
        try:
            asyncio.create_task(_prefetch_area_reddit(destination, area_id, area_name, experience_types))
        except Exception:
            pass
        return []

    # Step 4 — Hook generation (one batch Groq call)
    all_ids = [p["id"] for cat in categories_with_places for p in cat["places"]]
    all_names = [p["name"] for cat in categories_with_places for p in cat["places"]]
    hook_prompt = (
        f"Write a punchy one-liner hook (under 15 words) for each place in {area_name}, {destination}. "
        f"Return a JSON object mapping place_id to hook string. "
        f"Places: {json.dumps(dict(zip(all_ids, all_names)))}. "
        f"Return only valid JSON."
    )
    hooks_raw = await _groq_json(hook_prompt, max_tokens=800)
    hooks: dict[str, str] = hooks_raw if isinstance(hooks_raw, dict) else {}

    categories_out = []
    for cat in categories_with_places:
        places_out = [
            {
                "id": p["id"],
                "name": p["name"],
                "hook": hooks.get(p["id"]) or f"A great spot in {area_name}",
                "photo_url": p["photo_url"],
            }
            for p in cat["places"]
        ]
        categories_out.append({"label": cat["label"], "places": places_out})

    state["place_cards"] = categories_out
    await set_cached(cache_key, categories_out, ttl=43200)
    try:
        asyncio.create_task(_prefetch_area_reddit(destination, area_id, area_name, experience_types))
    except Exception:
        pass
    return categories_out


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
    if state.get("selected_place"):
        return "place_selected"
    if state.get("places_shown"):
        if not state.get("trip_duration"):
            return "duration_pending"
        return "places_shown"
    if state.get("selected_area"):
        return "area_selected"
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
        if state.get("experience_types"):
            # Branch A: user came via experience chips — skip vibe cards
            areas = await fetch_area_cards(state)
            return "show_area_cards", {"areas": areas}
        else:
            # Branch B: user typed destination directly — capture travel style first
            vibes = await fetch_vibe_cards(state)
            return "show_vibe_cards", {"vibes": vibes}

    if stage == "vibe_selected":
        # Branch B: vibes confirmed → show area cards
        areas = await fetch_area_cards(state)
        return "show_area_cards", {"areas": areas}

    if stage == "area_selected":
        categories = await fetch_place_cards(state)
        return "show_place_cards", {"categories": categories}

    if stage == "place_selected":
        return "show_activity_options", {"activities": []}

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

BASE_VIBE_CARDS: list[dict] = [
    {
        "id": "adv",
        "label": "Adventure & Outdoors",
        "eyebrow": "Physical · Outdoors",
        "description": "Trails, altitude, water, adrenaline",
        "tags": ["trekking", "water sports", "adrenaline"],
    },
    {
        "id": "loc",
        "label": "Culture & Food",
        "eyebrow": "Culture · Food · People",
        "description": "History, local cuisine, markets, people",
        "tags": ["heritage", "food", "local life"],
    },
    {
        "id": "spt",
        "label": "Spots & Scenes",
        "eyebrow": "Spots · Scenes",
        "description": "Viewpoints, sunsets, cafés, photo moments",
        "tags": ["sunsets", "cafes", "scenic"],
    },
    {
        "id": "hid",
        "label": "Hidden & Slow",
        "eyebrow": "Hidden · Slow",
        "description": "Off-path, quiet, unhurried, local secrets",
        "tags": ["offbeat", "quiet", "slow travel"],
    },
]


async def build_experience_chips(state: dict) -> list[dict]:
    """Return geo-filtered experience chips with live event hooks.

    plan mode: all 6 chips returned immediately.
    now mode: Tavily pre-fetch + Groq classification filters to nearby categories.
    Falls back to all 6 if Tavily or Groq fails.
    Mutates state["destination_candidates"] as a side-effect for the next turn.
    """
    if state.get("trip_mode") not in ("now", None):
        return [{**c, "live_hook": None} for c in BASE_CHIPS]

    origin = get_origin(state)
    origin_name = origin.get("name", "") if origin else ""
    if not origin_name:
        return [{**c, "live_hook": None} for c in BASE_CHIPS]

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

    return chips or [{**c, "live_hook": None} for c in BASE_CHIPS]


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
            filtered.append((name, None, None, None))

    if not filtered:
        return []

    # Sort closer first (None duration sorts last), take top 10
    filtered.sort(key=lambda x: (x[2] is None, x[2] or 0))
    filtered = filtered[:10]
    names_filtered = [f[0] for f in filtered]

    # Step 5: Groq hook generation (one batch call)
    hooks = await _generate_destination_hooks(names_filtered, trip_who, trip_season, experience_types)

    # Step 6: Google Places photos for all candidates
    GOOGLE_MAPS_KEY = os.getenv("GOOGLE_API_KEY", "")
    photos_raw = await fetch_place_photos(names_filtered, GOOGLE_MAPS_KEY)
    photo_by_name = {p["name"]: p["url"] for p in photos_raw if isinstance(p, dict)}

    # Step 7: assemble cards
    cards = []
    for i, (name, dist_km, dur_mins, travel_time) in enumerate(filtered):
        cards.append({
            "name": name,
            "experience_type": candidate_type.get(name, experience_types[0] if experience_types else ""),
            "distance_km": dist_km,
            "travel_time": travel_time,
            "hook": hooks[i] if i < len(hooks) else f"Visit {name}",
            "photo_url": photo_by_name.get(name),
        })

    return cards


async def fetch_vibe_cards(state: dict) -> list[dict]:
    """Return 4 vibe cards with destination-specific description hooks.

    Branch B only — called when user typed destination directly with no experience_types.
    Falls back to BASE_VIBE_CARDS generic descriptions on Groq failure.
    Cached by destination for 24h.
    """
    destination = state.get("destination", "")
    if not destination:
        return [{**v} for v in BASE_VIBE_CARDS]

    cache_key = f"vibe_cards:{destination.lower()}"
    cached = await get_cached(cache_key)
    if cached is not None:
        return cached

    # Build context from already-fetched blog signals
    blog_ctx = ""
    blog = state.get("blog_signals") or {}
    if blog:
        snippets = []
        for val in blog.values():
            if isinstance(val, list):
                snippets.extend(str(v)[:150] for v in val[:2])
            elif isinstance(val, str):
                snippets.append(val[:200])
        blog_ctx = " | ".join(snippets[:5])

    prompt = (
        f'You are a vivid travel writer. For the destination "{destination}", write a short '
        f'destination-specific hook (max 70 chars) for each of the 4 travel vibes below. '
        f'Use specific place names and activities from {destination} — not generic descriptions.\n'
        f'Context: {blog_ctx or f"use your knowledge of {destination}"}\n\n'
        f'Return JSON only (no markdown):\n'
        f'{{"adv": "...", "loc": "...", "spt": "...", "hid": "..."}}'
    )
    hooks = await _groq_json(prompt, max_tokens=300)

    cards = []
    for v in BASE_VIBE_CARDS:
        card = {**v}
        if isinstance(hooks, dict) and v["id"] in hooks and hooks[v["id"]]:
            card["description"] = str(hooks[v["id"]])[:70]
        cards.append(card)

    await set_cached(cache_key, cards)
    return cards


async def fetch_area_cards(state: dict) -> list[dict]:
    """Return 3-5 area/neighbourhood cards for the confirmed destination.

    Pipeline:
      1. Scale assessment (Groq) — flat list vs zoned grouping
      2. Tavily enrichment per zone (parallel)
      3. Area generation with teaser+summary (Groq, one batch call)
      4. Photos (Google Places, parallel)
    Cached by (destination, experience_type|vibe_ids) for 24h.
    """
    destination = state.get("destination", "")
    if not destination:
        return []

    experience_types: list[str] = state.get("experience_types") or []
    vibe_ids: list[str] = state.get("selected_vibe_ids") or []
    exp_key = "|".join(sorted(experience_types)) if experience_types else "|".join(sorted(vibe_ids))
    cache_key = f"area_cards:{destination.lower()}:{exp_key}"

    cached = await get_cached(cache_key)
    if cached is not None:
        state["area_cards"] = cached
        return cached

    trip_season = state.get("trip_season") or "any season"
    trip_who = state.get("trip_who") or "travellers"
    interest_str = ", ".join(experience_types or vibe_ids) or "travel"

    # Step 1: Scale assessment
    scale_prompt = (
        f'Destination: "{destination}". Travel interest: "{interest_str}".\n'
        f'Does exploring {destination} need:\n'
        f'(a) "flat" — list specific neighbourhoods/areas directly (small or focused destination), or\n'
        f'(b) "zoned" — group areas under broad geographic zones like North/South or major cities?\n\n'
        f'Return JSON only (no markdown):\n'
        f'{{"tier": "flat", "zones": []}} or {{"tier": "zoned", "zones": ["North Goa", "South Goa"]}}'
    )
    scale = await _groq_json(scale_prompt, max_tokens=150)
    if not isinstance(scale, dict) or "tier" not in scale:
        scale = {"tier": "flat", "zones": []}

    tier = scale.get("tier", "flat")
    zones: list[str] = scale.get("zones") or []
    if not zones:
        zones = [destination]

    # Step 2: Tavily enrichment per zone (parallel)
    tavily_tasks = [
        tavily_search(f"{zone} {interest_str} areas things to do {trip_season}", max_results=5)
        for zone in zones
    ]
    zone_raw = await asyncio.gather(*tavily_tasks, return_exceptions=True)
    zone_context: dict[str, str] = {}
    for zone, result in zip(zones, zone_raw):
        if isinstance(result, list) and result:
            zone_context[zone] = " | ".join(
                r.get("content", "")[:200] for r in result[:3] if r.get("content")
            )
        else:
            zone_context[zone] = ""

    # Step 3: Area generation (one Groq batch call)
    zones_ctx = "\n".join(f"- {z}: {zone_context.get(z) or 'no extra context'}" for z in zones)
    area_prompt = (
        f'You are a travel expert writing for a travel app. '
        f'For destination "{destination}" with interest in "{interest_str}" '
        f'({trip_who}, {trip_season}), identify 3–5 specific areas or neighbourhoods to explore.\n\n'
        f'Geographic context:\n{zones_ctx}\n\n'
        f'For each area provide:\n'
        f'- id: lowercase slug (e.g. "vagator")\n'
        f'- name: display name (e.g. "Vagator")\n'
        f'- zone: geographic zone it belongs to (e.g. "North Goa"), or null if not applicable\n'
        f'- teaser: 3-4 punchy lines — vivid, specific, honest about who it suits. No generic phrases.\n'
        f'- summary: one full paragraph — geography, vibe, best things to do, when to visit, who it suits\n'
        f'- tags: 3-4 short labels (e.g. ["cliffs", "nightlife", "sunsets"])\n\n'
        f'Return a JSON array only (no markdown):\n'
        f'[{{"id":"...","name":"...","zone":"..." or null,"teaser":"...","summary":"...","tags":["..."]}}]'
    )
    areas_raw = await _groq_json(area_prompt, max_tokens=1500)
    if not isinstance(areas_raw, list) or not areas_raw:
        state["area_cards"] = []
        return []

    # Step 4: Photos (parallel)
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    photo_tasks = [
        fetch_place_photos([a.get("name", "")], GOOGLE_API_KEY)
        for a in areas_raw
    ]
    photo_raw = await asyncio.gather(*photo_tasks, return_exceptions=True)
    photo_map: dict[int, str | None] = {}
    for idx, (a, pr) in enumerate(zip(areas_raw, photo_raw)):
        if isinstance(pr, list) and pr:
            photo_map[idx] = pr[0].get("url")
        else:
            photo_map[idx] = None

    areas = [
        {
            "id": a.get("id", ""),
            "name": a.get("name", ""),
            "zone": a.get("zone") if tier == "zoned" else None,
            "teaser": a.get("teaser", ""),
            "summary": a.get("summary", ""),
            "tags": a.get("tags") or [],
            "photo_url": photo_map.get(idx),
        }
        for idx, a in enumerate(areas_raw)
    ]

    state["area_cards"] = areas
    await set_cached(cache_key, areas)
    return areas


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
