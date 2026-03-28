"""
nodes/resolve_location.py — Resolves user's current physical location for Phase 3.
Priority order:
  1. GPS coords already in state (source=gps) → pass through
  2. Google Maps link in message → regex extract lat/lng
  3. LLM extracts location phrase → geocode with dest appended
  4. missing_location=True → ask_for_location node
"""
import re
import asyncio
from typing import Optional, Literal

import aiohttp
import os

from app.graph.state import GraphState
from app.utils.logger import get_logger
from app.utils.message_utils import last_user_content

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY", "")


async def _geocode(place: str) -> Optional[dict]:
    """Geocode a place string using Google Maps Geocoding API."""
    if not GOOGLE_MAPS_KEY:
        return None
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": place, "key": GOOGLE_MAPS_KEY}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as r:
                data = await r.json()
                if data.get("results"):
                    loc = data["results"][0]["geometry"]["location"]
                    return {"lat": loc["lat"], "lng": loc["lng"], "label": place, "source": "geocoded"}
    except Exception as e:
        logger.error(f"Geocoding failed for '{place}': {e}")
    return None


async def _llm_extract_location(message: str) -> Optional[str]:
    """Use Groq to extract a location phrase from the message."""
    if not GROQ_API_KEY:
        return None
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [
            {"role": "system", "content": "Extract the specific location phrase from this message. Return ONLY the location name, nothing else. If no location is mentioned, return 'NONE'."},
            {"role": "user", "content": message},
        ],
        "max_tokens": 50,
        "temperature": 0,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                phrase = result["choices"][0]["message"]["content"].strip()
                return None if phrase == "NONE" else phrase
    except Exception as e:
        logger.error(f"LLM location extract failed: {e}")
    return None


async def resolve_location(state: GraphState) -> GraphState:
    """Resolve current location for Phase 3 queries."""

    # Priority 1: GPS already in state
    current = state.get("current_location")
    if current and current.get("source") == "gps":
        logger.info("resolve_location: Using GPS coords from state")
        return state

    # Priority 2: Google Maps share link in message
    messages = state.get("messages", [])
    latest_msg = last_user_content(messages) if messages else ""
    maps_link_match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", latest_msg)
    if maps_link_match:
        lat, lng = float(maps_link_match.group(1)), float(maps_link_match.group(2))
        state["current_location"] = {"lat": lat, "lng": lng, "label": "Shared location", "source": "maps_link"}
        logger.info(f"resolve_location: Extracted from Maps link {lat},{lng}")
        return state

    # Priority 3: LLM extract → geocode
    phrase = await _llm_extract_location(latest_msg)
    if phrase:
        dest = state.get("destination", "")
        full_phrase = f"{phrase}, {dest}" if dest else phrase
        coords = await _geocode(full_phrase)
        if coords:
            state["current_location"] = coords
            logger.info(f"resolve_location: Geocoded '{full_phrase}' → {coords}")
            return state

    # Priority 4: Ask the user
    logger.info("resolve_location: No location found — asking user")
    state["missing_location"] = True
    return state


async def ask_for_location(state: GraphState) -> dict:
    """Ask user to share their current location."""
    question = "To find nearby places, could you share your current location or tell me where you are?"
    return {
        "messages": [{"role": "assistant", "content": question}],
        "response": question
    }


def location_resolved_or_ask(state: GraphState) -> Literal["in_destination", "ask_for_location"]:
    """Conditional edge: proceed to in_destination or ask for location."""
    if state.get("missing_location"):
        return "ask_for_location"
    return "in_destination"
