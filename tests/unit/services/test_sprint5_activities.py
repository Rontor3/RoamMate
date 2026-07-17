"""Sprint 5 — activity options tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.graph.state import GraphState


# ── Task 1: State fields ──────────────────────────────────────────────────────

def test_graphstate_has_pending_activities():
    state: GraphState = {}
    state["pending_activities"] = {"chapora_fort": ["Sunrise Trek", "Cliff Photography"]}
    assert state["pending_activities"]["chapora_fort"] == ["Sunrise Trek", "Cliff Photography"]


def test_graphstate_pending_activities_defaults_to_none():
    state: GraphState = {}
    assert state.get("pending_activities") is None


def test_graphstate_has_activity_options():
    state: GraphState = {}
    state["activity_options"] = [{"id": "sunrise_trek", "label": "Sunrise Trek", "duration": "2h", "time": "morning", "vibe": "adventure"}]
    assert state["activity_options"][0]["id"] == "sunrise_trek"


def test_graphstate_activity_options_defaults_to_none():
    state: GraphState = {}
    assert state.get("activity_options") is None


# ── Task 1: Responder persistence ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_responder_persists_pending_activities():
    from app.graph.nodes.responder import responder
    state: GraphState = {
        "destination": "Goa",
        "messages": [{"role": "user", "content": "hi"}],
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
    }
    with patch("app.graph.nodes.responder._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.responder.aiohttp.ClientSession") as mock_session:
        mock_action.return_value = (None, None)
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"choices": [{"message": {"content": "Nice!"}}]})
        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=MagicMock(return_value=mock_post)))
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await responder(state)
    assert result["pending_activities"] == {"chapora_fort": ["Sunrise Trek"]}


@pytest.mark.asyncio
async def test_responder_persists_activity_options():
    from app.graph.nodes.responder import responder
    opts = [{"id": "sunrise_trek", "label": "Sunrise Trek", "duration": "2h", "time": "morning", "vibe": "adventure"}]
    state: GraphState = {
        "destination": "Goa",
        "messages": [{"role": "user", "content": "hi"}],
        "activity_options": opts,
    }
    with patch("app.graph.nodes.responder._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.responder.aiohttp.ClientSession") as mock_session:
        mock_action.return_value = (None, None)
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"choices": [{"message": {"content": "Nice!"}}]})
        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=MagicMock(return_value=mock_post)))
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await responder(state)
    assert result["activity_options"] == opts


@pytest.mark.asyncio
async def test_responder_defaults_pending_activities_to_empty_dict():
    from app.graph.nodes.responder import responder
    state: GraphState = {
        "destination": "Goa",
        "messages": [{"role": "user", "content": "hi"}],
    }
    with patch("app.graph.nodes.responder._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.responder.aiohttp.ClientSession") as mock_session:
        mock_action.return_value = (None, None)
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"choices": [{"message": {"content": "Nice!"}}]})
        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=MagicMock(return_value=mock_post)))
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await responder(state)
    assert result["pending_activities"] == {}
    assert result["activity_options"] == []
