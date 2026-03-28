"""
nodes/in_destination.py — Phase 3: In-Destination
Detects query type (food/events/sights), LLM generates 4 Maps queries,
fires all 4 in parallel, builds mappings with score gap handling, ranks.
Persists new scores in background via asyncio.create_task.
"""
import asyncio
import json
import os
from typing import List, Dict, Any

import aiohttp

from app.graph.state import GraphState
from app.models import Place, PlaceAreaMapping, TravelIntent
from app.services.ranker import Ranker
from app.services.scoring_engine import ScoringEngine
from app.utils.logger import get_logger
from app.utils.message_utils import last_user_content

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_ranker = Ranker()
_scoring_engine = ScoringEngine()


def _detect_query_type(message: str) -> str:
    """Classify message as food, events, or sights."""
    msg = message.lower()
    if any(w in msg for w in ["eat", "food", "restaurant", "cafe", "coffee", "drink", "bar"]):
        return "food"
    if any(w in msg for w in ["event", "happening", "festival", "show", "concert", "tonight"]):
        return "events"
    return "sights"


async def _build_query_set(destination: str, query_type: str, intent: TravelIntent) -> List[str]:
    """Use Groq to generate 4 targeted Maps search queries."""
    vibe = intent.vibe[0].value if intent and intent.vibe else "general"
    interests = ", ".join(intent.interests[:3]) if intent and intent.interests else query_type

    system = "Generate exactly 4 specific Google Maps search queries as a JSON array of strings. No explanation."
    prompt = (
        f"Destination: {destination}\nQuery type: {query_type}\nUser vibe: {vibe}\nInterests: {interests}\n"
        "Generate 4 diverse, specific Maps search queries to find the best local options."
    )
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "max_tokens": 200, "temperature": 0.3,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                content = result["choices"][0]["message"]["content"]
                import re
                match = re.search(r"\[.*?\]", content, re.DOTALL)
                if match:
                    return json.loads(match.group())
    except Exception as e:
        logger.error(f"Query generation failed: {e}")

    # Fallback queries
    return [
        f"best {query_type} near {destination}",
        f"top rated {query_type} in {destination}",
        f"local {query_type} {destination}",
        f"hidden gem {query_type} {destination}",
    ]


async def _fetch_nearby_broad(queries: List[str], location: dict) -> List[Dict[str, Any]]:
    """Fire all Maps queries in parallel."""
    async def fetch_one(query: str) -> List[Dict]:
        try:
            from app.tools.registry import call_tool
            args = {"query": query}
            if location:
                args["lat"] = location.get("lat")
                args["lng"] = location.get("lng")
            result = await call_tool("google_maps", "nearby_search", args)
            return result.get("places", []) if isinstance(result, dict) else []
        except Exception as e:
            logger.warning(f"Nearby search failed for '{query}': {e}")
            return []

    results = await asyncio.gather(*[fetch_one(q) for q in queries], return_exceptions=True)
    all_places: List[Dict] = []
    seen_ids = set()
    for r in results:
        if isinstance(r, list):
            for p in r:
                pid = p.get("place_id", p.get("name", ""))
                if pid not in seen_ids:
                    seen_ids.add(pid)
                    all_places.append(p)
    return all_places


def _build_mappings(places: List[Dict], pre_scored: Dict[str, float]) -> List[PlaceAreaMapping]:
    """Build PlaceAreaMapping list, merging pre-scored ratings where available."""
    mappings = []
    for p in places:
        name = p.get("name", "")
        rating = p.get("rating")

        # Score gap handling: if pre-scored, use stored score to set review_count proxy
        if name in pre_scored:
            review_count = int(pre_scored[name] * 100)
        else:
            review_count = int(p.get("user_ratings_total", 0))

        if rating is not None and rating < 4.2:
            continue  # Heuristic filter

        try:
            place_obj = Place(
                place_id=p.get("place_id", name),
                name=name,
                place_type=p.get("type", "point_of_interest"),
                lat=float(p.get("lat", p.get("latitude", 0.0))),
                lon=float(p.get("lng", p.get("longitude", 0.0))),
                rating=rating,
                review_count=review_count,
                price_level=p.get("price_level"),
                tags=p.get("types", p.get("tags", [])),
            )
            mappings.append(PlaceAreaMapping(place=place_obj))
        except Exception as e:
            logger.warning(f"Mapping failed for '{name}': {e}")
    return mappings


async def _persist_scores_bg(place_ids: List[str], scores: List[float]):
    """Background task to persist scores to Redis."""
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        import redis.asyncio as aioredis
        r = await aioredis.from_url(redis_url, decode_responses=True)
        async with r.pipeline() as pipe:
            for pid, score in zip(place_ids, scores):
                await pipe.setex(f"place_score:{pid}", 86400, str(score))
            await pipe.execute()
        logger.debug(f"Persisted {len(place_ids)} place scores")
    except Exception as e:
        logger.warning(f"Background score persist failed: {e}")


async def in_destination(state: GraphState) -> GraphState:
    """Phase 3 — in-destination nearby search and ranking."""
    messages = state.get("messages", [])
    latest_msg = last_user_content(messages) if messages else ""
    intent: TravelIntent = state.get("travel_intent") or TravelIntent()
    dest = state.get("destination", "")
    location = state.get("current_location", {})

    # Detect what the user wants
    query_type = _detect_query_type(latest_msg)
    logger.info(f"in_destination: dest={dest}, query_type={query_type}, location={bool(location)}")

    # Generate 4 Maps queries
    queries = await _build_query_set(dest, query_type, intent)

    # Fetch in parallel
    all_places = await _fetch_nearby_broad(queries, location)

    # Pre-scored cache lookup
    pre_scored = state.get("place_scores", {})

    # Build mappings with gap handling
    area_scores = _scoring_engine.score_area()
    mappings = _build_mappings(all_places, pre_scored)

    if not mappings:
        state["nearby_results"] = []
        state["ranked_places"] = []
        return state

    # Override with generic weights if "surprise me"
    ranked = _ranker.rank_places(mappings, intent if not state.get("is_generic_request") else TravelIntent(), area_scores)

    ranked_dicts = [
        {
            "name": rp.place.name,
            "rating": rp.place.rating,
            "final_score": rp.rank_score,
            "rank": rp.rank_position,
            "explanation": {
                "top_factor": rp.explanation.top_factor if rp.explanation else "",
                "weakest_factor": rp.explanation.weakest_factor if rp.explanation else "",
            },
        }
        for rp in ranked
    ]

    state["nearby_results"] = ranked_dicts
    state["ranked_places"] = ranked_dicts

    # Background persist
    asyncio.create_task(_persist_scores_bg(
        [rp.place.place_id for rp in ranked],
        [rp.rank_score for rp in ranked],
    ))

    logger.info(f"in_destination: {len(ranked_dicts)} places ranked")
    return state
