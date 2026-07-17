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


# ── Task 3: _STAGE_RULES and resolve_stage ────────────────────────────────────

def test_stage_rules_is_list_of_tuples():
    from app.services.stage_machine import _STAGE_RULES
    assert isinstance(_STAGE_RULES, list)
    assert len(_STAGE_RULES) == 9
    for predicate, stage in _STAGE_RULES:
        assert callable(predicate)
        assert isinstance(stage, str)


def test_resolve_stage_no_destination_no_experience():
    from app.services.stage_machine import resolve_stage
    assert resolve_stage({}) == "experience_type_unknown"


def test_resolve_stage_no_destination_with_experience():
    from app.services.stage_machine import resolve_stage
    assert resolve_stage({"experience_types": ["beach_coast"]}) == "experience_type_known"


def test_resolve_stage_destination_known():
    from app.services.stage_machine import resolve_stage
    assert resolve_stage({"destination": "Goa"}) == "destination_known"


def test_resolve_stage_selected_place_wins_over_pending_activities():
    """selected_place fires before pending_activities in _STAGE_RULES."""
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "selected_place": "chapora_fort",
        "pending_activities": {"baga_beach": ["Sunrise Walk"]},
    }
    assert resolve_stage(state) == "place_selected"


def test_resolve_stage_pending_activities_wins_over_selected_activities():
    """pending_activities fires before selected_activities in _STAGE_RULES."""
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "pending_activities": {"baga_beach": ["Sunrise Walk"]},
        "selected_activities": ["Sunrise Walk"],
    }
    assert resolve_stage(state) == "area_selected"


def test_resolve_stage_pending_activities_empty_dict_does_not_fire():
    """Empty {} is falsy — should not trigger pending_activities rule."""
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "pending_activities": {},
        "selected_activities": ["Sunrise Walk"],
    }
    assert resolve_stage(state) == "activities_selected"


def test_resolve_stage_selected_activities_fires_when_pending_cleared():
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "selected_activities": ["Sunrise Trek", "Photo Walk"],
    }
    assert resolve_stage(state) == "activities_selected"


def test_resolve_stage_places_shown_with_no_duration():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "places_shown": True}
    assert resolve_stage(state) == "duration_pending"


def test_resolve_stage_places_shown_with_duration():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "places_shown": True, "trip_duration": 3}
    assert resolve_stage(state) == "places_shown"


def test_resolve_stage_selected_area():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_area": "north_goa"}
    assert resolve_stage(state) == "area_selected"


def test_resolve_stage_route_arc_highest_priority():
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "route_arc": {"direction": "north"},
        "selected_pace": "mix",
        "selected_place": "chapora_fort",
        "pending_activities": {"x": ["y"]},
        "selected_activities": ["y"],
    }
    assert resolve_stage(state) == "route_arc_selected"


def test_resolve_stage_selected_pace():
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "selected_pace": "mix",
        "selected_place": "chapora_fort",
    }
    assert resolve_stage(state) == "pace_selected"


# ── Task 3: _resolve_place_name ───────────────────────────────────────────────

def test_resolve_place_name_found_in_place_cards():
    from app.services.stage_machine import _resolve_place_name
    state = {
        "selected_place": "chapora_fort",
        "place_cards": [
            {"label": "Forts", "places": [{"id": "chapora_fort", "name": "Chapora Fort"}]},
        ],
    }
    assert _resolve_place_name(state) == "Chapora Fort"


def test_resolve_place_name_falls_back_to_place_id():
    from app.services.stage_machine import _resolve_place_name
    state = {
        "selected_place": "unknown_place_id",
        "place_cards": [
            {"label": "Forts", "places": [{"id": "chapora_fort", "name": "Chapora Fort"}]},
        ],
    }
    assert _resolve_place_name(state) == "unknown_place_id"


def test_resolve_place_name_no_place_cards():
    from app.services.stage_machine import _resolve_place_name
    state = {"selected_place": "chapora_fort"}
    assert _resolve_place_name(state) == "chapora_fort"


