"""
app/tools/fetchers/blogs.py — Tavily MCP fetcher for blog and event content.
"""
from typing import Any, Dict, List

from app.tools.registry import call_tool
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def search_travel_blogs(destination: str, vibe: str = "", max_results: int = 5) -> List[Dict[str, Any]]:
    """Search for editorial travel blog content about a destination."""
    result = await call_tool("tavily", "search_travel_blogs", {
        "destination": destination,
        "vibe": vibe,
        "max_results": max_results,
    })
    return result.get("sources", []) if isinstance(result, dict) else []


async def search_local_events(destination: str, max_results: int = 4) -> List[Dict[str, Any]]:
    """Search for events and activities currently happening at a destination."""
    result = await call_tool("tavily", "search_local_events", {
        "destination": destination,
        "max_results": max_results,
    })
    return result.get("events", []) if isinstance(result, dict) else []
