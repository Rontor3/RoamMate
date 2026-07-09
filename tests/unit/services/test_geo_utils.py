"""Unit tests for geo_utils."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── get_origin ────────────────────────────────────────────────────────────────

def test_get_origin_prefers_gps():
    from app.services.geo_utils import get_origin
    state = {
        "current_location": {"lat": 19.076, "lng": 72.877, "label": "Mumbai"},
        "travel_intent": None,
    }
    result = get_origin(state)
    assert result == {"lat": 19.076, "lng": 72.877, "name": "Mumbai"}


def test_get_origin_falls_back_to_intent():
    from app.services.geo_utils import get_origin
    intent = MagicMock()
    intent.origin_city = "Pune"
    state = {"current_location": None, "travel_intent": intent}
    result = get_origin(state)
    assert result == {"name": "Pune"}


def test_get_origin_returns_none_when_neither():
    from app.services.geo_utils import get_origin
    assert get_origin({}) is None


# ── geocode ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_geocode_returns_lat_lng():
    mock_response = MagicMock()
    mock_response.json = AsyncMock(return_value=[{"lat": "18.5204", "lon": "73.8567"}])
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from app.services.geo_utils import geocode
        result = await geocode("Pune")
    assert result == {"lat": 18.5204, "lng": 73.8567}


@pytest.mark.asyncio
async def test_geocode_returns_none_on_empty_response():
    mock_response = MagicMock()
    mock_response.json = AsyncMock(return_value=[])
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from app.services.geo_utils import geocode
        result = await geocode("NonexistentPlace")
    assert result is None


# ── driving_time ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_driving_time_returns_dict():
    mock_response = MagicMock()
    mock_response.json = AsyncMock(return_value={
        "code": "Ok",
        "routes": [{"distance": 263000, "duration": 19800}]
    })
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from app.services.geo_utils import driving_time
        result = await driving_time(
            {"lat": 19.076, "lng": 72.877},
            {"lat": 17.685, "lng": 73.609},
        )
    assert result["distance_km"] == 263
    assert result["duration_mins"] == 330
    assert result["travel_time"] == "5h 30min"


@pytest.mark.asyncio
async def test_driving_time_returns_none_on_failure():
    with patch("aiohttp.ClientSession", side_effect=Exception("timeout")):
        from app.services.geo_utils import driving_time
        result = await driving_time({"lat": 0, "lng": 0}, {"lat": 1, "lng": 1})
    assert result is None


@pytest.mark.asyncio
async def test_driving_time_returns_none_when_osrm_not_ok():
    mock_response = MagicMock()
    mock_response.json = AsyncMock(return_value={"code": "NoRoute", "routes": []})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        from app.services.geo_utils import driving_time
        result = await driving_time({"lat": 0, "lng": 0}, {"lat": 1, "lng": 1})
    assert result is None


# ── resolve_origin_coords ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_origin_coords_returns_gps_directly():
    from app.services.geo_utils import resolve_origin_coords
    state = {"current_location": {"lat": 19.076, "lng": 72.877, "label": "Mumbai"}}
    result = await resolve_origin_coords(state)
    assert result["lat"] == 19.076
    assert result["lng"] == 72.877


@pytest.mark.asyncio
async def test_resolve_origin_coords_geocodes_city_name():
    from app.services import geo_utils
    with patch.object(geo_utils, "geocode", new=AsyncMock(return_value={"lat": 18.52, "lng": 73.85})):
        intent = MagicMock()
        intent.origin_city = "Pune"
        state = {"current_location": None, "travel_intent": intent}
        result = await geo_utils.resolve_origin_coords(state)
    assert result["lat"] == 18.52
    assert result["name"] == "Pune"


@pytest.mark.asyncio
async def test_resolve_origin_coords_returns_none_when_no_origin():
    from app.services.geo_utils import resolve_origin_coords
    assert await resolve_origin_coords({}) is None
