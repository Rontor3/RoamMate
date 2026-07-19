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
