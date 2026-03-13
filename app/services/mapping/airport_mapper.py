"""
Airport Mapper - Finds nearest airports using world-airports.csv data.
"""
import csv
import logging
import math
from typing import Optional
from dataclasses import dataclass

from app.models import Airport, AirportResult, AirportType

logger = logging.getLogger(__name__)

# Default distance thresholds (km)
LARGE_AIRPORT_MAX_DISTANCE = 150
MEDIUM_AIRPORT_MAX_DISTANCE = 100
SMALL_AIRPORT_MAX_DISTANCE = 50


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in kilometers."""
    R = 6371  # Earth's radius in km
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


class AirportMapper:
    """Maps destinations to nearest airports using CSV data."""
    
    def __init__(self, csv_path: str):
        """Load and index world-airports.csv on init."""
        self.airports: list[dict] = []
        self._load_csv(csv_path)
        logger.info(f"Loaded {len(self.airports)} airports")
    
    def _load_csv(self, csv_path: str) -> None:
        """Load airports from CSV file."""
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Only include airports with valid coordinates and IATA code
                    try:
                        lat = float(row.get('latitude_deg', 0))
                        lon = float(row.get('longitude_deg', 0))
                        iata = row.get('iata_code', '').strip()
                        airport_type = row.get('type', '')
                        
                        # Skip if no coordinates or not a recognized airport type
                        if not lat or not lon:
                            continue
                        if airport_type not in ['large_airport', 'medium_airport', 'small_airport']:
                            continue
                        
                        self.airports.append({
                            'iata_code': iata or row.get('ident', ''),
                            'name': row.get('name', 'Unknown'),
                            'type': airport_type,
                            'lat': lat,
                            'lon': lon,
                            'municipality': row.get('municipality', ''),
                            'country': row.get('country_name', ''),
                            'country_code': row.get('iso_country', '')
                        })
                    except (ValueError, TypeError):
                        continue
                        
        except FileNotFoundError:
            logger.error(f"Airport CSV not found: {csv_path}")
        except Exception as e:
            logger.error(f"Error loading airport CSV: {e}")
    
    def find_nearest(
        self,
        lat: float,
        lon: float,
        max_results: int = 3,
        airport_types: Optional[list[str]] = None
    ) -> list[Airport]:
        """Find nearest airports to coordinates."""
        if airport_types is None:
            airport_types = ['large_airport', 'medium_airport']
        
        candidates = []
        
        for ap in self.airports:
            if ap['type'] not in airport_types:
                continue
            
            # Calculate distance
            distance = haversine_distance(lat, lon, ap['lat'], ap['lon'])
            
            # Check distance threshold based on type
            max_dist = self._get_max_distance(ap['type'])
            if distance > max_dist:
                continue
            
            # Map type to enum
            try:
                ap_type = AirportType(ap['type'])
            except ValueError:
                ap_type = AirportType.SMALL
            
            candidates.append(Airport(
                iata_code=ap['iata_code'],
                name=ap['name'],
                airport_type=ap_type,
                lat=ap['lat'],
                lon=ap['lon'],
                municipality=ap['municipality'],
                country=ap['country'],
                distance_km=round(distance, 1)
            ))
        
        # Sort by distance and return top N
        candidates.sort(key=lambda x: x.distance_km)
        return candidates[:max_results]
    
    def _get_max_distance(self, airport_type: str) -> float:
        """Get maximum search distance for airport type."""
        if airport_type == 'large_airport':
            return LARGE_AIRPORT_MAX_DISTANCE
        elif airport_type == 'medium_airport':
            return MEDIUM_AIRPORT_MAX_DISTANCE
        else:
            return SMALL_AIRPORT_MAX_DISTANCE
    
    def find_for_destination(
        self,
        lat: float,
        lon: float,
        max_results: int = 3
    ) -> AirportResult:
        """Find airports for a destination with fallback logic."""
        # Try large airports first
        airports = self.find_nearest(lat, lon, max_results, ['large_airport'])
        
        # If no large airports, try medium
        if not airports:
            airports = self.find_nearest(lat, lon, max_results, ['medium_airport'])
        
        # If still none, try small with expanded radius
        if not airports:
            airports = self.find_nearest(lat, lon, max_results, ['small_airport'])
        
        # If still none, expand search radius
        if not airports:
            airports = self._expanded_search(lat, lon, max_results)
        
        primary = airports[0].iata_code if airports else None
        
        return AirportResult(
            destination_lat=lat,
            destination_lon=lon,
            nearest_airports=airports,
            primary_airport=primary
        )
    
    def _expanded_search(self, lat: float, lon: float, max_results: int) -> list[Airport]:
        """Search with expanded radius (300km) for remote destinations."""
        candidates = []
        
        for ap in self.airports:
            distance = haversine_distance(lat, lon, ap['lat'], ap['lon'])
            
            # Expanded 300km radius
            if distance > 300:
                continue
            
            try:
                ap_type = AirportType(ap['type'])
            except ValueError:
                ap_type = AirportType.SMALL
            
            candidates.append(Airport(
                iata_code=ap['iata_code'],
                name=ap['name'],
                airport_type=ap_type,
                lat=ap['lat'],
                lon=ap['lon'],
                municipality=ap['municipality'],
                country=ap['country'],
                distance_km=round(distance, 1)
            ))
        
        candidates.sort(key=lambda x: (
            0 if x.airport_type == AirportType.LARGE else 
            1 if x.airport_type == AirportType.MEDIUM else 2,
            x.distance_km
        ))
        
        return candidates[:max_results]
    
    def get_for_city(self, city: str, country: str) -> list[Airport]:
        """Get airports by city name (for cached lookups)."""
        matches = []
        city_lower = city.lower()
        country_lower = country.lower()
        
        for ap in self.airports:
            if (ap['municipality'].lower() == city_lower and 
                ap['country'].lower() == country_lower):
                try:
                    ap_type = AirportType(ap['type'])
                except ValueError:
                    ap_type = AirportType.SMALL
                    
                matches.append(Airport(
                    iata_code=ap['iata_code'],
                    name=ap['name'],
                    airport_type=ap_type,
                    lat=ap['lat'],
                    lon=ap['lon'],
                    municipality=ap['municipality'],
                    country=ap['country'],
                    distance_km=0.0
                ))
        
        # Sort by airport type priority
        matches.sort(key=lambda x: (
            0 if x.airport_type == AirportType.LARGE else 
            1 if x.airport_type == AirportType.MEDIUM else 2
        ))
        
        return matches[:3]
