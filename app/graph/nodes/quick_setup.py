"""
nodes/quick_setup.py — Direct Phase 3 entry without prior planning.
Geocodes location, fetches Reddit + weather in parallel, scores area,
sets needs_vibe_clarification.
"""
import asyncio
import os
from typing import Literal

import aiohttp

from app.graph.state import GraphState
from app.services.reddit_signals import get_reddit_place_signals, build_reddit_queries
from app.services.scoring_engine import ScoringEngine
from app.models import TravelIntent
from app.utils.logger import get_logger

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY", "")
_scoring_engine = ScoringEngine()


async def _geocode_from_intent(intent: TravelIntent) -> dict:
    """Geocode the destination from intent."""
    dest = intent.destination.city or intent.destination.area or ""
    if not dest or not GOOGLE_MAPS_KEY:
        return {}
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params={"address": dest, "key": GOOGLE_MAPS_KEY}) as r:
                data = await r.json()
                if data.get("results"):
                    loc = data["results"][0]["geometry"]["location"]
                    return {"lat": loc["lat"], "lng": loc["lng"], "label": dest, "source": "geocoded"}
    except Exception as e:
        logger.error(f"quick_setup geocode failed: {e}")
    return {}


async def _get_weather(location: dict) -> dict:
    """Fetch weather from OpenWeatherMap MCP."""
    if not location:
        return {}
    try:
        from app.tools.registry import call_tool
        return await call_tool("openweather", "get_current_weather", location)
    except Exception as e:
        logger.warning(f"quick_setup weather failed: {e}")
        return {}


async def quick_setup(state: GraphState) -> GraphState:
    """Handle direct Phase 3 entry — minimal context fast-path."""
    intent: TravelIntent = state.get("travel_intent") or TravelIntent()
    logger.info(f"quick_setup: dest={state.get('destination')}, gps={bool(state.get('current_location', {}).get('source') == 'gps')}")

    # Geocode unless we have GPS
    location = state.get("current_location", {})
    if not location or location.get("source") != "gps":
        geocoded = await _geocode_from_intent(intent)
        if geocoded:
            state["current_location"] = geocoded
            location = geocoded

    # 2 parallel: Reddit + weather
    reddit_task = get_reddit_place_signals(intent, post_limit=8)
    weather_task = _get_weather(location)
    reddit, weather = await asyncio.gather(reddit_task, weather_task, return_exceptions=True)

    state["reddit_signals"] = reddit if not isinstance(reddit, Exception) else {"place_signals": {}, "raw_posts_text": ""}
    state["weather_data"] = weather if not isinstance(weather, Exception) else {}

    # Score area
    raw_text = state["reddit_signals"].get("raw_posts_text", "")
    area_scores = _scoring_engine.score_area(reddit_text=raw_text or None)
    state["area_scores"] = area_scores

    # Determine if vibe clarification is needed
    has_vibe = bool(intent.vibe)
    has_interests = bool(intent.interests)
    state["needs_vibe_clarification"] = not (has_vibe or has_interests)
    state["quick_setup_done"] = True

    logger.info(f"quick_setup done: needs_vibe_clarification={state['needs_vibe_clarification']}")
    return state


async def ask_vibe(state: GraphState) -> dict:
    """Ask user one lightweight vibe question before proceeding."""
    dest = state.get("destination", "your destination")
    question = (
        f"I'm ready to help you explore {dest}! "
        "Are you looking for something chill (cafes, parks), adventurous (hikes, extreme sports), "
        "cultural (museums, art), or just surprise me?"
    )
    return {
        "messages": [{"role": "assistant", "content": question}],
        "response": question
    }


def vibe_or_location(state: GraphState) -> Literal["ask_vibe", "resolve_location"]:
    """Conditional edge: clarify vibe or proceed to location resolution."""
    if state.get("needs_vibe_clarification"):
        return "ask_vibe"
    return "resolve_location"
