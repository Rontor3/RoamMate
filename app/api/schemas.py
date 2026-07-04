"""
app/api/schemas.py — Pydantic request/response schemas for the API layer.
"""
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel


class LocationPayload(BaseModel):
    lat: float
    lng: float
    accuracy: Optional[float] = None
    label: Optional[str] = None
    source: Literal["gps", "manual", "maps_link"] = "gps"


class ChatRequest(BaseModel):
    message: str
    thread_id: str
    location: Optional[LocationPayload] = None
    card_action: Optional[str] = None
    card_data: Optional[Dict[str, Any]] = None
    # Phase 0 structured fields — sent by frontend on first message
    trip_mode: str | None = None      # "plan" | "now"
    trip_who: str | None = None       # "solo" | "couple" | "friends" | "family_kids" | "family_elder"
    trip_season: str | None = None    # "summer" | "monsoon" | "winter" | "flex"


class ReverseGeocodeRequest(BaseModel):
    lat: float
    lng: float


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    phase: Optional[str] = None
    photos: list[dict] = []   # [{name, url}, ...] — Google Place photos for mentioned places
    hotels: list[dict] = []   # structured hotel data from Booking.com
    places: list[dict] = []   # structured place data for PlaceCard components
    action: Optional[str] = None       # card UI action for frontend
    payload: Optional[Dict[str, Any]] = None  # data for the card UI
