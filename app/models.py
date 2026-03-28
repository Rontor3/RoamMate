"""
Data models for the RoamMate recommendation system.
"""
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


# ============== Enums ==============

class Vibe(str, Enum):
    CHILL = "chill"
    PARTY = "party"
    ADVENTURE = "adventure"
    CULTURAL = "cultural"
    ROMANTIC = "romantic"
    FAMILY = "family"


class CrowdPreference(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Duration(str, Enum):
    DAY = "day"
    WEEKEND = "weekend"
    WEEK = "week"
    EXTENDED = "extended"


class Budget(str, Enum):
    BUDGET = "budget"
    MID = "mid"
    LUXURY = "luxury"


class AreaType(str, Enum):
    NEIGHBORHOOD = "neighborhood"
    DISTRICT = "district"
    LANDMARK_AREA = "landmark_area"
    VAGUE = "vague"


class AirportType(str, Enum):
    LARGE = "large_airport"
    MEDIUM = "medium_airport"
    SMALL = "small_airport"


# ============== Intent Models ==============

@dataclass
class Destination:
    city: Optional[str] = None
    country: Optional[str] = None
    area: Optional[str] = None
    region: Optional[str] = None  # e.g. "North East India", "Scottish Highlands"


@dataclass
class IntentConfidence:
    overall: float = 0.0
    ambiguous_fields: list[str] = field(default_factory=list)


@dataclass
class TravelIntent:
    destination: Destination = field(default_factory=Destination)
    vibe: list[Vibe] = field(default_factory=list)
    crowd_preference: Optional[CrowdPreference] = None
    duration: Optional[Duration] = None
    needs_flight: Optional[bool] = None
    needs_hotel: Optional[bool] = None
    interests: list[str] = field(default_factory=list)
    budget: Optional[Budget] = None
    confidence: IntentConfidence = field(default_factory=IntentConfidence)


# ============== Geo Models ==============

@dataclass
class GeoLocation:
    lat: float
    lon: float
    radius_km: float = 1.0


@dataclass
class BoundingBox:
    north: float
    south: float
    east: float
    west: float


@dataclass
class ResolvedArea:
    area_id: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    geo: Optional[GeoLocation] = None
    bounding_box: Optional[BoundingBox] = None
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    source: str = "unknown"
    confidence: float = 0.0


# ============== Area Phrase Models ==============

@dataclass
class AreaPhrase:
    phrase: str
    context: str
    phrase_type: AreaType
    confidence: float


@dataclass
class AreaExtractionResult:
    area_phrases: list[AreaPhrase] = field(default_factory=list)
    source_length: int = 0
    phrases_found: int = 0
    had_ambiguity: bool = False


# ============== Place Models ==============

@dataclass
class Place:
    place_id: str
    name: str
    place_type: str  # cafe, hotel, restaurant, etc.
    lat: float
    lon: float
    rating: Optional[float] = None
    review_count: int = 0
    price_level: Optional[int] = None
    tags: list[str] = field(default_factory=list)
    source: str = "google"


@dataclass
class PlaceAreaMapping:
    place: Place
    primary_area: Optional[ResolvedArea] = None
    distance_km: float = 0.0
    inherited_priors: Optional["AreaScores"] = None


# ============== Score Models ==============

@dataclass
class ScoreResult:
    value: float
    confidence: float
    signals_used: list[str] = field(default_factory=list)
    fallback_used: bool = False


@dataclass
class AreaScores:
    crowd_score: Optional[ScoreResult] = None
    authenticity_score: Optional[ScoreResult] = None


@dataclass
class RankExplanation:
    quality: dict = field(default_factory=dict)
    crowd_fit: dict = field(default_factory=dict)
    authenticity: dict = field(default_factory=dict)
    intent_match: dict = field(default_factory=dict)
    top_factor: str = ""
    weakest_factor: str = ""


@dataclass
class RankedPlace:
    place: Place
    rank_score: float
    rank_position: int
    area: Optional[ResolvedArea] = None
    explanation: Optional[RankExplanation] = None
    confidence: float = 0.0


# ============== Airport Models ==============

@dataclass
class Airport:
    iata_code: str
    name: str
    airport_type: AirportType
    lat: float
    lon: float
    municipality: str
    country: str
    distance_km: float = 0.0


@dataclass
class AirportResult:
    destination_lat: float
    destination_lon: float
    nearest_airports: list[Airport] = field(default_factory=list)
    primary_airport: Optional[str] = None


# ============== Cache Document Models ==============

@dataclass
class CityDocument:
    city_id: str
    name: str
    country: str
    areas: list[ResolvedArea] = field(default_factory=list)
    reddit_last_fetched: Optional[str] = None
    crowd_baseline: float = 0.5
    auth_baseline: float = 0.5
    created_at: Optional[str] = None
    last_updated: Optional[str] = None


@dataclass
class PlaceDocument:
    place_id: str
    place: Place
    area_mapping: Optional[PlaceAreaMapping] = None
    fetched_at: Optional[str] = None
