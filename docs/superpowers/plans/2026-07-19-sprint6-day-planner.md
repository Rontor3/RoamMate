# Sprint 6 — Day Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace three empty stubs (`build_route_arcs`, `build_day_plan`, `build_destination_brief`) with real implementations so `route_arc_selected` fires `open_day_planner` with a real day-by-day itinerary and destination intel.

**Architecture:** New `app/services/day_planner.py` owns all data work (Groq + Tavily); the three stubs in `stage_machine.py` become one-line bridge functions that import from it. A new `selected_places: List[str]` state field plugs the gap where `activities_confirmed` was discarding place IDs.

**Tech Stack:** Python 3.13, FastAPI, LangGraph, aiohttp (Groq), Tavily search, Redis (via `area_cache`), pytest-asyncio

## Global Constraints

- Groq model: `meta-llama/llama-4-scout-17b-16e-instruct` (same as Sprint 5)
- Groq env var: `GROQ_API` (not `GROQ_API_KEY`)
- Groq URL: `https://api.groq.com/openai/v1/chat/completions`
- `temperature: 0.3` on all Groq calls
- Redis cache helpers: `get_cached` / `set_cached` from `app.services.area_cache`
- Activity Redis key: `activity_options:{destination.lower()}:{place_id.lower()}` TTL 21600
- `PACE_DENSITY = {"slow": 2, "mix": 3, "power": 5}` — activities per day
- `trip_duration` defaults to 1 when 0 or missing: `max(state.get("trip_duration") or 1, 1)`
- Markdown fence stripping: if text starts with ` ``` `, split on ` ``` `, take `parts[1]`, strip leading `json`, then split again on ` ``` ` and take `parts[0]`
- All handlers in `intent.py` set `skip_graph = True` before returning
- Never cache `DEFAULT_ACTIVITIES` / `DEFAULT_ARCS` — only cache Groq success results

---

## Task 1: State field + intent handler updates

**Files:**
- Modify: `app/graph/state.py` (add `selected_places` after line 100)
- Modify: `app/graph/nodes/intent.py` (update `activities_confirmed` at line 141; add `trip_duration_set` after line 153)
- Modify: `app/graph/nodes/responder.py` (persist `selected_places` in return dict after line 344)
- Create: `tests/unit/services/test_sprint6_day_plan.py`

**Interfaces:**
- Produces: `state["selected_places"]: List[str]` — available for Tasks 2 and 3
- Produces: `state["trip_duration"]: int` — set by new `trip_duration_set` handler

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/services/test_sprint6_day_plan.py`:

```python
"""Sprint 6 — day planner tests."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.graph.state import GraphState


# ── Task 1: selected_places state field ──────────────────────────────────────

def test_graphstate_has_selected_places():
    state: GraphState = {}
    state["selected_places"] = ["chapora_fort", "baga_beach"]
    assert state["selected_places"] == ["chapora_fort", "baga_beach"]


def test_graphstate_selected_places_defaults_to_none():
    state: GraphState = {}
    assert state.get("selected_places") is None


# ── Task 1: activities_confirmed saves selected_places ───────────────────────

@pytest.mark.asyncio
async def test_activities_confirmed_saves_selected_places():
    from app.graph.nodes.intent import intent
    state: GraphState = {
        "card_action": "activities_confirmed",
        "card_data": {},
        "pending_activities": {
            "chapora_fort": ["Sunrise Trek"],
            "baga_beach": ["Beach Volleyball"],
        },
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.intent.resolve_stage", return_value="activities_selected"):
        mock_action.return_value = ("show_pace_options", {})
        result = await intent(state)
    assert set(result["selected_places"]) == {"chapora_fort", "baga_beach"}
    assert result["pending_activities"] == {}
    assert set(result["selected_activities"]) == {"Sunrise Trek", "Beach Volleyball"}


# ── Task 1: trip_duration_set handler ────────────────────────────────────────

@pytest.mark.asyncio
async def test_trip_duration_set_handler():
    from app.graph.nodes.intent import intent
    state: GraphState = {
        "card_action": "trip_duration_set",
        "card_data": {"days": 3},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.intent.resolve_stage", return_value="places_shown"):
        mock_action.return_value = ("show_activity_options", {"activities": []})
        result = await intent(state)
    assert result["trip_duration"] == 3
    assert result["skip_graph"] is True


@pytest.mark.asyncio
async def test_trip_duration_set_defaults_to_3_when_missing():
    from app.graph.nodes.intent import intent
    state: GraphState = {
        "card_action": "trip_duration_set",
        "card_data": {},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.intent.resolve_stage", return_value="places_shown"):
        mock_action.return_value = ("show_activity_options", {"activities": []})
        result = await intent(state)
    assert result["trip_duration"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/rakshitsingh/Desktop/My_project/RoamMate
pytest tests/unit/services/test_sprint6_day_plan.py -v 2>&1 | head -40
```

