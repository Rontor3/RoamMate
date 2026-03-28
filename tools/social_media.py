"""
tools/social_media.py — MCP tool server for Tavily blog and events search.
NOTE: Reddit has been moved to app/services/reddit_signals.py (direct asyncpraw).
This server now handles Tavily blogs + events only.
"""
import logging
import os

import aiohttp
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"

mcp = FastMCP("SocialTools")


@mcp.tool(
    name="search_travel_blogs",
    description="Search travel blogs and editorial sources for destination guides using Tavily."
)
async def search_travel_blogs(destination: str, vibe: str = "", max_results: int = 5) -> dict:
    """Search Tavily for editorial blog content about a destination."""
    if not TAVILY_API_KEY:
        return {"error": "TAVILY_API_KEY not set", "sources": []}

    query = f"best things to do in {destination} travel guide {vibe}".strip()
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(TAVILY_URL, json=payload) as r:
                data = await r.json()
                results = data.get("results", [])
                return {
                    "query": query,
                    "sources": [
                        {
                            "url": r.get("url", ""),
                            "title": r.get("title", ""),
                            "snippet": r.get("content", "")[:400],
                            "score": r.get("score", 0.0),
                        }
                        for r in results
                    ],
                }
    except Exception as e:
        logger.error(f"Tavily blog search failed: {e}")
        return {"error": str(e), "sources": []}


@mcp.tool(
    name="search_local_events",
    description="Search for current events, festivals and activities happening at a destination."
)
async def search_local_events(destination: str, max_results: int = 4) -> dict:
    """Search Tavily for events and activities at a destination."""
    if not TAVILY_API_KEY:
        return {"error": "TAVILY_API_KEY not set", "events": []}

    query = f"events and activities happening in {destination} this month"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "include_answer": False,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(TAVILY_URL, json=payload) as r:
                data = await r.json()
                results = data.get("results", [])
                return {
                    "destination": destination,
                    "events": [
                        {
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": r.get("content", "")[:300],
                        }
                        for r in results
                    ],
                }
    except Exception as e:
        logger.error(f"Tavily events search failed: {e}")
        return {"error": str(e), "events": []}


if __name__ == "__main__":
    mcp.run(transport="sse", port=3003)
