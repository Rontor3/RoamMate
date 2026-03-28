"""
app/tools/fetchers/weather.py — OpenWeatherMap MCP fetcher.
"""
from typing import Any, Dict, Optional

from app.tools.registry import call_tool
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def get_current_weather(location: str) -> Dict[str, Any]:
    """Get current weather for a city/location name."""
    result = await call_tool("openweather", "get_current_weather", {"location": location})
    return result or {}


async def get_weather_by_coords(lat: float, lng: float) -> Dict[str, Any]:
    """Get current weather using GPS coordinates."""
    result = await call_tool("openweather", "get_current_weather", {"lat": lat, "lng": lng})
    return result or {}


async def get_forecast(location: str, days: int = 5) -> Dict[str, Any]:
    """Get multi-day weather forecast."""
    result = await call_tool("openweather", "get_forecast", {"location": location, "days": days})
    return result or {}
