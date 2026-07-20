"""Full pipeline integration test — experience_type_selected → open_day_planner."""
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


# ── Canned Groq responses ─────────────────────────────────────────────────────

_ACTIVITIES_JSON = json.dumps([
    {"id": "sunrise_trek", "label": "Sunrise Trek", "duration": "2h", "time": "morning", "vibe": "adventure"},
    {"id": "sunset_picnic", "label": "Sunset Picnic", "duration": "1h", "time": "evening", "vibe": "chill"},
])

_ARCS_JSON = json.dumps([
    {"id": "north_to_south", "label": "North → South", "description": "Classic flow", "place_order": ["Chapora Fort"]},
])

_PLAN_JSON = json.dumps([
    {"day": 1, "title": "Fort Day", "activities": [{"time": "7:00 AM", "activity": "Sunrise Trek", "place": "Chapora Fort", "duration": "2h"}], "note": "Start early."},
    {"day": 2, "title": "Chill Day", "activities": [{"time": "5:00 PM", "activity": "Sunset Picnic", "place": "Chapora Fort", "duration": "1h"}], "note": "Easy day."},
    {"day": 3, "title": "Final Day", "activities": [], "note": "Head out."},
])

_BRIEF_JSON = json.dumps({
    "weather": "Hot & humid, 30-34°C. Carry a rain layer.",
    "language_tip": "Konkani locally; English widely spoken at tourist spots.",
    "lingo": [
        "Dev borem korum — greet locals, means God bless you",
        "Kitlem zaata? — how much? — use when bargaining",
        "Susegad — slow down and enjoy",
    ],
    "transport": "Rent a scooter for ₹300-400/day.",
    "local_events": "None currently known",
    "permits": "None required",
    "safety": "Swim only at flagged beaches.",
    "currency": "Beach shacks are cash-only. ATMs in Calangute.",
})

_RESPONDER_TEXT = "Great choices! I've got you set up."

# Parsed (not JSON-encoded) versions for high-level mocks
_ACTIVITIES = json.loads(_ACTIVITIES_JSON)
_ARCS = json.loads(_ARCS_JSON)
_PLAN = json.loads(_PLAN_JSON)
_BRIEF = json.loads(_BRIEF_JSON)

# Canned area/place card data
_AREA_CARDS = [
    {
        "id": "north_goa",
        "name": "North Goa",
        "zone": None,
        "teaser": "Beaches, forts, and vibrant nightlife",
        "summary": "North Goa is the most popular zone.",
        "tags": ["beaches", "forts", "nightlife"],
        "photo_url": None,
    }
]

_PLACE_CARDS = [
    {
        "label": "Things to Do",
        "places": [
            {
                "id": "chapora_fort",
                "name": "Chapora Fort",
                "hook": "Iconic clifftop fort with panoramic views",
                "photo_url": None,
            }
        ],
    }
]


# ── Mock factories ─────────────────────────────────────────────────────────────

def _fixed_session(content: str):
    """aiohttp.ClientSession mock always returning content as Groq response."""
    def fake_post(*args, **kwargs):
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.json = AsyncMock(return_value={"choices": [{"message": {"content": content}}]})
        return resp
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(side_effect=fake_post)
    return MagicMock(return_value=session)


def _cycling_session(responses: list[str]):
    """aiohttp.ClientSession mock cycling through responses in order."""
    call_state = [0]

    def fake_post(*args, **kwargs):
        content = responses[call_state[0] % len(responses)]
        call_state[0] += 1
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.json = AsyncMock(return_value={"choices": [{"message": {"content": content}}]})
        return resp

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(side_effect=fake_post)
    return MagicMock(return_value=session)


def _cycling_groq_post(responses: list):
    """
    Mock for day_planner._groq_post that cycles through pre-parsed JSON values.
    Returns each response in turn (wrapping with modulo).
    """
    call_state = [0]

    async def fake_groq_post(prompt: str, max_tokens: int):
        result = responses[call_state[0] % len(responses)]
        call_state[0] += 1
        return result

    fake_groq_post.call_count = call_state
    return fake_groq_post