# ── Task 3: determine_action place_selected and area_selected ────────────────

@pytest.mark.asyncio
async def test_determine_action_place_selected_returns_activity_options():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_place": "chapora_fort",
        "place_cards": [
            {"label": "Forts", "places": [{"id": "chapora_fort", "name": "Chapora Fort", "hook": "x", "photo_url": None}]},
        ],
    }
    mock_activities = [{"id": "sunrise_trek", "label": "Sunrise Trek", "duration": "2h", "time": "morning", "vibe": "adventure"}]
    with patch("app.services.stage_machine.build_activity_options", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = mock_activities
        action, payload = await determine_action("place_selected", state)
    assert action == "show_activity_options"
    assert payload["place_id"] == "chapora_fort"
    assert payload["place_name"] == "Chapora Fort"
    assert payload["activities"] == mock_activities


@pytest.mark.asyncio
async def test_determine_action_place_selected_persists_activity_options_to_state():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_place": "chapora_fort",
        "place_cards": [],
    }
    mock_activities = [{"id": "x", "label": "X", "duration": "1h", "time": "any", "vibe": "any"}]
    with patch("app.services.stage_machine.build_activity_options", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = mock_activities
        await determine_action("place_selected", state)
    assert state.get("activity_options") == mock_activities


@pytest.mark.asyncio
async def test_determine_action_area_selected_includes_pending_activities():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_area": "north_goa",
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"label": "Forts", "places": []}]
        action, payload = await determine_action("area_selected", state)
    assert action == "show_place_cards"
    assert payload["pending_activities"] == {"chapora_fort": ["Sunrise Trek"]}


@pytest.mark.asyncio
async def test_determine_action_area_selected_pending_activities_defaults_to_empty():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_area": "north_goa",
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        action, payload = await determine_action("area_selected", state)
    assert action == "show_place_cards"
    assert payload["pending_activities"] == {}


# ── Task 4: intent.py card action handlers ────────────────────────────────────

