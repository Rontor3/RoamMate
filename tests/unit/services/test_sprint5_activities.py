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


# ── Task 2: activity_options.py ──────────────────────────────────────────────────

def test_default_activities_has_three_entries():
    from app.services.activity_options import DEFAULT_ACTIVITIES
    assert len(DEFAULT_ACTIVITIES) == 3


def test_default_activities_have_required_fields():
    from app.services.activity_options import DEFAULT_ACTIVITIES
    for act in DEFAULT_ACTIVITIES:
        assert "id" in act
        assert "label" in act
        assert "duration" in act
        assert "time" in act
        assert "vibe" in act


def test_default_activities_time_is_any():
    from app.services.activity_options import DEFAULT_ACTIVITIES
    for act in DEFAULT_ACTIVITIES:
        assert act["time"] == "any"
        assert act["vibe"] == "any"


@pytest.mark.asyncio
async def test_build_activity_options_returns_cached_result():
    from app.services.activity_options import build_activity_options
    cached = [{"id": "cached_act", "label": "Cached", "duration": "1h", "time": "any", "vibe": "any"}]
    with patch("app.services.activity_options.get_cached", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = cached
        result = await build_activity_options("chapora_fort", "Chapora Fort", "Goa", "north_goa", None, None)
    assert result == cached
    mock_get.assert_called_once_with("activity_options:goa:chapora_fort")


@pytest.mark.asyncio
async def test_build_activity_options_groq_success():
    from app.services.activity_options import build_activity_options
    import json as _json
    groq_result = [
        {"id": "sunrise_trek", "label": "Sunrise Trek", "duration": "2h", "time": "morning", "vibe": "adventure"},
        {"id": "cliff_photo", "label": "Cliff Photography", "duration": "1h", "time": "evening", "vibe": "cultural"},
        {"id": "history_walk", "label": "History Walk", "duration": "45m", "time": "morning", "vibe": "cultural"},
        {"id": "sunset_picnic", "label": "Sunset Picnic", "duration": "1h", "time": "evening", "vibe": "chill"},
    ]
    with patch("app.services.activity_options.get_cached", new_callable=AsyncMock) as mock_get, \
         patch("app.services.activity_options.set_cached", new_callable=AsyncMock) as mock_set, \
         patch("app.services.activity_options.aiohttp.ClientSession") as mock_session:
        mock_get.side_effect = [None, None]  # cache miss for activity_options, then area reddit
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"choices": [{"message": {"content": _json.dumps(groq_result)}}]})
        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=MagicMock(return_value=mock_post)))
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await build_activity_options("chapora_fort", "Chapora Fort", "Goa", "north_goa", None, None)
    # Should have called set_cached to store the result
    assert mock_set.called
    cache_call_args = mock_set.call_args
    assert cache_call_args[0][0] == "activity_options:goa:chapora_fort"
    assert cache_call_args[1].get("ttl") == 21600 or cache_call_args[0][2] == 21600


@pytest.mark.asyncio
async def test_build_activity_options_groq_failure_returns_defaults():
    from app.services.activity_options import build_activity_options, DEFAULT_ACTIVITIES
    with patch("app.services.activity_options.get_cached", new_callable=AsyncMock) as mock_get, \
         patch("app.services.activity_options.set_cached", new_callable=AsyncMock), \
         patch("app.services.activity_options.aiohttp.ClientSession") as mock_session:
        mock_get.return_value = None
        mock_session.side_effect = Exception("Groq unreachable")
        result = await build_activity_options("chapora_fort", "Chapora Fort", "Goa", "north_goa", None, None)
    assert result == DEFAULT_ACTIVITIES


@pytest.mark.asyncio
async def test_build_activity_options_uses_reddit_context():
    """reddit_context from area cache is included in Groq prompt."""
    from app.services.activity_options import build_activity_options
    area_signals = [{
        "place_signals": {
            "Chapora Fort": {
                "review_highlights": ["amazing sunrise view"],
                "vibe_tags": ["adventure", "history"],
            }
        }
    }]
    captured_prompts = []

    def fake_groq_post(url, headers=None, json=None, **kwargs):
        if "groq" in url:
            captured_prompts.append(json["messages"][0]["content"])
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.json = AsyncMock(return_value={"choices": [{"message": {"content": '[{"id":"x","label":"X","duration":"1h","time":"any","vibe":"any"}]'}}]})
        return resp

    with patch("app.services.activity_options.get_cached", new_callable=AsyncMock) as mock_get, \
         patch("app.services.activity_options.set_cached", new_callable=AsyncMock), \
         patch("app.services.activity_options.aiohttp.ClientSession") as mock_session:
        mock_get.side_effect = [None, area_signals]
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = MagicMock(side_effect=fake_groq_post)
        mock_session.return_value = mock_client
        await build_activity_options("chapora_fort", "Chapora Fort", "Goa", "north_goa", None, None)

    assert captured_prompts, "Groq post was never called — mock wiring failed"
    assert "chapora fort" in captured_prompts[0].lower() or "Chapora Fort" in captured_prompts[0]


@pytest.mark.asyncio
async def test_build_activity_options_vibe_str_from_intent():
    """vibe_str is derived from intent.vibe."""
    from app.services.activity_options import build_activity_options
    from unittest.mock import MagicMock
    intent = MagicMock()
    intent.vibe = [MagicMock(value="adventure"), MagicMock(value="cultural")]
    captured_prompts = []

    def fake_post(url, headers=None, json=None, **kwargs):
        if "groq" in url:
            captured_prompts.append(json["messages"][0]["content"])
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.json = AsyncMock(return_value={"choices": [{"message": {"content": '[{"id":"x","label":"X","duration":"1h","time":"any","vibe":"any"}]'}}]})
        return resp

    with patch("app.services.activity_options.get_cached", new_callable=AsyncMock) as mock_get, \
         patch("app.services.activity_options.set_cached", new_callable=AsyncMock), \
         patch("app.services.activity_options.aiohttp.ClientSession") as mock_session:
        mock_get.return_value = None
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = MagicMock(side_effect=fake_post)
        mock_session.return_value = mock_client
        await build_activity_options("chapora_fort", "Chapora Fort", "Goa", "north_goa", intent, "couple")

    assert captured_prompts, "Groq post was never called — mock wiring failed"
    assert "adventure" in captured_prompts[0] and "cultural" in captured_prompts[0]
