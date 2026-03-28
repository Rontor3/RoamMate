"""
app/tools/fetchers/places.py — Place search fetcher via Google Maps MCP.
Used by planning.py and in_destination.py nodes.
"""
from typing import Any, Dict, List, Optional

from app.tools.registry import call_tool
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def search_places(destination: str, query: str = "") -> List[Dict[str, Any]]:
    """Search for top places at a destination."""
    args = {
        "location": destination,
        "query": query or f"top attractions in {destination}",
    }
    result = await call_tool("google_maps", "search_places", args)
    return result.get("places", []) if isinstance(result, dict) else []


async def nearby_search(lat: float, lng: float, query: str, radius_m: int = 2000) -> List[Dict[str, Any]]:
    """Nearby search using GPS coordinates."""
    args = {"lat": lat, "lng": lng, "query": query, "radius": radius_m}
    result = await call_tool("google_maps", "nearby_search", args)
    return result.get("places", []) if isinstance(result, dict) else []
