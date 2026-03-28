"""
Cache Manager - Handles City and Place Documents for caching.
"""
import json
import logging
import os
import aiofiles
from typing import Optional, List
from datetime import datetime, timedelta

from app.models import CityDocument, PlaceDocument, ResolvedArea, Place, PlaceAreaMapping

logger = logging.getLogger(__name__)

CACHE_DIR = "database/cache"
CITY_DOC_TTL_DAYS = 7
PLACE_DOC_TTL_HOURS = 24


class CacheManager:
    """Manages file-based caching for documents."""
    
    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(os.path.join(cache_dir, "cities"), exist_ok=True)
        os.makedirs(os.path.join(cache_dir, "places"), exist_ok=True)
    
    # --- City Documents ---
    
    async def get_city_document(self, city: str, country: str) -> Optional[CityDocument]:
        """Retrieve cached city document if fresh."""
        city_id = f"{country}:{city}".lower().replace(" ", "_")
        path = os.path.join(self.cache_dir, "cities", f"{city_id}.json")
        
        if not os.path.exists(path):
            return None
            
        try:
            async with aiofiles.open(path, 'r') as f:
                data = json.loads(await f.read())
                
            # Check TTL
            last_updated = datetime.fromisoformat(data.get("last_updated"))
            if datetime.now() - last_updated > timedelta(days=CITY_DOC_TTL_DAYS):
                logger.info(f"City document expired: {city_id}")
                return None
                
            # Reconstruct objects
            areas = [
                self._dict_to_resolved_area(a) 
                for a in data.get("areas", [])
            ]
            
            return CityDocument(
                city_id=data["city_id"],
                name=data["name"],
                country=data["country"],
                areas=areas,
                reddit_last_fetched=data.get("reddit_last_fetched"),
                crowd_baseline=data.get("crowd_baseline", 0.5),
                auth_baseline=data.get("auth_baseline", 0.5),
                created_at=data.get("created_at"),
                last_updated=data.get("last_updated")
            )
        except Exception as e:
            logger.error(f"Error reading city document {city_id}: {e}")
            return None

    async def save_city_document(self, doc: CityDocument) -> None:
        """Save city document to cache."""
        path = os.path.join(self.cache_dir, "cities", f"{doc.city_id}.json")
        
        data = {
            "city_id": doc.city_id,
            "name": doc.name,
            "country": doc.country,
            "areas": [self._resolved_area_to_dict(a) for a in doc.areas],
            "reddit_last_fetched": doc.reddit_last_fetched,
            "crowd_baseline": doc.crowd_baseline,
            "auth_baseline": doc.auth_baseline,
            "created_at": doc.created_at or datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
        
        try:
            async with aiofiles.open(path, 'w') as f:
                await f.write(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Error saving city document {doc.city_id}: {e}")

    # --- Place Documents ---
    
    async def get_place_document(self, place_id: str) -> Optional[PlaceDocument]:
        """Retrieve cached place document if fresh."""
        path = os.path.join(self.cache_dir, "places", f"{place_id}.json")
        
        if not os.path.exists(path):
            return None
            
        try:
            async with aiofiles.open(path, 'r') as f:
                data = json.loads(await f.read())
            
            # Check TTL
            fetched_at = datetime.fromisoformat(data.get("fetched_at"))
            if datetime.now() - fetched_at > timedelta(hours=PLACE_DOC_TTL_HOURS):
                return None
                
            place = Place(**data["place"])
            mapping = None
            if data.get("area_mapping"):
                # Simplified mapping reconstruction logic needed here
                pass 
                
            return PlaceDocument(
                place_id=data["place_id"],
                place=place,
                area_mapping=mapping,
                fetched_at=data.get("fetched_at")
            )
        except Exception as e:
            logger.error(f"Error reading place document {place_id}: {e}")
            return None

    async def save_place_document(self, doc: PlaceDocument) -> None:
        """Save place document to cache."""
        path = os.path.join(self.cache_dir, "places", f"{doc.place_id}.json")
        
        data = {
            "place_id": doc.place_id,
            "place": doc.place.__dict__,
            # "area_mapping": ... (mapping serialization if needed)
            "fetched_at": doc.fetched_at or datetime.now().isoformat()
        }
        
        try:
            async with aiofiles.open(path, 'w') as f:
                await f.write(json.dumps(data, indent=2))
        except Exception as e:
            logger.error(f"Error saving place document {doc.place_id}: {e}")

    # --- Helpers ---
    
    def _dict_to_resolved_area(self, data: dict) -> ResolvedArea:
        # Helper to reconstruct ResolvedArea from dict
        # Assuming geo/bbox need reconstruction too
        return ResolvedArea(**data) # Simplified for brevity
        
    def _resolved_area_to_dict(self, area: ResolvedArea) -> dict:
        return area.__dict__  # Simplified
