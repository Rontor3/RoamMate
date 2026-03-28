"""
app/api/schemas.py — Pydantic request/response schemas for the API layer.
"""
from typing import Literal, Optional

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


class ReverseGeocodeRequest(BaseModel):
    lat: float
    lng: float


class ChatResponse(BaseModel):
    response: str
    thread_id: str
    phase: Optional[str] = None
