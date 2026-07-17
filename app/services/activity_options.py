"""
app/services/activity_options.py — Build activity mini-cards for a selected place.

Reads cached area Reddit signals (Sprint 4 prefetch), calls Groq to generate
4–6 place-specific activities, caches result for 6 hours.
"""
import json
import os
from typing import Any

import aiohttp

from app.services.area_cache import get_cached, set_cached
from app.utils.logger import get_logger

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

DEFAULT_ACTIVITIES: list[dict] = [
    {"id": "explore_on_foot", "label": "Explore on foot",   "duration": "1h",  "time": "any", "vibe": "any"},
    {"id": "photo_walk",      "label": "Photo walk",        "duration": "1h",  "time": "any", "vibe": "any"},
    {"id": "try_food_nearby", "label": "Try food nearby",   "duration": "45m", "time": "any", "vibe": "any"},
]


async def build_activity_options(
    place_id: str,
    place_name: str,
    destination: str,
    area_id: str,
    intent: Any,
    trip_who: str | None,
) -> list[dict]:
    """
    Return 4–6 activity mini-cards for place_id.
    Reads area Reddit cache → calls Groq → caches result for 6h.
    Returns DEFAULT_ACTIVITIES on any failure.
    """
    cache_key = f"activity_options:{destination.lower()}:{place_id.lower()}"

    cached = await get_cached(cache_key)
    if cached:
        logger.info(f"[activity_options] cache hit: {cache_key}")
        return cached

    # Step 1 — Read area Reddit signals (best-effort)
    reddit_context = ""
    try:
        area_cache_key = f"reddit_area:{destination.lower()}:{area_id.lower()}"
        cached_reddit = await get_cached(area_cache_key)
        area_signals = cached_reddit[0] if cached_reddit else {}
        place_signals = area_signals.get("place_signals", {})
        for signal_key, signal_val in place_signals.items():
            if place_name.lower() in signal_key.lower():
                highlights = signal_val.get("review_highlights") or []
                vibe_tags = signal_val.get("vibe_tags") or []
                parts = highlights[:3] + vibe_tags[:3]
                reddit_context = "; ".join(str(p) for p in parts)[:400]
                break
    except Exception as e:
        logger.warning(f"[activity_options] reddit cache read failed: {e}")

    # Step 2 — Groq call
    vibe_str = ", ".join(v.value for v in intent.vibe) if intent and intent.vibe else ""
    local_intel = f"Local intel: {reddit_context}" if reddit_context else ""
    prompt = (
        f"Generate 4-6 specific activities a traveller can do at {place_name} in {destination}. "
        f"Group: {trip_who or 'solo'}. "
        f"Vibe: {vibe_str or 'general'}. "
        f"{local_intel} "
        f"Return a JSON array. Each object must have: "
        f"id (snake_case), label (display name, max 6 words), duration (e.g. '1h', '45m', 'half-day'), "
        f"time ('morning'|'afternoon'|'evening'|'any'), vibe ('adventure'|'chill'|'cultural'|'party'|'any'). "
        f"Return only valid JSON, no explanation."
    )

    activities = DEFAULT_ACTIVITIES
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        body = {
            "model": _MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                text = result["choices"][0]["message"]["content"].strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                parsed = json.loads(text)
                if isinstance(parsed, list) and parsed:
                    activities = parsed
                    logger.info(f"[activity_options] Groq ✓ {len(activities)} activities for {place_name}")
    except Exception as e:
        logger.error(f"[activity_options] Groq failed for {place_name}: {e} — using defaults")

    if activities is not DEFAULT_ACTIVITIES:
        await set_cached(cache_key, activities, ttl=21600)
    return activities