Expected: FAIL — `KeyError: 'selected_places'` or `AttributeError`

- [ ] **Step 3: Add `selected_places` to GraphState**

In `app/graph/state.py`, after line 100 (after `activity_options: List[Dict[str, Any]]`):

```python
    # ── Activity selection loop — populated in Sprint 5 ──────────────────────
    pending_activities: Dict[str, List[str]]  # {place_id: [activity_labels]} — accumulates during multi-place loop
    activity_options: List[Dict[str, Any]]    # current activity chips shown — persisted for frontend re-render
    selected_places: List[str]               # place IDs user actually selected (set by activities_confirmed before clearing pending_activities)
```

- [ ] **Step 4: Update `activities_confirmed` in `intent.py`**

Replace the `activities_confirmed` block (lines 141–153) with:

```python
    elif card_action == "activities_confirmed":
        pending = dict(state.get("pending_activities") or {})
        state["selected_places"] = list(pending.keys())          # save before clearing
        state["selected_activities"] = [act for acts in pending.values() for act in acts]
        state["pending_activities"] = {}                         # MUST clear before resolve_stage
        state["selected_place"] = None
        state["card_action"] = None
        state["skip_graph"] = True
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state
```

- [ ] **Step 5: Add `trip_duration_set` handler in `intent.py`**

After the `activities_confirmed` block and before `elif card_action == "route_selected":`, insert:

```python
    elif card_action == "trip_duration_set":
        state["trip_duration"] = int(card_data.get("days", 3))
        state["card_action"] = None
        state["skip_graph"] = True
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state
```

- [ ] **Step 6: Persist `selected_places` in `responder.py`**

In `app/graph/nodes/responder.py`, in the `return {...}` dict after `"activity_options": state.get("activity_options") or [],`:

```python
        "activity_options": state.get("activity_options") or [],
        "selected_places": state.get("selected_places") or [],
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/unit/services/test_sprint6_day_plan.py -v 2>&1 | head -30
```

Expected: 4 tests PASS

- [ ] **Step 8: Run full suite to check for regressions**

```bash
pytest tests/unit/services/ -v --tb=short 2>&1 | tail -20
```

Expected: same pass count as before (161/162 or better)

- [ ] **Step 9: Commit**

```bash
git add app/graph/state.py app/graph/nodes/intent.py app/graph/nodes/responder.py tests/unit/services/test_sprint6_day_plan.py
git commit -m "feat(sprint6): add selected_places state field, trip_duration_set handler, save places on activities_confirmed"
```

---

## Task 2: `generate_route_arcs`

**Files:**
- Create: `app/services/day_planner.py`
- Modify: `tests/unit/services/test_sprint6_day_plan.py` (append tests)

**Interfaces:**
- Produces: `generate_route_arcs(state: dict) -> list[dict]`
- Arc shape: `{"id": str, "label": str, "description": str, "place_order": list[str]}`
- Fallback: `DEFAULT_ARCS` — 2 generic arcs using place names from place_cards filtered by selected_places

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/services/test_sprint6_day_plan.py`:

```python
# ── Task 2: generate_route_arcs ───────────────────────────────────────────────

def _make_session_mock(content: str):
    """Build aiohttp.ClientSession mock returning fixed JSON content."""
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


_BASE_STATE = {
    "destination": "Goa",
    "selected_area": "north_goa",
    "selected_places": ["chapora_fort"],
    "place_cards": [{"category": "Forts", "places": [{"id": "chapora_fort", "name": "Chapora Fort"}]}],
    "experience_types": ["beach_coast"],
    "trip_who": "solo",
    "trip_duration": 3,
}


