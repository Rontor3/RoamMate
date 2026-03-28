"""
app/tools/fetchers/geocode.py — Geocoding and distance matrix fetcher via Google Maps MCP.
"""
from typing import Any, Dict, List, Optional

from app.tools.registry import call_tool
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def geocode(place: str) -> Dict[str, Any]:
    """Geocode a place string to lat/lng."""
    result = await call_tool("google_maps", "geocode", {"address": place})
    return result or {}


async def reverse_geocode(lat: float, lng: float) -> str:
    """Convert lat/lng to a human-readable address."""
    result = await call_tool("google_maps", "reverse_geocode", {"lat": lat, "lng": lng})
    return result.get("formatted_address", f"{lat:.4f},{lng:.4f}") if isinstance(result, dict) else ""


async def distance_matrix(origin: str, destinations: List[str]) -> Dict[str, Any]:
    """Get travel distances from origin to a list of destinations."""
    args = {"origin": origin, "destinations": destinations}
    result = await call_tool("google_maps", "distance_matrix", args)
    return result or {}
