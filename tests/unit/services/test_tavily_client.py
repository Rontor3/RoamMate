"""Unit tests for tavily_client."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_tavily_search_returns_results():
    mock_response = MagicMock()
    mock_response.json = AsyncMock(return_value={"results": [{"title": "Goa", "content": "beach"}]})
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.tavily_client.TAVILY_API_KEY", "fake-key"), \
         patch("aiohttp.ClientSession", return_value=mock_session):
        from app.services.tavily_client import tavily_search
        results = await tavily_search("weekend trips from Mumbai")
    assert results == [{"title": "Goa", "content": "beach"}]


@pytest.mark.asyncio
async def test_tavily_search_returns_empty_when_no_key():
    with patch("app.services.tavily_client.TAVILY_API_KEY", ""):
        from app.services import tavily_client
        import importlib
        importlib.reload(tavily_client)
        results = await tavily_client.tavily_search("anything")
    assert results == []


@pytest.mark.asyncio
async def test_tavily_search_returns_empty_on_exception():
    with patch("app.services.tavily_client.TAVILY_API_KEY", "fake-key"), \
         patch("aiohttp.ClientSession", side_effect=Exception("network error")):
        from app.services.tavily_client import tavily_search
        results = await tavily_search("test query")
    assert results == []