@pytest.mark.asyncio
async def test_generate_route_arcs_returns_groq_arcs():
    from app.services.day_planner import generate_route_arcs
    groq_arcs = [{"id": "north_to_south", "label": "North → South", "description": "Classic flow", "place_order": ["Chapora Fort"]}]
    with patch("app.services.day_planner.aiohttp.ClientSession", _make_session_mock(json.dumps(groq_arcs))):
        result = await generate_route_arcs(_BASE_STATE)
    assert isinstance(result, list) and len(result) >= 1
    assert result[0]["id"] == "north_to_south"
    assert "place_order" in result[0]


@pytest.mark.asyncio
async def test_generate_route_arcs_fallback_on_groq_failure():
    from app.services.day_planner import generate_route_arcs
    bad_session = MagicMock()
    bad_session.__aenter__ = AsyncMock(side_effect=Exception("Groq down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=bad_session)):
        result = await generate_route_arcs(_BASE_STATE)
    assert len(result) == 2
    assert result[0]["id"] == "selection_order"
    assert result[1]["id"] == "reverse_order"


@pytest.mark.asyncio
async def test_generate_route_arcs_filters_by_selected_places():
    """Only place names matching selected_places IDs are passed to Groq."""
    from app.services.day_planner import generate_route_arcs
    captured = []

    def fake_post(url, headers=None, json=None, **kwargs):
        captured.append(json["messages"][0]["content"])
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.json = AsyncMock(return_value={"choices": [{"message": {"content": "[]"}}]})
        return resp

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(side_effect=fake_post)

    state = {
        **_BASE_STATE,
        "selected_places": ["chapora_fort"],
        "place_cards": [{"category": "All", "places": [
            {"id": "chapora_fort", "name": "Chapora Fort"},
            {"id": "baga_beach", "name": "Baga Beach"},   # NOT selected
        ]}],
    }
    with patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=session)):
        await generate_route_arcs(state)

    assert captured, "Groq was never called"
    assert "Chapora Fort" in captured[0]
    assert "Baga Beach" not in captured[0]