# ── Full pipeline test ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_to_day_planner():
    from app.api.server import app as fastapi_app
    from app.graph.builder import build_graph

    THREAD_ID = str(uuid.uuid4())

    # day_planner._groq_post cycling mock:
    # Both detect_intent and responder call determine_action, so calls double.
    # Exact call sequence across Steps 8-9:
    #   call 0: Step 8 detect_intent  → build_route_arcs         → needs _ARCS
    #   call 1: Step 8 responder      → build_route_arcs          → needs _ARCS
    #   call 2: Step 9 detect_intent  → build_day_plan            → needs _PLAN
    #   call 3: Step 9 detect_intent  → build_destination_brief   → needs _BRIEF
    #   call 4: Step 9 responder      → build_day_plan            → needs _PLAN
    #   call 5: Step 9 responder      → build_destination_brief   → needs _BRIEF
    groq_post_mock = _cycling_groq_post([_ARCS, _ARCS, _PLAN, _BRIEF, _PLAN, _BRIEF])
    _groq_call_counter = groq_post_mock.call_count

    # Mock _build_activity_options_for_place directly in stage_machine to avoid
    # patching aiohttp twice (all modules share the same aiohttp module object;
    # patching ClientSession on it from two patch() calls means the last one wins).
    async def _mock_build_activities(state: dict) -> list[dict]:
        state["activity_options"] = _ACTIVITIES
        return _ACTIVITIES

    with patch("app.services.area_cache.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.area_cache.set_cached", new_callable=AsyncMock), \
         patch("app.services.day_planner._groq_post", side_effect=groq_post_mock), \
         patch("app.services.day_planner.tavily_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.day_planner.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.graph.nodes.responder.aiohttp.ClientSession", _fixed_session(_RESPONDER_TEXT)), \
         patch("app.utils.place_photos.fetch_place_photos", new_callable=AsyncMock, return_value=[]), \
         patch("app.api.server.fetch_place_photos", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.stage_machine.fetch_area_cards",
               new_callable=AsyncMock, return_value=_AREA_CARDS), \
         patch("app.services.stage_machine.fetch_place_cards",
               new_callable=AsyncMock, return_value=_PLACE_CARDS), \
         patch("app.services.stage_machine._build_activity_options_for_place",
               side_effect=_mock_build_activities):

        # Build the graph directly to avoid the slow lifespan (MCP subprocesses + sleep)
        compiled, checkpointer = await build_graph()
        fastapi_app.state.graph = compiled
        fastapi_app.state.checkpointer = checkpointer
        fastapi_app.state.thread_id = "test_session"

        async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as client:

            def post(card_action, card_data=None):
                return client.post("/chat", json={
                    "message": "",
                    "thread_id": THREAD_ID,
                    "card_action": card_action,
                    "card_data": card_data or {},
                })

            # Step 1: experience_type_selected
            r = await post("experience_type_selected", {"types": ["beach_coast"]})
            assert r.status_code == 200

            # Step 2: destination_selected → show_area_cards
            r = await post("destination_selected", {"destination": "Goa"})
            assert r.status_code == 200
            data = r.json()
            assert data["action"] == "show_area_cards"

            # Step 3: trip_duration_set (pre-set before area selection to skip duration_pending)
            r = await post("trip_duration_set", {"days": 3})
            assert r.status_code == 200

            # Step 4: area_selected → show_place_cards
            r = await post("area_selected", {"area_id": "north_goa"})
            assert r.status_code == 200
            data = r.json()
            assert data["action"] == "show_place_cards"

            # Step 5: place_selected → show_activity_options (Groq in activity_options.py)
            r = await post("place_selected", {"place_id": "chapora_fort"})
            assert r.status_code == 200
            data = r.json()
            assert data["action"] == "show_activity_options"

            # Step 6: activities_for_place → show_place_cards (back to multi-place loop)
            r = await post("activities_for_place", {"place_id": "chapora_fort", "activities": ["Sunrise Trek", "Sunset Picnic"]})
            assert r.status_code == 200

            # Step 7: activities_confirmed → show_pace_options
            r = await post("activities_confirmed", {})
            assert r.status_code == 200
            data = r.json()
            assert data["action"] == "show_pace_options"

            # Step 8: pace_selected → show_route_arcs (Groq build_route_arcs)
            r = await post("pace_selected", {"pace": "mix"})
            assert r.status_code == 200
            data = r.json()
            assert data["action"] == "show_route_arcs"
            arcs = data["payload"]["arcs"]
            assert isinstance(arcs, list) and len(arcs) > 0
            assert "place_order" in arcs[0]

            # Step 9: route_arc_selected → open_day_planner (Groq build_day_plan + build_destination_brief)
            r = await post("route_arc_selected", {"arc": {"id": "north_to_south", "label": "North → South", "place_order": ["Chapora Fort"]}})
            assert r.status_code == 200
            data = r.json()
            assert data["action"] == "open_day_planner"

            plan = data["payload"]["plan"]
            brief = data["payload"]["brief"]

            assert isinstance(plan, list) and len(plan) > 0
            assert all("day" in d and "activities" in d for d in plan)
            assert "weather" in brief
            assert "lingo" in brief
            assert isinstance(brief["lingo"], list) and len(brief["lingo"]) >= 3

            # Verify cycling mock consumed exactly the expected calls (2 for pace_selected + 4 for route_arc_selected)
            assert _groq_call_counter[0] == 6, (
                f"Expected 6 _groq_post calls (double-invocation of determine_action × 3 Groq steps) "
                f"but got {_groq_call_counter[0]}. If this changes, update the cycling sequence."
            )
