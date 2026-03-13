"""
Area Mapper - Maps places to areas using distance-based assignment.
"""
import math
import logging
from typing import Optional

from app.models import Place, ResolvedArea, PlaceAreaMapping, AreaScores, GeoLocation

logger = logging.getLogger(__name__)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in kilometers."""
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


class AreaMapper:
    """Maps places to geographic areas."""
    
    def __init__(self, areas: Optional[list[ResolvedArea]] = None):
        self.areas = areas or []
    
    def set_areas(self, areas: list[ResolvedArea]) -> None:
        """Set the list of known areas."""
        self.areas = areas
    
    def map_place(
        self,
        place: Place,
        area_scores: Optional[dict[str, AreaScores]] = None
    ) -> PlaceAreaMapping:
        """Map a single place to its area context."""
        if not self.areas:
            return PlaceAreaMapping(place=place)
        
        # Find all matching areas
        matches = []
        for area in self.areas:
            if not area.geo:
                continue
            
            distance = haversine_distance(
                place.lat, place.lon,
                area.geo.lat, area.geo.lon
            )
            
            # Check if within area radius (with 20% buffer)
            if distance <= area.geo.radius_km * 1.2:
                matches.append((area, distance))
        
        if not matches:
            # No match - expand search or use fallback
            return self._fallback_mapping(place)
        
        # Resolve overlaps
        primary_area, min_distance = self._resolve_overlap(matches)
        
        # Get inherited priors
        inherited = None
        if area_scores and primary_area.area_id in area_scores:
            inherited = area_scores[primary_area.area_id]
        
        return PlaceAreaMapping(
            place=place,
            primary_area=primary_area,
            distance_km=round(min_distance, 2),
            inherited_priors=inherited
        )
    
    def map_batch(
        self,
        places: list[Place],
        area_scores: Optional[dict[str, AreaScores]] = None
    ) -> list[PlaceAreaMapping]:
        """Map multiple places efficiently."""
        return [self.map_place(place, area_scores) for place in places]
    
    def _resolve_overlap(
        self,
        matches: list[tuple[ResolvedArea, float]]
    ) -> tuple[ResolvedArea, float]:
        """Resolve overlapping areas - pick most specific or nearest."""
        if len(matches) == 1:
            return matches[0]
        
        # Sort by specificity (smaller radius = more specific) then distance
        matches.sort(key=lambda x: (x[0].geo.radius_km, x[1]))
        
        # Check if areas are hierarchical
        smallest = matches[0]
        for area, dist in matches[1:]:
            # If smallest is contained in larger, prefer smallest
            if smallest[0].geo.radius_km < area.geo.radius_km:
                continue
        
        return smallest
    
    def _fallback_mapping(self, place: Place) -> PlaceAreaMapping:
        """Handle places not in any known area."""
        # Find nearest area even if outside radius
        if not self.areas:
            return PlaceAreaMapping(place=place)
        
        nearest = None
        min_dist = float('inf')
        
        for area in self.areas:
            if not area.geo:
                continue
            dist = haversine_distance(
                place.lat, place.lon,
                area.geo.lat, area.geo.lon
            )
            if dist < min_dist:
                min_dist = dist
                nearest = area
        
        if nearest and min_dist <= nearest.geo.radius_km * 1.5:
            logger.info(f"Place {place.name} mapped to edge of {nearest.canonical_name}")
            return PlaceAreaMapping(
                place=place,
                primary_area=nearest,
                distance_km=round(min_dist, 2)
            )
        
        return PlaceAreaMapping(place=place)
    
    def get_prior_weight(self, mapping: PlaceAreaMapping) -> float:
        """Calculate prior weight based on distance from area center."""
        if not mapping.primary_area or not mapping.primary_area.geo:
            return 0.0
        
        radius = mapping.primary_area.geo.radius_km
        distance = mapping.distance_km
        confidence = mapping.primary_area.confidence
        
        # Weight decreases with distance from center
        # prior_weight = 0.3 × (1 - distance/radius) × area_confidence
        distance_factor = max(0, 1 - distance / radius)
        return 0.3 * distance_factor * confidence