@pytest.mark.asyncio
async def test_generate_route_arcs_fallback_uses_all_place_cards_when_selected_places_empty():
    from app.services.day_planner import generate_route_arcs
    state = {
        **_BASE_STATE,
        "selected_places": [],  # empty — fall back to all place_cards
        "place_cards": [{"category": "All", "places": [
            {"id": "chapora_fort", "name": "Chapora Fort"},
            {"id": "baga_beach", "name": "Baga Beach"},
        ]}],
    }
    bad_session = MagicMock()
    bad_session.__aenter__ = AsyncMock(side_effect=Exception("Groq down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=bad_session)):
        result = await generate_route_arcs(state)
    assert result[0]["place_order"] == ["Chapora Fort", "Baga Beach"]
    assert result[1]["place_order"] == ["Baga Beach", "Chapora Fort"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/services/test_sprint6_day_plan.py::test_generate_route_arcs_returns_groq_arcs -v 2>&1
```

Expected: FAIL — `ModuleNotFoundError: app.services.day_planner`

- [ ] **Step 3: Create `app/services/day_planner.py`**

```python
"""
app/services/day_planner.py — Sprint 6: route arcs, day plan, destination brief.
"""
import asyncio
import json
import os
from datetime import datetime
from typing import Any

import aiohttp

from app.services.area_cache import get_cached
from app.services.tavily_client import tavily_search
from app.utils.logger import get_logger

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

PACE_DENSITY: dict[str, int] = {"slow": 2, "mix": 3, "power": 5}


def _strip_fences(text: str) -> str:
    """Strip markdown code fences from Groq response."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.split("```")[0]
    return text


async def _groq_post(prompt: str, max_tokens: int) -> Any:
    """POST to Groq and return parsed JSON. Raises on any failure."""
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(GROQ_URL, headers=headers, json=body) as r:
            result = await r.json()
            text = result["choices"][0]["message"]["content"]
            return json.loads(_strip_fences(text))


async def generate_route_arcs(state: dict) -> list[dict]:
    """Generate 2–3 geographic route arc options for the user's selected places."""
    destination = state.get("destination", "")
    selected_area = state.get("selected_area", "")
    experience_types: list[str] = state.get("experience_types") or []
    trip_who = state.get("trip_who")
    trip_duration = max(state.get("trip_duration") or 1, 1)

    selected_ids = set(state.get("selected_places") or [])
    place_names = [
        p.get("name", p.get("id", ""))
        for cat in (state.get("place_cards") or [])
        for p in cat.get("places", [])
        if not selected_ids or p.get("id") in selected_ids
    ]

    default_arcs = [
        {
            "id": "selection_order",
            "label": "In Order",
            "description": "Visit places in the order you selected them",
            "place_order": place_names,
        },
        {
            "id": "reverse_order",
            "label": "Reverse Order",
            "description": "Start from the last place and work back",
            "place_order": list(reversed(place_names)),
        },
    ]

    prompt = (
        f"You are a travel expert. The user is visiting {destination}, focusing on the {selected_area} area. "
        f"Places selected: {place_names}. "
        f"Experience types: {experience_types}. Group: {trip_who or 'solo'}. "
        f"Trip duration: {trip_duration} days. "
        f"Generate 2-3 geographic route arcs — different orderings of these places that make physical sense "
        f"(e.g. north-to-south, coastal loop, base-camp style). "
        f"Return a JSON array. Each object: id (snake_case), label (short name), description (1 sentence — who it suits), "
        f"place_order (list of place names in visit order). "
        f"Return only valid JSON, no explanation."
    )

    try:
        parsed = await _groq_post(prompt, max_tokens=400)
        if isinstance(parsed, list) and parsed:
            logger.info(f"[day_planner] route_arcs ✓ {len(parsed)} arcs for {destination}")
            return parsed
    except Exception as e:
        logger.error(f"[day_planner] route_arcs Groq failed: {e} — using defaults")

    return default_arcs
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/services/test_sprint6_day_plan.py -k "route_arcs" -v 2>&1
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/day_planner.py tests/unit/services/test_sprint6_day_plan.py
git commit -m "feat(sprint6): add generate_route_arcs to day_planner.py"
```

---

## Task 3: `generate_day_plan`

**Files:**
- Modify: `app/services/day_planner.py` (append `generate_day_plan`)
- Modify: `tests/unit/services/test_sprint6_day_plan.py` (append tests)

**Interfaces:**
- Consumes: `generate_route_arcs` already in `day_planner.py`; `PACE_DENSITY` constant; `get_cached` from `area_cache`
- Produces: `generate_day_plan(state: dict) -> list[dict]`
- Day shape: `{"day": int, "title": str, "activities": list[{"time", "activity", "place", "duration"}], "note": str}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/services/test_sprint6_day_plan.py`:

```python
# ── Task 3: generate_day_plan ─────────────────────────────────────────────────

_PLAN_STATE = {
    "destination": "Goa",
    "route_arc": {"place_order": ["Chapora Fort"]},
    "selected_activities": ["Sunrise Trek", "Sunset Picnic"],
    "selected_pace": "mix",
    "trip_duration": 3,
    "place_cards": [],
    "travel_intent": None,
}

_GROQ_PLAN = json.dumps([
    {"day": 1, "title": "Fort Day", "activities": [{"time": "7:00 AM", "activity": "Sunrise Trek", "place": "Chapora Fort", "duration": "2h"}], "note": "Start early."},
    {"day": 2, "title": "Chill Day", "activities": [{"time": "5:00 PM", "activity": "Sunset Picnic", "place": "Chapora Fort", "duration": "1h"}], "note": "Easy day."},
    {"day": 3, "title": "Wrap Up", "activities": [], "note": "Check out."},
])


@pytest.mark.asyncio
async def test_generate_day_plan_returns_groq_plan():
    from app.services.day_planner import generate_day_plan
    with patch("app.services.day_planner.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.day_planner.aiohttp.ClientSession", _make_session_mock(_GROQ_PLAN)):
        result = await generate_day_plan(_PLAN_STATE)
    assert isinstance(result, list) and len(result) > 0
    assert result[0]["day"] == 1
    assert "activities" in result[0]
    assert "note" in result[0]


@pytest.mark.asyncio
async def test_generate_day_plan_fallback_distributes_evenly():
    from app.services.day_planner import generate_day_plan
    state = {**_PLAN_STATE, "selected_activities": ["A", "B", "C"], "trip_duration": 3}
    bad_session = MagicMock()
    bad_session.__aenter__ = AsyncMock(side_effect=Exception("Groq down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.day_planner.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=bad_session)):
        result = await generate_day_plan(state)
    assert len(result) == 3
    assert all("day" in d and "activities" in d for d in result)


@pytest.mark.asyncio
async def test_generate_day_plan_uses_cached_activity_objects():
    """Redis-cached full activity objects (with duration/time/vibe) are sent to Groq."""
    from app.services.day_planner import generate_day_plan
    cached_activities = [{"id": "sunrise_trek", "label": "Sunrise Trek", "duration": "2h", "time": "morning", "vibe": "adventure"}]
    state = {
        **_PLAN_STATE,
        "place_cards": [{"category": "Forts", "places": [{"id": "chapora_fort"}]}],
    }
    captured = []

    def fake_post(url, headers=None, json=None, **kwargs):
        captured.append(json["messages"][0]["content"])
        resp = AsyncMock()
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        resp.json = AsyncMock(return_value={"choices": [{"message": {"content": _GROQ_PLAN}}]})
        return resp

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.post = MagicMock(side_effect=fake_post)

    with patch("app.services.day_planner.get_cached", new_callable=AsyncMock, return_value=cached_activities), \
         patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=session)):
        await generate_day_plan(state)

    assert captured, "Groq was never called"
    assert "morning" in captured[0]  # duration/time from cached objects reached the prompt


@pytest.mark.asyncio
async def test_generate_day_plan_trip_duration_zero_defaults_to_one():
    from app.services.day_planner import generate_day_plan
    state = {**_PLAN_STATE, "trip_duration": 0, "selected_activities": ["A"]}
    bad_session = MagicMock()
    bad_session.__aenter__ = AsyncMock(side_effect=Exception("Groq down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.day_planner.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=bad_session)):
        result = await generate_day_plan(state)
    assert len(result) == 1  # trip_duration defaults to 1
    assert result[0]["day"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/services/test_sprint6_day_plan.py -k "day_plan" -v 2>&1 | head -20
```

Expected: FAIL — `ImportError: cannot import name 'generate_day_plan'`

- [ ] **Step 3: Add `generate_day_plan` to `app/services/day_planner.py`**

Append after `generate_route_arcs`:

```python
async def generate_day_plan(state: dict) -> list[dict]:
    """Generate day-by-day timed itinerary from confirmed activities + route arc + pace."""
    destination = state.get("destination", "")
    route_arc: dict = state.get("route_arc") or {}
    selected_activities: list[str] = state.get("selected_activities") or []
    selected_pace = state.get("selected_pace", "mix")
    trip_duration = max(state.get("trip_duration") or 1, 1)

    # Reconstruct full activity objects from Redis cache (Sprint 5 cached activity_options)
    place_ids = [
        p.get("id")
        for cat in (state.get("place_cards") or [])
        for p in cat.get("places", [])
        if p.get("id")
    ]
    all_cached: list[dict] = []
    for pid in place_ids:
        cache_key = f"activity_options:{destination.lower()}:{pid.lower()}"
        cached = await get_cached(cache_key)
        if cached:
            all_cached.extend(cached)

    label_to_obj: dict[str, dict] = {a["label"].lower(): a for a in all_cached}
    full_activities = [
        label_to_obj.get(lbl.lower(), {"label": lbl, "duration": "1h", "time": "any", "vibe": "any"})
        for lbl in selected_activities
    ]

    acts_per_day = PACE_DENSITY.get(selected_pace, 3)
    place_order = route_arc.get("place_order") or [
        p.get("name", p.get("id", ""))
        for cat in (state.get("place_cards") or [])
        for p in cat.get("places", [])
    ]

    prompt = (
        f"Create a {trip_duration}-day itinerary for {destination}. "
        f"Place visit order: {place_order}. "
        f"Pace: {selected_pace} (~{acts_per_day} activities per day). "
        f"Activities to schedule (with duration and preferred time): {json.dumps(full_activities)}. "
        f"Rules: "
        f"1. Schedule morning activities (time='morning') before noon, evening ones after 4pm. "
        f"2. Spread activities across days — do not put more than {acts_per_day} per day. "
        f"3. Group activities at the same place on the same day when possible. "
        f"4. Give each day a short punchy title based on the places visited. "
        f"5. Add a one-sentence 'note' per day (e.g. arrival tip, pace note). "
        f"Return a JSON array of day objects. Each day: "
        f"day (int), title (str), activities (list of {{time, activity, place, duration}}), note (str). "
        f"Return only valid JSON, no explanation."
    )

    try:
        parsed = await _groq_post(prompt, max_tokens=800)
        if isinstance(parsed, list) and parsed:
            logger.info(f"[day_planner] day_plan ✓ {len(parsed)} days for {destination}")
            return parsed
    except Exception as e:
        logger.error(f"[day_planner] day_plan Groq failed: {e} — distributing evenly")

    chunks = [selected_activities[i::trip_duration] for i in range(trip_duration)]
    return [
        {"day": i + 1, "title": f"Day {i + 1}", "activities": [{"activity": a} for a in chunk], "note": ""}
        for i, chunk in enumerate(chunks)
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/services/test_sprint6_day_plan.py -k "day_plan" -v 2>&1
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/day_planner.py tests/unit/services/test_sprint6_day_plan.py
git commit -m "feat(sprint6): add generate_day_plan to day_planner.py"
```

---

## Task 4: `generate_destination_brief`

**Files:**
- Modify: `app/services/day_planner.py` (append `generate_destination_brief`)
- Modify: `tests/unit/services/test_sprint6_day_plan.py` (append tests)

**Interfaces:**
- Produces: `generate_destination_brief(state: dict) -> dict`
- Brief shape: `{"weather", "language_tip", "lingo": list[str], "transport", "local_events", "permits", "safety", "currency"}`
- Fallback: `{"destination": str, "note": "Destination intel unavailable — check local sources on arrival."}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/services/test_sprint6_day_plan.py`:

```python
# ── Task 4: generate_destination_brief ───────────────────────────────────────

_BRIEF_STATE = {
    "destination": "Goa",
    "experience_types": ["beach_coast"],
    "trip_who": "solo",
    "travel_intent": None,
}

_GROQ_BRIEF = json.dumps({
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
    "safety": "Swim only at flagged beaches — riptides common elsewhere.",
    "currency": "Beach shacks are cash-only. ATMs in Calangute.",
})


@pytest.mark.asyncio
async def test_generate_destination_brief_returns_all_keys():
    from app.services.day_planner import generate_destination_brief
    with patch("app.services.day_planner.tavily_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.day_planner.aiohttp.ClientSession", _make_session_mock(_GROQ_BRIEF)):
        result = await generate_destination_brief(_BRIEF_STATE)
    assert "weather" in result
    assert "language_tip" in result
    assert "lingo" in result
    assert isinstance(result["lingo"], list) and len(result["lingo"]) >= 3
    assert "transport" in result
    assert "safety" in result


@pytest.mark.asyncio
async def test_generate_destination_brief_fallback_on_groq_failure():
    from app.services.day_planner import generate_destination_brief
    bad_session = MagicMock()
    bad_session.__aenter__ = AsyncMock(side_effect=Exception("Groq down"))
    bad_session.__aexit__ = AsyncMock(return_value=False)
    with patch("app.services.day_planner.tavily_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.day_planner.aiohttp.ClientSession", MagicMock(return_value=bad_session)):
        result = await generate_destination_brief(_BRIEF_STATE)
    assert result["destination"] == "Goa"
    assert "note" in result


@pytest.mark.asyncio
async def test_generate_destination_brief_proceeds_when_tavily_fails():
    """Tavily error does not raise — Groq uses own knowledge, brief is still returned."""
    from app.services.day_planner import generate_destination_brief
    with patch("app.services.day_planner.tavily_search", new_callable=AsyncMock, side_effect=Exception("Tavily down")), \
         patch("app.services.day_planner.aiohttp.ClientSession", _make_session_mock(_GROQ_BRIEF)):
        result = await generate_destination_brief(_BRIEF_STATE)
    assert "weather" in result  # brief still returned via Groq
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/services/test_sprint6_day_plan.py -k "destination_brief" -v 2>&1 | head -20
```

Expected: FAIL — `ImportError: cannot import name 'generate_destination_brief'`

- [ ] **Step 3: Add `generate_destination_brief` to `app/services/day_planner.py`**

Append after `generate_day_plan`:

```python
async def generate_destination_brief(state: dict) -> dict:
    """Generate destination intel via parallel Tavily searches + Groq synthesis."""
    destination = state.get("destination", "")
    experience_types: list[str] = state.get("experience_types") or []
    trip_who = state.get("trip_who")

    month = datetime.now().strftime("%B")
    results = await asyncio.gather(
        tavily_search(f"{destination} travel tips weather permits {month}"),
        tavily_search(f"{destination} local events things to know for tourists"),
        return_exceptions=True,
    )
    snippets = ""
    for r in results:
        if isinstance(r, list):
            snippets += " ".join(item.get("content", "")[:300] for item in r[:4])

    context_line = f"Context from recent travel sources: {snippets[:2000]}" if snippets else ""
    prompt = (
        f"You are a local travel expert for {destination}. "
        f"Group: {trip_who or 'solo'}. Experience: {', '.join(experience_types) or 'general'}. "
        f"{context_line} "
        f"Generate a destination brief with these exact keys: "
        f"weather (current conditions + what to pack), "
        f"language_tip (dominant language + how English is used), "
        f"lingo (list of 3-5 practical phrases — greetings, honorifics like uncle/aunty equivalents, "
        f"bargaining words — format each as: 'phrase — when/how to use it'), "
        f"transport (best way to get around), "
        f"local_events (any notable events or festivals happening soon, or 'None currently known'), "
        f"permits (entry fees or permits required for selected places, or 'None required'), "
        f"safety (1 practical safety tip), "
        f"currency (cash vs card situation). "
        f"Return only valid JSON, no explanation."
    )

    try:
        parsed = await _groq_post(prompt, max_tokens=600)
        if isinstance(parsed, dict):
            logger.info(f"[day_planner] destination_brief ✓ for {destination}")
            return parsed
    except Exception as e:
        logger.error(f"[day_planner] destination_brief Groq failed: {e}")

    return {"destination": destination, "note": "Destination intel unavailable — check local sources on arrival."}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/services/test_sprint6_day_plan.py -k "destination_brief" -v 2>&1
```

Expected: 3 tests PASS

- [ ] **Step 5: Run all Sprint 6 unit tests**

```bash
pytest tests/unit/services/test_sprint6_day_plan.py -v 2>&1 | tail -20
```

Expected: all 15 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/day_planner.py tests/unit/services/test_sprint6_day_plan.py
git commit -m "feat(sprint6): add generate_destination_brief to day_planner.py"
```

---

## Task 5: Wire stage_machine.py bridge functions

**Files:**
- Modify: `app/services/stage_machine.py` (lines 838–850 — replace 3 stubs)

**Interfaces:**
- Consumes: `generate_route_arcs`, `generate_day_plan`, `generate_destination_brief` from Tasks 2–4
- Produces: `build_route_arcs`, `build_day_plan`, `build_destination_brief` — same signatures as before, now delegating

- [ ] **Step 1: Replace the 3 stubs in `app/services/stage_machine.py`**

Find and replace the stub block at lines 838–850:

```python
async def build_route_arcs(state: dict) -> list[dict]:
    """Sprint 6: geographic journey arc generation."""
    return []


async def build_day_plan(state: dict) -> list[dict]:
    """Sprint 6: day-by-day plan generation from route arc + activities + pace."""
    return []


async def build_destination_brief(state: dict) -> dict:
    """Sprint 6: weather + events + permits + local language tips."""
    return {}
```

Replace with:

```python
async def build_route_arcs(state: dict) -> list[dict]:
    from app.services.day_planner import generate_route_arcs
    return await generate_route_arcs(state)


async def build_day_plan(state: dict) -> list[dict]:
    from app.services.day_planner import generate_day_plan
    return await generate_day_plan(state)


async def build_destination_brief(state: dict) -> dict:
    from app.services.day_planner import generate_destination_brief
    return await generate_destination_brief(state)
```

- [ ] **Step 2: Verify the full unit test suite still passes**

```bash
pytest tests/unit/services/ -v --tb=short 2>&1 | tail -20
```

Expected: same count as before (all Sprint 6 tests pass, no regressions)

- [ ] **Step 3: Commit**

```bash
git add app/services/stage_machine.py
git commit -m "feat(sprint6): wire build_route_arcs, build_day_plan, build_destination_brief as bridge functions"
```

---

## Task 6: Integration test — full pipeline to `open_day_planner`

**Files:**
- Create: `tests/integration/test_pipeline.py`

**Interfaces:**
- Consumes: all Tasks 1–5 being complete
- Uses: `httpx.AsyncClient` + `ASGITransport` against `app.api.server.app`; real LangGraph `SqliteSaver` checkpointer accumulates state across steps
- Mocks: `aiohttp.ClientSession` per module, `tavily_search`, `fetch_place_photos`, `area_cache.get_cached`, `area_cache.set_cached`

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_pipeline.py`:

```python
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


# ── Mock factories ─────────────────────────────────────────────────────────────

def _fixed_session(content: str):
    """aiohttp.ClientSession mock always returning content."""
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


# ── Full pipeline test ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_pipeline_to_day_planner():
    from app.api.server import app as fastapi_app

    THREAD_ID = str(uuid.uuid4())

    with patch("app.services.activity_options.aiohttp.ClientSession", _fixed_session(_ACTIVITIES_JSON)), \
         patch("app.services.area_cache.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.area_cache.set_cached", new_callable=AsyncMock), \
         patch("app.services.day_planner.aiohttp.ClientSession", _cycling_session([_ARCS_JSON, _PLAN_JSON, _BRIEF_JSON])), \
         patch("app.services.day_planner.tavily_search", new_callable=AsyncMock, return_value=[]), \
         patch("app.graph.nodes.responder.aiohttp.ClientSession", _fixed_session(_RESPONDER_TEXT)), \
         patch("app.utils.place_photos.fetch_place_photos", new_callable=AsyncMock, return_value=[]):

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
```

- [ ] **Step 2: Run the integration test**

```bash
pytest tests/integration/test_pipeline.py -v --tb=short 2>&1
```

Expected: 1 test PASS (`test_full_pipeline_to_day_planner`)

If it fails with a state routing error (wrong `action` at any step), add `-s` to see logs:

```bash
pytest tests/integration/test_pipeline.py -v -s 2>&1 | head -60
```

- [ ] **Step 3: Run full test suite for final check**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all Sprint 6 unit tests (15) + integration test (1) pass; no regressions in existing suite

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_pipeline.py
git commit -m "test(sprint6): full pipeline integration test — experience_type_selected to open_day_planner"
```

---

## Self-review notes

- **Spec section 2 (route arcs):** covered by Task 2 — `selected_places` filter, Groq prompt, `DEFAULT_ARCS` fallback ✓
- **Spec section 3 (day plan):** covered by Task 3 — Redis reconstruction, `PACE_DENSITY`, Groq prompt, even-distribution fallback ✓
- **Spec section 4 (destination brief):** covered by Task 4 — parallel Tavily, Groq synthesis, 8 keys including `lingo` as list ✓
- **Spec section 6 (`activities_confirmed` fix):** covered by Task 1 — `selected_places` set before clearing `pending_activities` ✓
- **Spec section 7 (`trip_duration_set`):** covered by Task 1 ✓
- **Spec section 8 (error handling):** each function returns its fallback constant on any Groq exception; Tavily exceptions caught by `asyncio.gather(return_exceptions=True)` and result is treated as empty ✓
- **Integration test step order:** matches spec section 5 verbatim ✓
- **`selected_places` in responder.py:** covered by Task 1 — persisted so LangGraph checkpointer carries it forward to `generate_route_arcs` ✓