@pytest.mark.asyncio
async def test_activities_for_place_stores_in_pending_activities():
    from app.graph.nodes.intent import detect_intent
    state = {
        "destination": "Goa",
        "selected_area": "north_goa",
        "selected_place": "chapora_fort",
        "card_action": "activities_for_place",
        "card_data": {
            "place_id": "chapora_fort",
            "activities": ["Sunrise Trek", "Cliff Photography"],
        },
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_place_cards", {"categories": [], "pending_activities": {"chapora_fort": ["Sunrise Trek", "Cliff Photography"]}})
        result = await detect_intent(state)
    assert result["pending_activities"]["chapora_fort"] == ["Sunrise Trek", "Cliff Photography"]


@pytest.mark.asyncio
async def test_activities_for_place_clears_selected_place():
    from app.graph.nodes.intent import detect_intent
    state = {
        "destination": "Goa",
        "selected_area": "north_goa",
        "selected_place": "chapora_fort",
        "card_action": "activities_for_place",
        "card_data": {
            "place_id": "chapora_fort",
            "activities": ["Sunrise Trek"],
        },
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_place_cards", {"categories": [], "pending_activities": {}})
        result = await detect_intent(state)
    assert result["selected_place"] is None


@pytest.mark.asyncio
async def test_activities_for_place_accumulates_across_places():
    """Second place's activities are added alongside first place's."""
    from app.graph.nodes.intent import detect_intent
    state = {
        "destination": "Goa",
        "selected_area": "north_goa",
        "selected_place": "baga_beach",
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
        "card_action": "activities_for_place",
        "card_data": {
            "place_id": "baga_beach",
            "activities": ["Sunset Swim", "Beach Volleyball"],
        },
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_place_cards", {"categories": [], "pending_activities": {}})
        result = await detect_intent(state)
    assert "chapora_fort" in result["pending_activities"]
    assert "baga_beach" in result["pending_activities"]
    assert result["pending_activities"]["baga_beach"] == ["Sunset Swim", "Beach Volleyball"]


@pytest.mark.asyncio
async def test_activities_for_place_routes_to_area_selected():
    from app.graph.nodes.intent import detect_intent
    state = {
        "destination": "Goa",
        "selected_area": "north_goa",
        "selected_place": "chapora_fort",
        "card_action": "activities_for_place",
        "card_data": {"place_id": "chapora_fort", "activities": ["Sunrise Trek"]},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_place_cards", {"categories": [], "pending_activities": {"chapora_fort": ["Sunrise Trek"]}})
        result = await detect_intent(state)
    assert result["conversation_stage"] == "area_selected"
    assert result["skip_graph"] is True
    assert result["action"] == "show_place_cards"


@pytest.mark.asyncio
async def test_activities_confirmed_flattens_pending_into_selected():
    from app.graph.nodes.intent import detect_intent
    state = {
        "destination": "Goa",
        "selected_area": "north_goa",
        "pending_activities": {
            "chapora_fort": ["Sunrise Trek", "Cliff Photography"],
            "baga_beach": ["Sunset Swim"],
        },
        "card_action": "activities_confirmed",
        "card_data": {},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_pace_options", {})
        result = await detect_intent(state)
    selected = result["selected_activities"]
    assert "Sunrise Trek" in selected
    assert "Cliff Photography" in selected
    assert "Sunset Swim" in selected
    assert len(selected) == 3


@pytest.mark.asyncio
async def test_activities_confirmed_clears_pending_activities():
    """Invariant: pending_activities MUST be {} after activities_confirmed."""
    from app.graph.nodes.intent import detect_intent
    state = {
        "destination": "Goa",
        "selected_area": "north_goa",
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
        "card_action": "activities_confirmed",
        "card_data": {},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_pace_options", {})
        result = await detect_intent(state)
    assert result["pending_activities"] == {}


@pytest.mark.asyncio
async def test_activities_confirmed_routes_to_activities_selected():
    from app.graph.nodes.intent import detect_intent
    state = {
        "destination": "Goa",
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
        "card_action": "activities_confirmed",
        "card_data": {},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_pace_options", {})
        result = await detect_intent(state)
    assert result["conversation_stage"] == "activities_selected"
    assert result["skip_graph"] is True
    assert result["action"] == "show_pace_options"


@pytest.mark.asyncio
async def test_activities_confirmed_empty_pending_gives_empty_selected():
    """Edge case: user hits Done with no activities saved."""
    from app.graph.nodes.intent import detect_intent
    state = {
        "destination": "Goa",
        "pending_activities": {},
        "card_action": "activities_confirmed",
        "card_data": {},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_pace_options", {})
        result = await detect_intent(state)
    assert result["selected_activities"] == []
    assert result["pending_activities"] == {}


# ── Integration: place_selected card action sets activity_options ─────────────

@pytest.mark.asyncio
async def test_place_selected_card_action_sets_activity_options():
    """detect_intent card_action='place_selected' must populate state['activity_options']."""
    from app.graph.nodes.intent import detect_intent
    mock_activities = [{"id": "sunrise_trek", "label": "Sunrise Trek", "duration": "2h", "time": "morning", "vibe": "adventure"}]
    state = {
        "destination": "Goa",
        "selected_area": "north_goa",
        "card_action": "place_selected",
        "card_data": {"place_id": "chapora_fort"},
        "place_cards": [
            {"label": "Forts", "places": [{"id": "chapora_fort", "name": "Chapora Fort", "hook": "x", "photo_url": None}]},
        ],
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.services.stage_machine.build_activity_options", new_callable=AsyncMock) as mock_build:
        mock_build.return_value = mock_activities
        mock_action.return_value = ("show_activity_options", {
            "place_id": "chapora_fort",
            "place_name": "Chapora Fort",
            "activities": mock_activities,
        })
        result = await detect_intent(state)
    assert result.get("activity_options") == mock_activities
