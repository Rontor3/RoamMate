"""
app/tools/fetchers/hotels_flights.py — Hotel and flight search fetcher via Booking MCP.
"""
from typing import Any, Dict, List, Optional

from app.tools.registry import call_tool
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def search_hotels(
    destination: str,
    check_in: Optional[str] = None,
    check_out: Optional[str] = None,
    guests: int = 2,
) -> List[Dict[str, Any]]:
    """Search for hotels at a destination."""
    args: Dict[str, Any] = {"destination": destination, "guests": guests}
    if check_in:
        args["check_in"] = check_in
    if check_out:
        args["check_out"] = check_out
    result = await call_tool("booking", "search_hotels", args)
    return result.get("hotels", []) if isinstance(result, dict) else []


async def search_flights(
    origin: str,
    destination: str,
    departure_date: Optional[str] = None,
    passengers: int = 1,
) -> List[Dict[str, Any]]:
    """Search for flights between two cities."""
    args: Dict[str, Any] = {"origin": origin, "destination": destination, "passengers": passengers}
    if departure_date:
        args["departure_date"] = departure_date
    result = await call_tool("booking", "search_flights", args)
    return result.get("flights", []) if isinstance(result, dict) else []


async def get_hotel_details(hotel_id: str) -> Dict[str, Any]:
    """Get details for a specific hotel."""
    result = await call_tool("booking", "get_hotel_details", {"hotel_id": hotel_id})
    return result or {}
