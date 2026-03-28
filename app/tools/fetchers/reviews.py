"""
app/tools/fetchers/reviews.py — Google Place Reviews fetcher via Maps MCP.
"""
from typing import Any, Dict, List

from app.tools.registry import call_tool
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def get_place_reviews(place_id: str, max_reviews: int = 5) -> List[Dict[str, Any]]:
    """Fetch reviews for a specific place."""
    result = await call_tool("google_maps", "get_place_reviews", {
        "place_id": place_id,
        "max_reviews": max_reviews,
    })
    return result.get("reviews", []) if isinstance(result, dict) else []


async def get_place_details(place_id: str) -> Dict[str, Any]:
    """Get full place details including reviews, hours, and photos."""
    result = await call_tool("google_maps", "get_place_details", {"place_id": place_id})
    return result or {}
