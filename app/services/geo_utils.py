"""
app/services/geo_utils.py — Geographic utilities for Sprint 2.

get_origin: resolve origin coordinates or name from GraphState
geocode: Nominatim city name → {lat, lng}
driving_time: OSRM road routing between two coordinate pairs
batch_driving_times: parallel OSRM calls for multiple destinations
resolve_origin_coords: get_origin + geocode if only name available
"""
import asyncio
import aiohttp

from app.utils.logger import get_logger

logger = get_logger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "http://router.project-osrm.org/route/v1/driving"
_HEADERS = {"User-Agent": "RoamMate/1.0 travel-assistant-app"}


def get_origin(state: dict) -> dict | None:
    """
    Resolve origin from state.
    Returns {"lat", "lng", "name"} if GPS available,
    {"name"} if only city name known, or None.
    """
    loc = state.get("current_location")
    if loc and loc.get("lat") and loc.get("lng"):
        return {"lat": float(loc["lat"]), "lng": float(loc["lng"]), "name": loc.get("label", "")}
    intent = state.get("travel_intent")
    if intent:
        origin_city = getattr(intent, "origin_city", None) or (
            intent.get("origin_city") if isinstance(intent, dict) else None
        )
        if origin_city:
            return {"name": origin_city}
    return None


async def geocode(place_name: str) -> dict | None:
    """
    Nominatim: city name → {lat, lng}.
    Appends ", India" to bias results. Returns None on any failure.
    """
    params = {"q": f"{place_name}, India", "format": "json", "limit": 1}
    try:
        async with aiohttp.ClientSession(headers=_HEADERS) as session:
            async with session.get(
                NOMINATIM_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                results = await r.json()
                if results:
                    return {"lat": float(results[0]["lat"]), "lng": float(results[0]["lon"])}
    except Exception as e:
        logger.warning(f"[Nominatim] geocode failed for '{place_name}': {e}")
    return None


async def driving_time(origin: dict, destination: dict) -> dict | None:
    """
    OSRM: actual road driving time + distance between two {lat, lng} dicts.
    OSRM takes coordinates as lng,lat (longitude first).
    Returns {distance_km, duration_mins, travel_time} or None on failure.
    """
    url = (
        f"{OSRM_URL}/"
        f"{origin['lng']},{origin['lat']};"
        f"{destination['lng']},{destination['lat']}"
        "?overview=false"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                data = await r.json()
                if data.get("code") == "Ok" and data.get("routes"):
                    route = data["routes"][0]
                    distance_km = round(route["distance"] / 1000)
                    duration_mins = round(route["duration"] / 60)
                    hours = duration_mins // 60
                    mins = duration_mins % 60
                    travel_time = f"{hours}h {mins}min" if mins else f"{hours}h"
                    return {
                        "distance_km": distance_km,
                        "duration_mins": duration_mins,
                        "travel_time": travel_time,
                    }
    except Exception as e:
        logger.warning(f"[OSRM] routing failed: {e}")
    return None


async def batch_driving_times(
    origin: dict, destinations: list[dict]
) -> list[dict | None]:
    """Run driving_time for multiple destinations in parallel."""
    results = await asyncio.gather(
        *[driving_time(origin, d) for d in destinations],
        return_exceptions=True,
    )
    return [None if isinstance(r, BaseException) else r for r in results]


async def resolve_origin_coords(state: dict) -> dict | None:
    """
    Return origin with guaranteed {lat, lng, name}.
    Geocodes city name if lat/lng not already available.
    Returns None if origin cannot be resolved.
    """
    origin = get_origin(state)
    if origin is None:
        return None
    if "lat" in origin and "lng" in origin:
        return origin
    coords = await geocode(origin["name"])
    if coords:
        return {**origin, **coords}
    return None
