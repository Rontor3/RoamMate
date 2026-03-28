"""Integration test — Full graph invocation with mocked MCP tools and Groq."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_full_graph_discovery_phase():
    """Smoke test: Phase 1 discovery completes and returns a response."""
    # This test requires the graph to be compiled; skip in CI without full env
    pytest.skip("Requires full env (Groq API key, SQLite checkpoint)")


@pytest.mark.asyncio
async def test_full_graph_planning_phase():
    """Smoke test: Phase 2 planning with mocked Reddit + Maps."""
    pytest.skip("Requires full env")


@pytest.mark.asyncio
async def test_full_graph_in_destination():
    """Smoke test: Phase 3 with GPS location injected."""
    pytest.skip("Requires full env")
