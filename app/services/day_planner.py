"""
app/services/day_planner.py — Sprint 6: route arcs, day plan, destination brief.
"""
import asyncio
import json
import os
from datetime import datetime
from typing import Any

import aiohttp

from app.services.area_cache import get_cached
from app.services.tavily_client import tavily_search
from app.utils.logger import get_logger

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

PACE_DENSITY: dict[str, int] = {"slow": 2, "mix": 3, "power": 5}


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from Groq response."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.split("```")[0]
    return text


async def _groq_post(prompt: str, max_tokens: int) -> Any:
    """POST to Groq and return parsed JSON. Raises on any failure."""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(GROQ_URL, headers=headers, json=body) as r:
            result = await r.json()
            text = result["choices"][0]["message"]["content"]
            return json.loads(_strip_fences(text))


async def generate_route_arcs(state: dict) -> list[dict]:
    """Generate 2–3 geographic route arc options for the user's selected places."""
    destination = state.get("destination", "")
    selected_area = state.get("selected_area", "")
    experience_types: list[str] = state.get("experience_types") or []
    trip_who = state.get("trip_who")
    trip_duration = max(state.get("trip_duration") or 1, 1)

    selected_ids = set(state.get("selected_places") or [])
    place_names = [
        p.get("name", p.get("id", ""))
        for cat in (state.get("place_cards") or [])
        for p in cat.get("places", [])
        if not selected_ids or p.get("id") in selected_ids
    ]

    default_arcs = [
        {
            "id": "selection_order",
            "label": "In Order",
            "description": "Visit places in the order you selected them",
            "place_order": place_names,
        },
        {
            "id": "reverse_order",
            "label": "Reverse Order",
            "description": "Start from the last place and work back",
            "place_order": list(reversed(place_names)),
        },
    ]

    prompt = (
        f"You are a travel expert. The user is visiting {destination}, focusing on the {selected_area} area. "
        f"Places selected: {place_names}. "
        f"Experience types: {experience_types}. Group: {trip_who or 'solo'}. "
        f"Trip duration: {trip_duration} days. "
        f"Generate 2-3 geographic route arcs — different orderings of these places that make physical sense "
        f"(e.g. north-to-south, coastal loop, base-camp style). "
        f"Return a JSON array. Each object: id (snake_case), label (short name), description (1 sentence — who it suits), "
        f"place_order (list of place names in visit order). "
        f"Return only valid JSON, no explanation."
    )

    try:
        parsed = await _groq_post(prompt, max_tokens=400)
        if isinstance(parsed, list) and parsed:
            logger.info(f"[day_planner] route_arcs ✓ {len(parsed)} arcs for {destination}")
            return parsed
    except Exception as e:
        logger.error(f"[day_planner] route_arcs Groq failed: {e} — using defaults")

    return default_arcs


async def generate_day_plan(state: dict) -> list[dict]:
    """Generate day-by-day timed itinerary from confirmed activities + route arc + pace."""
    destination = state.get("destination", "")
    route_arc: dict = state.get("route_arc") or {}
    selected_activities: list[str] = state.get("selected_activities") or []
    selected_pace = state.get("selected_pace", "mix")
    trip_duration = max(state.get("trip_duration") or 1, 1)

    # Reconstruct full activity objects from Redis cache (Sprint 5 cached activity_options)
    place_ids = [
        p.get("id")
        for cat in (state.get("place_cards") or [])
        for p in cat.get("places", [])
        if p.get("id")
    ]
    all_cached: list[dict] = []
    for pid in place_ids:
        cache_key = f"activity_options:{destination.lower()}:{pid.lower()}"
        cached = await get_cached(cache_key)
        if cached:
            all_cached.extend(cached)

    label_to_obj: dict[str, dict] = {a["label"].lower(): a for a in all_cached}
    full_activities = [
        label_to_obj.get(lbl.lower(), {"label": lbl, "duration": "1h", "time": "any", "vibe": "any"})
        for lbl in selected_activities
    ]

    acts_per_day = PACE_DENSITY.get(selected_pace, 3)
    place_order = route_arc.get("place_order") or [
        p.get("name", p.get("id", ""))
        for cat in (state.get("place_cards") or [])
        for p in cat.get("places", [])
    ]

    prompt = (
        f"Create a {trip_duration}-day itinerary for {destination}. "
        f"Place visit order: {place_order}. "
        f"Pace: {selected_pace} (~{acts_per_day} activities per day). "
        f"Activities to schedule (with duration and preferred time): {json.dumps(full_activities)}. "
        f"Rules: "
        f"1. Schedule morning activities (time='morning') before noon, evening ones after 4pm. "
        f"2. Spread activities across days — do not put more than {acts_per_day} per day. "
        f"3. Group activities at the same place on the same day when possible. "
        f"4. Give each day a short punchy title based on the places visited. "
        f"5. Add a one-sentence 'note' per day (e.g. arrival tip, pace note). "
        f"Return a JSON array of day objects. Each day: "
        f"day (int), title (str), activities (list of {{time, activity, place, duration}}), note (str). "
        f"Return only valid JSON, no explanation."
    )

    try:
        parsed = await _groq_post(prompt, max_tokens=800)
        if isinstance(parsed, list) and parsed:
            logger.info(f"[day_planner] day_plan ✓ {len(parsed)} days for {destination}")
            return parsed
    except Exception as e:
        logger.error(f"[day_planner] day_plan Groq failed: {e} — distributing evenly")

    chunks = [selected_activities[i::trip_duration] for i in range(trip_duration)]
    return [
        {"day": i + 1, "title": f"Day {i + 1}", "activities": [{"activity": a} for a in chunk], "note": ""}
        for i, chunk in enumerate(chunks)
    ]
