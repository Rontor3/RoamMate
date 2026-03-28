"""
nodes/planning.py — Phase 2: Planning
Full fetch: Reddit signals + blog signals + Maps places + hotels (if needed).
ScoringEngine → score_all → Ranker.rank_places.
Caches scored results in Redis at scores:{dest}:{vibe_key} TTL 12hr.
"""
import asyncio
import json
import os
from typing import Optional

import redis.asyncio as aioredis

from app.graph.state import GraphState
from app.models import Place, PlaceAreaMapping, TravelIntent
from app.services.reddit_signals import get_reddit_place_signals
from app.services.blog_signals import get_blog_signals
from app.services.scoring_engine import ScoringEngine
from app.services.ranker import Ranker
from app.tools.fetchers.places import search_places
from app.tools.fetchers.hotels_flights import search_hotels
from app.utils.logger import get_logger

logger = get_logger(__name__)

_scoring_engine = ScoringEngine()
_ranker = Ranker()
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


async def _get_redis():
    try:
        return await aioredis.from_url(REDIS_URL, decode_responses=True)
    except Exception:
        return None


async def _get_or_fetch(cache_key: str, fetch_coro, ttl: int = 43200):
    """Return cached value or call fetch_coro and cache the result."""
    r = await _get_redis()
    if r:
        try:
            cached = await r.get(cache_key)
            if cached:
                logger.info(f"Cache hit: {cache_key}")
                return json.loads(cached)
        except Exception:
            pass

    data = await fetch_coro
    if r:
        try:
            await r.setex(cache_key, ttl, json.dumps(data, default=str))
        except Exception:
            pass
    return data


async def _fetch_maps_places(destination: str) -> list:
    """Fetch places from Google Maps MCP."""
    try:
        return await search_places(destination)
    except Exception as e:
        logger.warning(f"Maps places fetch failed: {e}")
        return []


async def _fetch_hotels(destination: str) -> list:
    """Fetch hotels from Booking MCP."""
    try:
        return await search_hotels(destination)
    except Exception as e:
        logger.warning(f"Hotel fetch failed: {e}")
        return []


def _rank_places(raw_places: list, intent: TravelIntent, reddit_signals: dict, area_scores) -> list:
    """Map raw place dicts to Place objects, rank them, return formatted dicts."""
    mappings = []
    for p in raw_places:
        try:
            # Check for Reddit crowd signal for this place
            place_signal = reddit_signals.get("place_signals", {}).get(p.get("name", ""), {})
            place_obj = Place(
                place_id=p.get("place_id", p.get("id", p.get("name", "unknown"))),
                name=p.get("name", "Unknown Place"),
                place_type=p.get("type", "point_of_interest"),
                lat=float(p.get("lat", p.get("latitude", 0.0))),
                lon=float(p.get("lng", p.get("longitude", 0.0))),
                rating=p.get("rating"),
                review_count=int(p.get("user_ratings_total", p.get("review_count", 0))),
                price_level=p.get("price_level"),
                tags=[t for t in p.get("types", p.get("tags", []))],
            )
            # Heuristic: drop low-rated places (< 4.2)
            if place_obj.rating is not None and place_obj.rating < 4.2:
                continue
            mappings.append(PlaceAreaMapping(place=place_obj))
        except Exception as e:
            logger.warning(f"Failed to map place '{p.get('name')}': {e}")

    if not mappings:
        return []

    ranked = _ranker.rank_places(mappings, intent, area_scores)
    return [
        {
            "name": rp.place.name,
            "rating": rp.place.rating,
            "final_score": rp.rank_score,
            "rank": rp.rank_position,
            "explanation": {
                "top_factor": rp.explanation.top_factor if rp.explanation else "",
                "weakest_factor": rp.explanation.weakest_factor if rp.explanation else "",
            },
            "confidence": rp.confidence,
            "tags": rp.place.tags,
        }
        for rp in ranked
    ]


async def planning(state: GraphState) -> GraphState:
    """Phase 2 — full fetch, score and rank."""
    dest = state.get("destination", "")
    intent: TravelIntent = state.get("travel_intent") or TravelIntent()
    vibe_key = "_".join(v.value for v in intent.vibe) if intent.vibe else "general"
    cache_key = f"scores:{dest}:{vibe_key}"

    logger.info(f"planning: starting for '{dest}' (vibe={vibe_key})")

    # Parallel fetches
    reddit_task = get_reddit_place_signals(intent)
    blog_task = get_blog_signals(dest, vibe_key)
    maps_task = _fetch_maps_places(dest)
    hotel_task = _fetch_hotels(dest) if intent.needs_hotel else asyncio.sleep(0, result=[])

    reddit, blog, places_raw, hotels = await asyncio.gather(
        reddit_task, blog_task, maps_task, hotel_task, return_exceptions=True
    )

    reddit = reddit if not isinstance(reddit, Exception) else {"place_signals": {}, "raw_posts_text": ""}
    blog = blog if not isinstance(blog, Exception) else {"sources": [], "top_answer": ""}
    places_raw = places_raw if not isinstance(places_raw, list) else places_raw
    hotels = hotels if not isinstance(hotels, list) else hotels

    # Record which tools were used this turn
    events: list = state.get("tool_events") or []
    reddit_posts = len(reddit.get("raw_posts_text", "").split("---")) if reddit.get("raw_posts_text") else 0
    events.append(f"[Reddit] {reddit_posts} posts retrieved for '{dest}'")
    blog_sources = len(blog.get("sources", []))
    events.append(f"[Tavily/blog] {blog_sources} sources for '{dest}'")
    events.append(f"[MCP/google_maps] {len(places_raw)} places returned")
    if intent.needs_hotel:
        events.append(f"[MCP/booking] {len(hotels) if isinstance(hotels, list) else 0} hotels returned")
    state["tool_events"] = events

    state["reddit_signals"] = reddit
    state["blog_signals"] = blog
    state["hotel_data"] = hotels if isinstance(hotels, list) else []

    # Score area using Reddit text
    raw_text = reddit.get("raw_posts_text", "")
    area_scores = _scoring_engine.score_area(reddit_text=raw_text or None)
    state["area_scores"] = area_scores

    # Rank places
    ranked = _rank_places(places_raw, intent, reddit, area_scores)
    state["ranked_places"] = ranked

    logger.info(f"planning complete: {len(ranked)} places ranked")
    return state
