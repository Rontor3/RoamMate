"""
app/services/tavily_client.py — Shared Tavily search client.

Used by blog_signals.py and stage_machine.py.
"""
import aiohttp
import os
from typing import Any

from app.utils.logger import get_logger

logger = get_logger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"


async def tavily_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """Call Tavily search API and return raw results. Returns [] on any failure."""
    if not TAVILY_API_KEY:
        logger.warning("[Tavily] TAVILY_API_KEY not set — skipping")
        return []
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
    }
    logger.info(f"[Tavily] → '{query}'")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(TAVILY_URL, json=payload) as r:
                data = await r.json()
                results = data.get("results", [])
                logger.info(f"[Tavily] ✓ '{query}' → {len(results)} results")
                return results
    except Exception as e:
        logger.error(f"[Tavily] ✗ '{query}': {e}")
        return []
