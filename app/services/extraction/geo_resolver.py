"""
Geo Resolver - Converts place names to geographic coordinates using geocoding APIs.
"""
import logging
import os
import aiohttp
from typing import Optional
from dataclasses import asdict

from app.models import ResolvedArea, GeoLocation, BoundingBox

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


class GeoResolver:
    """Resolves place names to geographic coordinates."""
    
    def __init__(self, google_api_key: Optional[str] = None):
        self.google_api_key = google_api_key or GOOGLE_API_KEY
        self._cache: dict[str, ResolvedArea] = {}
    
    async def resolve(
        self,
        phrase: str,
        context_city: Optional[str] = None,
        context_country: Optional[str] = None
    ) -> Optional[ResolvedArea]:
        """Resolve phrase to geographic area."""
        if not phrase:
            return None
        
        # Build cache key
        cache_key = f"{phrase}:{context_city}:{context_country}".lower()
        
        # Check cache first
        if cache_key in self._cache:
            logger.info(f"Cache hit for: {phrase}")
            return self._cache[cache_key]
        
        # Build scoped query
        query_parts = [phrase]
        if context_city:
            query_parts.append(context_city)
        if context_country:
            query_parts.append(context_country)
        query = ", ".join(query_parts)
        
        # Try Google Geocoding first
        result = await self._google_geocode(query)
        
        # Fallback to Nominatim
        if not result:
            logger.info(f"Google failed, trying Nominatim for: {query}")
            result = await self._nominatim_geocode(query)
        
        if result:
            self._cache[cache_key] = result
            
        return result
    
    async def resolve_batch(
        self,
        phrases: list[str],
        context_city: Optional[str] = None,
        context_country: Optional[str] = None
    ) -> list[Optional[ResolvedArea]]:
        """Resolve multiple phrases, deduplicating."""
        results = []
        seen = set()
        
        for phrase in phrases:
            if phrase.lower() in seen:
                continue
            seen.add(phrase.lower())
            result = await self.resolve(phrase, context_city, context_country)
            results.append(result)
        
        return results
    
    async def _google_geocode(self, query: str) -> Optional[ResolvedArea]:
        """Use Google Geocoding API."""
        if not self.google_api_key:
            logger.warning("Google API key not set")
            return None
        
        try:
            params = {
                "address": query,
                "key": self.google_api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(GOOGLE_GEOCODING_URL, params=params) as r:
                    data = await r.json()
            
            if data.get("status") != "OK" or not data.get("results"):
                return None
            
            result = data["results"][0]
            geometry = result["geometry"]
            location = geometry["location"]
            
            # Extract address components
            city = None
            country = None
            country_code = None
            
            for component in result.get("address_components", []):
                types = component.get("types", [])
                if "locality" in types:
                    city = component["long_name"]
                if "country" in types:
                    country = component["long_name"]
                    country_code = component["short_name"]
            
            # Calculate radius from viewport
            radius_km = 1.0
            if "viewport" in geometry:
                vp = geometry["viewport"]
                lat_diff = abs(vp["northeast"]["lat"] - vp["southwest"]["lat"])
                radius_km = max(lat_diff * 111 / 2, 0.5)  # 111km per degree lat
            
            # Build bounding box
            bounding_box = None
            if "viewport" in geometry:
                vp = geometry["viewport"]
                bounding_box = BoundingBox(
                    north=vp["northeast"]["lat"],
                    south=vp["southwest"]["lat"],
                    east=vp["northeast"]["lng"],
                    west=vp["southwest"]["lng"]
                )
            
            return ResolvedArea(
                area_id=f"{country_code or 'XX'}:{city or 'unknown'}:{query}".lower().replace(" ", "_"),
                canonical_name=result.get("formatted_address", query).split(",")[0],
                geo=GeoLocation(
                    lat=location["lat"],
                    lon=location["lng"],
                    radius_km=radius_km
                ),
                bounding_box=bounding_box,
                city=city,
                country=country,
                country_code=country_code,
                source="google_geocoding",
                confidence=0.9
            )
            
        except Exception as e:
            logger.error(f"Google geocoding error: {e}")
            return None
    
    async def _nominatim_geocode(self, query: str) -> Optional[ResolvedArea]:
        """Use Nominatim (OpenStreetMap) as fallback."""
        try:
            params = {
                "q": query,
                "format": "json",
                "limit": 1,
                "addressdetails": 1
            }
            headers = {
                "User-Agent": "RoamMate/1.0"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(NOMINATIM_URL, params=params, headers=headers) as r:
                    data = await r.json()
            
            if not data:
                return None
            
            result = data[0]
            address = result.get("address", {})
            
            # Extract city and country
            city = (
                address.get("city") or 
                address.get("town") or 
                address.get("municipality")
            )
            country = address.get("country")
            country_code = address.get("country_code", "").upper()
            
            # Calculate radius from bounding box
            radius_km = 1.0
            if "boundingbox" in result:
                bb = result["boundingbox"]
                lat_diff = abs(float(bb[1]) - float(bb[0]))
                radius_km = max(lat_diff * 111 / 2, 0.5)
            
            return ResolvedArea(
                area_id=f"{country_code or 'XX'}:{city or 'unknown'}:{query}".lower().replace(" ", "_"),
                canonical_name=result.get("display_name", query).split(",")[0],
                geo=GeoLocation(
                    lat=float(result["lat"]),
                    lon=float(result["lon"]),
                    radius_km=radius_km
                ),
                city=city,
                country=country,
                country_code=country_code,
                source="nominatim",
                confidence=0.7  # Lower confidence for fallback
            )
            
        except Exception as e:
            logger.error(f"Nominatim geocoding error: {e}")
            return None
    
    def add_to_cache(self, area: ResolvedArea) -> None:
        """Manually add an area to cache."""
        cache_key = f"{area.canonical_name}:{area.city}:{area.country}".lower()
        self._cache[cache_key] = area
