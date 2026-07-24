"""Sprint 4 — place cards and place selection tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.graph.state import GraphState


# ── Task 1: State fields ──────────────────────────────────────────────────────

def test_graphstate_has_place_cards():
    state: GraphState = {}
    state["place_cards"] = [{"label": "Beaches", "places": []}]
    assert state["place_cards"][0]["label"] == "Beaches"


def test_graphstate_has_selected_place():
    state: GraphState = {}
    state["selected_place"] = "chapora_fort"
    assert state["selected_place"] == "chapora_fort"


def test_graphstate_selected_place_defaults_to_none():
    state: GraphState = {}
    assert state.get("selected_place") is None


# ── Task 1: Responder persistence ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_responder_persists_place_cards():
    from app.graph.nodes.responder import responder
    state: GraphState = {
        "destination": "Goa",
        "messages": [{"role": "user", "content": "hi"}],
        "place_cards": [{"label": "Beaches", "places": [{"id": "x", "name": "Y", "hook": "z", "photo_url": None}]}],
        "selected_place": None,
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
    assert result["place_cards"] == state["place_cards"]
    assert result["selected_place"] is None


@pytest.mark.asyncio
async def test_responder_persists_selected_place():
    from app.graph.nodes.responder import responder
    state: GraphState = {
        "destination": "Goa",
        "messages": [{"role": "user", "content": "hi"}],
        "selected_place": "chapora_fort",
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
    assert result["selected_place"] == "chapora_fort"


# ── Task 2: get_area_reddit_signals ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_area_reddit_signals_returns_expected_shape():
    """get_area_reddit_signals returns dict with place_signals and raw_posts_text."""
    from app.services.reddit_signals import get_area_reddit_signals
    with patch("app.services.reddit_signals.asyncpraw.Reddit") as mock_reddit_cls, \
         patch("app.services.reddit_signals._extract_place_signals", new_callable=AsyncMock) as mock_extract:
        mock_reddit = AsyncMock()
        mock_reddit.__aenter__ = AsyncMock(return_value=mock_reddit)
        mock_reddit.__aexit__ = AsyncMock(return_value=False)
        mock_reddit_cls.return_value = mock_reddit
        mock_extract.return_value = {"place_signals": {"Chapora Fort": {"sentiment_score": 0.8}}}
        result = await get_area_reddit_signals("Vagator", "Goa", ["beach_coast"])
    assert "place_signals" in result
    assert "raw_posts_text" in result


@pytest.mark.asyncio
async def test_get_area_reddit_signals_on_failure_returns_empty():
    """get_area_reddit_signals returns empty dicts on any failure."""
    from app.services.reddit_signals import get_area_reddit_signals
    with patch("app.services.reddit_signals.asyncpraw.Reddit", side_effect=Exception("no creds")):
        result = await get_area_reddit_signals("Vagator", "Goa", [])
    assert result == {"place_signals": {}, "raw_posts_text": ""}


@pytest.mark.asyncio
async def test_search_reddit_uses_comment_limit():
    """_search_reddit with comment_limit=2 reads only 2 comments."""
    from app.services.reddit_signals import _search_reddit
    mock_comment = MagicMock()
    mock_comment.body = "great place" * 30  # 330 chars
    mock_submission = AsyncMock()
    mock_submission.title = "Vagator guide"
    mock_submission.selftext = ""
    mock_submission.comments = MagicMock()
    mock_submission.comments.replace_more = AsyncMock()
    mock_submission.comments.list = MagicMock(return_value=[mock_comment] * 5)
    mock_subreddit = AsyncMock()
    async def _gen(*a, **kw):
        yield mock_submission
    mock_subreddit.search = _gen
    mock_reddit = AsyncMock()
    mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)
    posts = await _search_reddit(mock_reddit, "Vagator Goa", limit=1, comment_limit=2, comment_body_chars=100)
    assert len(posts) == 1
    # 2 comments × 100 chars each, joined by " | "
    assert posts[0].count(" | ") == 1  # 2 comments → 1 separator


# ── Task 3: fetch_place_cards pipeline ───────────────────────────────────────

def _make_place(place_id: str, name: str, rating: float = 4.5) -> dict:
    """Helper — raw Maps dict."""
    return {"place_id": place_id, "name": name, "rating": rating, "user_ratings_total": 100,
            "types": ["tourist_attraction"], "photo_url": None, "lat": 15.6, "lng": 73.7}


def test_rank_places_for_area_filters_low_rating():
    """_rank_places_for_area drops places with rating < 4.2."""
    from app.services.stage_machine import _rank_places_for_area
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    places = [
        _make_place("good", "Good Place", 4.5),
        _make_place("bad", "Bad Place", 3.9),
    ]
    result = _rank_places_for_area(places, intent, {}, {})
    ids = [p["id"] for p in result]
    assert "bad" not in ids


def test_rank_places_for_area_returns_at_most_three():
    """_rank_places_for_area caps output at 3 places."""
    from app.services.stage_machine import _rank_places_for_area
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    places = [_make_place(f"p{i}", f"Place {i}", 4.6) for i in range(6)]
    result = _rank_places_for_area(places, intent, {}, {})
    assert len(result) <= 3


def test_rank_places_for_area_output_shape():
    """_rank_places_for_area output dicts have id, name, photo_url."""
    from app.services.stage_machine import _rank_places_for_area
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    places = [_make_place("fort", "Chapora Fort", 4.7)]
    result = _rank_places_for_area(places, intent, {}, {})
    assert len(result) == 1
    assert set(result[0].keys()) >= {"id", "name", "photo_url"}


def test_rank_places_for_area_empty_input_returns_empty():
    """_rank_places_for_area returns [] on empty input."""
    from app.services.stage_machine import _rank_places_for_area
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    assert _rank_places_for_area([], intent, {}, {}) == []


@pytest.mark.asyncio
async def test_fetch_place_cards_returns_categories():
    """fetch_place_cards returns list of category dicts with label and places."""
    from app.services.stage_machine import fetch_place_cards
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    state = {
        "destination": "Goa",
        "selected_areas": ["vagator"],
        "experience_types": ["beach_coast"],
        "selected_vibe_ids": [],
        "travel_intent": intent,
        "reddit_signals": {},
        "blog_signals": {},
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
    }
    mock_places = [_make_place("fort", "Chapora Fort", 4.8), _make_place("beach", "Ozran Beach", 4.5)]
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock) as mock_groq, \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock, return_value=mock_places), \
         patch("asyncio.create_task"):
        mock_groq.side_effect = [
            [{"label": "Beaches", "query": "beaches swimming"}],  # category call
            {"fort": "Panoramic views", "beach": "Hidden cove"},  # hooks call
        ]
        result = await fetch_place_cards(state)
    assert isinstance(result, list)
    assert len(result) >= 1
    cat = result[0]
    assert "label" in cat
    assert "places" in cat
    if cat["places"]:
        p = cat["places"][0]
        assert {"id", "name", "hook", "photo_url"} <= set(p.keys())


@pytest.mark.asyncio
async def test_fetch_place_cards_uses_cache_on_hit():
    """fetch_place_cards returns cached result and skips pipeline."""
    from app.services.stage_machine import fetch_place_cards
    cached = [{"label": "Beaches", "places": [{"id": "x", "name": "X", "hook": "hook", "photo_url": None}]}]
    state = {
        "destination": "Goa", "selected_areas": ["vagator"],
        "experience_types": [], "selected_vibe_ids": [],
        "travel_intent": None, "reddit_signals": {}, "blog_signals": {},
        "area_cards": [],
    }
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=cached), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock) as mock_search, \
         patch("asyncio.create_task"):
        result = await fetch_place_cards(state)
    assert result == cached
    mock_search.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_place_cards_falls_back_to_defaults_on_groq_failure():
    """fetch_place_cards uses DEFAULT_PLACE_CATEGORIES when Groq returns None."""
    from app.services.stage_machine import fetch_place_cards
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    state = {
        "destination": "Goa", "selected_areas": ["vagator"],
        "experience_types": [], "selected_vibe_ids": [],
        "travel_intent": intent, "reddit_signals": {}, "blog_signals": {},
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
    }
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock, return_value=[]), \
         patch("asyncio.create_task"):
        result = await fetch_place_cards(state)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_prefetch_area_reddit_skips_if_cached():
    """_prefetch_area_reddit does nothing if Redis key already warm."""
    from app.services.stage_machine import _prefetch_area_reddit
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=[{"existing": True}]), \
         patch("app.services.stage_machine.get_area_reddit_signals", new_callable=AsyncMock) as mock_reddit:
        await _prefetch_area_reddit("Goa", "vagator", "Vagator", [])
    mock_reddit.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_area_reddit_stores_signals():
    """_prefetch_area_reddit fetches and stores Reddit signals when cache is cold."""
    from app.services.stage_machine import _prefetch_area_reddit
    signals = {"place_signals": {"Chapora Fort": {"sentiment_score": 0.9}}, "raw_posts_text": "text"}
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock) as mock_set, \
         patch("app.services.stage_machine.get_area_reddit_signals", new_callable=AsyncMock, return_value=signals):
        await _prefetch_area_reddit("Goa", "vagator", "Vagator", ["beach_coast"])
    mock_set.assert_called_once()
    call_args = mock_set.call_args
    assert call_args[1].get("ttl") == 3600 or (len(call_args[0]) > 2 and call_args[0][2] == 3600)


# ── Task 4: resolve_stage + determine_action + intent handler ─────────────────

def test_resolve_stage_selected_place_wins_over_selected_areas():
    """selected_place takes priority over selected_areas in resolve_stage."""
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "selected_areas": ["vagator"],
        "selected_place": "chapora_fort",
        "vibes_confirmed": True,
    }
    assert resolve_stage(state) == "place_selected"


def test_resolve_stage_selected_place_wins_over_places_shown():
    """selected_place takes priority over places_shown in resolve_stage."""
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "selected_areas": ["vagator"],
        "places_shown": True,
        "selected_place": "beach",
    }
    assert resolve_stage(state) == "place_selected"


def test_resolve_stage_areas_selected_when_no_place():
    """resolve_stage returns areas_selected when selected_areas is set but selected_place is not."""
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_areas": ["vagator"]}
    assert resolve_stage(state) == "areas_selected"


@pytest.mark.asyncio
async def test_determine_action_areas_selected_calls_fetch_place_cards():
    """determine_action for areas_selected calls fetch_place_cards and returns show_place_cards."""
    from app.services.stage_machine import determine_action
    categories = [{"label": "Beaches", "places": [{"id": "x", "name": "X", "hook": "y", "photo_url": None}]}]
    state = {
        "destination": "Goa", "selected_areas": ["vagator"],
        "experience_types": [], "selected_vibe_ids": [],
        "travel_intent": None, "reddit_signals": {}, "blog_signals": {},
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock, return_value=categories):
        action, payload = await determine_action("areas_selected", state)
    assert action == "show_place_cards"
    assert payload["places"] == [{"id": "x", "name": "X", "hook": "y", "photo_url": None}]
    assert payload["pending_activities"] == {}


@pytest.mark.asyncio
async def test_determine_action_place_selected_returns_stub():
    """determine_action for place_selected returns show_activity_options with place info."""
    from app.services.stage_machine import determine_action
    mock_activities = [{"id": "explore_on_foot", "label": "Explore on foot", "duration": "1h", "time": "any", "vibe": "any"}]
    with patch("app.services.stage_machine.build_activity_options", new_callable=AsyncMock, return_value=mock_activities):
        action, payload = await determine_action("place_selected", {"selected_place": "chapora_fort"})
    assert action == "show_activity_options"
    assert "activities" in payload
    assert "place_id" in payload
    assert "place_name" in payload


@pytest.mark.asyncio
async def test_detect_intent_place_selected_sets_state():
    """detect_intent with card_action=place_selected sets selected_place and calls determine_action."""
    from app.graph.nodes.intent import detect_intent
    from app.graph.state import GraphState
    state: GraphState = {
        "destination": "Goa",
        "selected_areas": ["vagator"],
        "card_action": "place_selected",
        "card_data": {"place_id": "chapora_fort"},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.intent.resolve_stage", return_value="place_selected"):
        mock_action.return_value = ("show_activity_options", {"activities": []})
        result = await detect_intent(state)
    assert result["selected_place"] == "chapora_fort"
    assert result["card_action"] is None
    assert result["skip_graph"] is True
    assert result["action"] == "show_activity_options"
    assert result["payload"] == {"activities": []}
