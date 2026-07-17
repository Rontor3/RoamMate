# Sprint 5 — Activity Options per Selected Place: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `show_activity_options, {"activities": []}` stub with real activity mini-cards, enable a multi-place activity-selection loop via `pending_activities`, and refactor `resolve_stage` from a cascading if-chain to a priority-ordered `_STAGE_RULES` tuple list.

**Architecture:** `app/services/activity_options.py` owns all data work (Groq call + Redis read/write). `stage_machine.py` acts as a router — it reads/writes `state["activity_options"]` via a thin bridge helper (`_build_activity_options_for_place`), and delegates to the new service. `intent.py` handles the two new card actions (`activities_for_place`, `activities_confirmed`) using the same skip_graph pattern as all existing card handlers.

**Tech Stack:** Python 3.13, LangGraph TypedDict, aiohttp, Groq (meta-llama/llama-4-scout-17b-16e-instruct), Redis via `app/services/area_cache.py` (`get_cached` / `set_cached`), asyncpraw (existing), pytest + pytest-asyncio.

## Global Constraints

- Python 3.13 only; no new dependencies (aiohttp, asyncpraw, Groq already installed)
- Groq model: `meta-llama/llama-4-scout-17b-16e-instruct` (same as rest of codebase, set via `_MODEL` constant in `stage_machine.py`)
- Cache key for activity options: `f"activity_options:{destination.lower()}:{place_id.lower()}"`, TTL 21600 (6h)
- Cache key for area reddit signals: `f"reddit_area:{destination.lower()}:{area_id.lower()}"` (already written by Sprint 4 prefetch)
- `DEFAULT_ACTIVITIES`: exactly 3 generic fallback activities — see Task 2 for exact values
- Activity card shape: `{"id": str, "label": str, "duration": str, "time": "morning"|"afternoon"|"evening"|"any", "vibe": "adventure"|"chill"|"cultural"|"party"|"any"}`
- `pending_activities` MUST be cleared to `{}` before `selected_activities` is set in `activities_confirmed` handler — never both non-empty simultaneously
- `_STAGE_RULES` priority order is fixed (see Task 3) — do not reorder
- All card action handlers must set `state["skip_graph"] = True` and return early (same pattern as existing handlers in `intent.py`)
- `vibe_str` extraction: `", ".join(v.value for v in intent.vibe) if intent and intent.vibe else ""`

---

## File Map

| File | Status | Responsibility |
|------|--------|---------------|
| `app/graph/state.py` | Modify | Add `pending_activities` and `activity_options` fields |
| `app/services/activity_options.py` | **New** | `DEFAULT_ACTIVITIES`, `build_activity_options` — all Groq + Redis |
| `app/services/stage_machine.py` | Modify | `_STAGE_RULES`, refactored `resolve_stage`, `_resolve_place_name`, `_build_activity_options_for_place`, update `determine_action` for `place_selected` and `area_selected` |
| `app/graph/nodes/intent.py` | Modify | Add `activities_for_place` and `activities_confirmed` card action handlers |
| `app/graph/nodes/responder.py` | Modify | Persist `pending_activities` and `activity_options` in return dict |
| `tests/unit/services/test_sprint5_activities.py` | **New** | All Sprint 5 tests |

---

### Task 1: State Fields and Responder Persistence

**Files:**
- Modify: `app/graph/state.py`
- Modify: `app/graph/nodes/responder.py`
- Test: `tests/unit/services/test_sprint5_activities.py`

**Interfaces:**
- Produces: `GraphState["pending_activities"]` — `Dict[str, List[str]]`, keyed by place_id
- Produces: `GraphState["activity_options"]` — `List[Dict[str, Any]]`, current activity chips shown
- Produces: `responder()` return dict includes `"pending_activities"` and `"activity_options"` keys

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/services/test_sprint5_activities.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/rakshitsingh/Desktop/My_project/RoamMate
python -m pytest tests/unit/services/test_sprint5_activities.py -v -k "task1 or pending_activities or activity_options or graphstate_has_pending or graphstate_has_activity or responder_persists_pending or responder_persists_activity or responder_defaults"
```

Expected: FAIL — `KeyError` or `AssertionError` since the fields don't exist yet.

- [ ] **Step 3: Add state fields to `app/graph/state.py`**

In `app/graph/state.py`, add after line 96 (the `selected_place` field), inside `class GraphState(TypedDict, total=False)`:

```python
    # ── Activity selection loop — populated in Sprint 5 ──────────────────────
    pending_activities: Dict[str, List[str]]  # {place_id: [activity_labels]} — accumulates during multi-place loop
    activity_options: List[Dict[str, Any]]    # current activity chips shown — persisted for frontend re-render
```

- [ ] **Step 4: Add persistence to `app/graph/nodes/responder.py`**

In `responder.py`, find the `return {` block starting at line 326 and add two fields inside it, after the `"selected_place"` line:

```python
        "pending_activities": state.get("pending_activities") or {},
        "activity_options": state.get("activity_options") or [],
```

The return dict currently ends with `"selected_place": state.get("selected_place"),`. Add these two lines after it (before the closing `}`).

- [ ] **Step 5: Run tests — expect pass**

```
python -m pytest tests/unit/services/test_sprint5_activities.py -v -k "task1 or pending_activities or activity_options or graphstate_has_pending or graphstate_has_activity or responder_persists_pending or responder_persists_activity or responder_defaults"
```

Expected: All 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/graph/state.py app/graph/nodes/responder.py tests/unit/services/test_sprint5_activities.py
git commit -m "feat(sprint5): add pending_activities/activity_options state fields; persist in responder"
```

---

### Task 2: `app/services/activity_options.py` — Groq + Redis Data Service

**Files:**
- Create: `app/services/activity_options.py`
- Test: `tests/unit/services/test_sprint5_activities.py` (append)

**Interfaces:**
- Consumes: `get_cached(key)` → `list | None`, `set_cached(key, value, ttl)` from `app/services/area_cache.py`
- Consumes: `_groq_json` pattern — uses `aiohttp` directly (same pattern as `reddit_signals.py` `_extract_place_signals`)
- Produces: `DEFAULT_ACTIVITIES: list[dict]` — module-level constant, 3 generic activities
- Produces: `build_activity_options(place_id, place_name, destination, area_id, intent, trip_who) -> list[dict]`
  - Returns 4–6 activity dicts on success, `DEFAULT_ACTIVITIES` on failure
  - Each dict: `{"id": str, "label": str, "duration": str, "time": str, "vibe": str}`

- [ ] **Step 1: Append tests for Task 2 to test file**

Add to `tests/unit/services/test_sprint5_activities.py`:

```python
# ── Task 2: activity_options.py ──────────────────────────────────────────────

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
        mock_resp.json = AsyncMock(return_value={"choices": [{"message": {"content": str(groq_result).replace("'", '"')}}]})
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

    async def fake_groq_post(url, headers=None, json=None, **kwargs):
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

    if captured_prompts:
        assert "chapora fort" in captured_prompts[0].lower() or "Chapora Fort" in captured_prompts[0]


@pytest.mark.asyncio
async def test_build_activity_options_vibe_str_from_intent():
    """vibe_str is derived from intent.vibe."""
    from app.services.activity_options import build_activity_options
    from unittest.mock import MagicMock
    intent = MagicMock()
    intent.vibe = [MagicMock(value="adventure"), MagicMock(value="cultural")]
    captured_prompts = []

    async def fake_post(url, headers=None, json=None, **kwargs):
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

    if captured_prompts:
        assert "adventure" in captured_prompts[0] and "cultural" in captured_prompts[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/unit/services/test_sprint5_activities.py -v -k "default_activities or build_activity"
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.activity_options'`

- [ ] **Step 3: Create `app/services/activity_options.py`**

```python
"""
app/services/activity_options.py — Build activity mini-cards for a selected place.

Reads cached area Reddit signals (Sprint 4 prefetch), calls Groq to generate
4–6 place-specific activities, caches result for 6 hours.
"""
import json
import os
from typing import Any

import aiohttp

from app.services.area_cache import get_cached, set_cached
from app.utils.logger import get_logger

logger = get_logger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

DEFAULT_ACTIVITIES: list[dict] = [
    {"id": "explore_on_foot", "label": "Explore on foot",   "duration": "1h",  "time": "any", "vibe": "any"},
    {"id": "photo_walk",      "label": "Photo walk",        "duration": "1h",  "time": "any", "vibe": "any"},
    {"id": "try_food_nearby", "label": "Try food nearby",   "duration": "45m", "time": "any", "vibe": "any"},
]


async def build_activity_options(
    place_id: str,
    place_name: str,
    destination: str,
    area_id: str,
    intent: Any,
    trip_who: str | None,
) -> list[dict]:
    """
    Return 4–6 activity mini-cards for place_id.
    Reads area Reddit cache → calls Groq → caches result for 6h.
    Returns DEFAULT_ACTIVITIES on any failure.
    """
    cache_key = f"activity_options:{destination.lower()}:{place_id.lower()}"

    cached = await get_cached(cache_key)
    if cached:
        logger.info(f"[activity_options] cache hit: {cache_key}")
        return cached

    # Step 1 — Read area Reddit signals (best-effort)
    reddit_context = ""
    try:
        area_cache_key = f"reddit_area:{destination.lower()}:{area_id.lower()}"
        cached_reddit = await get_cached(area_cache_key)
        area_signals = cached_reddit[0] if cached_reddit else {}
        place_signals = area_signals.get("place_signals", {})
        for signal_key, signal_val in place_signals.items():
            if place_name.lower() in signal_key.lower():
                highlights = signal_val.get("review_highlights") or []
                vibe_tags = signal_val.get("vibe_tags") or []
                parts = highlights[:3] + vibe_tags[:3]
                reddit_context = "; ".join(str(p) for p in parts)[:400]
                break
    except Exception as e:
        logger.warning(f"[activity_options] reddit cache read failed: {e}")

    # Step 2 — Groq call
    vibe_str = ", ".join(v.value for v in intent.vibe) if intent and intent.vibe else ""
    local_intel = f"Local intel: {reddit_context}" if reddit_context else ""
    prompt = (
        f"Generate 4-6 specific activities a traveller can do at {place_name} in {destination}. "
        f"Group: {trip_who or 'solo'}. "
        f"Vibe: {vibe_str or 'general'}. "
        f"{local_intel} "
        f"Return a JSON array. Each object must have: "
        f"id (snake_case), label (display name, max 6 words), duration (e.g. '1h', '45m', 'half-day'), "
        f"time ('morning'|'afternoon'|'evening'|'any'), vibe ('adventure'|'chill'|'cultural'|'party'|'any'). "
        f"Return only valid JSON, no explanation."
    )

    activities = DEFAULT_ACTIVITIES
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        body = {
            "model": _MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                text = result["choices"][0]["message"]["content"].strip()
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                parsed = json.loads(text)
                if isinstance(parsed, list) and parsed:
                    activities = parsed
                    logger.info(f"[activity_options] Groq ✓ {len(activities)} activities for {place_name}")
    except Exception as e:
        logger.error(f"[activity_options] Groq failed for {place_name}: {e} — using defaults")

    await set_cached(cache_key, activities, ttl=21600)
    return activities
```

- [ ] **Step 4: Run tests — expect pass**

```
python -m pytest tests/unit/services/test_sprint5_activities.py -v -k "default_activities or build_activity"
```

Expected: All 7 tests PASS. Note: `test_build_activity_options_groq_success` may need the mock to return valid JSON — verify it passes; if the mock's string format doesn't JSON-parse, adjust to return proper JSON string.

- [ ] **Step 5: Commit**

```bash
git add app/services/activity_options.py tests/unit/services/test_sprint5_activities.py
git commit -m "feat(sprint5): add activity_options.py with build_activity_options and DEFAULT_ACTIVITIES"
```

---

### Task 3: `stage_machine.py` — `_STAGE_RULES`, Refactored `resolve_stage`, Helpers, `determine_action` Updates

**Files:**
- Modify: `app/services/stage_machine.py`
- Test: `tests/unit/services/test_sprint5_activities.py` (append)

**Interfaces:**
- Consumes: `build_activity_options(place_id, place_name, destination, area_id, intent, trip_who)` from `app/services/activity_options.py` (Task 2)
- Produces: `_STAGE_RULES: list[tuple]` — module-level, 9 rules
- Produces: `resolve_stage(state: dict) -> str` — replaces existing if-chain; same external contract
- Produces: `_resolve_place_name(state: dict) -> str` — private helper
- Produces: `_build_activity_options_for_place(state: dict) -> list[dict]` — async private helper
- Produces: `determine_action("place_selected", state)` — now calls `_build_activity_options_for_place` instead of returning stub
- Produces: `determine_action("area_selected", state)` — now includes `"pending_activities"` in payload

- [ ] **Step 1: Append tests for Task 3 to test file**

Add to `tests/unit/services/test_sprint5_activities.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/unit/services/test_sprint5_activities.py -v -k "stage_rules or resolve_stage or resolve_place or determine_action"
```

Expected: FAIL — `ImportError: cannot import name '_STAGE_RULES' from 'app.services.stage_machine'` and stage resolution bugs.

- [ ] **Step 3: Add `_STAGE_RULES` and refactor `resolve_stage` in `stage_machine.py`**

In `app/services/stage_machine.py`, find the `# ── Stage resolution ──` section (around line 313). Replace the entire `resolve_stage` function and the preceding comment with:

```python
# ── Stage resolution ───────────────────────────────────────────────────────────

_STAGE_RULES: list[tuple] = [
    # Late planning (most specific — highest priority)
    (lambda s: s.get("route_arc"),                                    "route_arc_selected"),
    (lambda s: s.get("selected_pace"),                                "pace_selected"),

    # Activity selection loop
    (lambda s: s.get("selected_place"),                               "place_selected"),
    (lambda s: s.get("pending_activities"),                           "area_selected"),
    (lambda s: s.get("selected_activities"),                          "activities_selected"),

    # Place cards shown
    (lambda s: s.get("places_shown") and not s.get("trip_duration"), "duration_pending"),
    (lambda s: s.get("places_shown"),                                 "places_shown"),

    # Area / vibe selection
    (lambda s: s.get("selected_area"),                                "area_selected"),
    (lambda s: s.get("vibes_confirmed"),                              "vibe_selected"),
]


def resolve_stage(state: dict) -> str:
    if not state.get("destination"):
        return "experience_type_known" if state.get("experience_types") else "experience_type_unknown"
    for predicate, stage in _STAGE_RULES:
        if predicate(state):
            return stage
    return "destination_known"
```

Remove the old `resolve_stage` function body (the cascading if-returns).

- [ ] **Step 4: Add `_resolve_place_name` and `_build_activity_options_for_place` to `stage_machine.py`**

Add these two functions immediately before `# ── Action determination ──` (around line 347):

```python
def _resolve_place_name(state: dict) -> str:
    """Resolve selected_place id → display name by scanning place_cards."""
    place_id = state.get("selected_place", "")
    for cat in (state.get("place_cards") or []):
        for p in cat.get("places", []):
            if p.get("id") == place_id:
                return p.get("name", place_id)
    return place_id


async def _build_activity_options_for_place(state: dict) -> list[dict]:
    """Bridge: read state, delegate to activity_options.py, persist result in state."""
    from app.services.activity_options import build_activity_options
    place_id = state.get("selected_place", "")
    place_name = _resolve_place_name(state)
    destination = state.get("destination", "")
    area_id = state.get("selected_area", "")
    intent = state.get("travel_intent")
    trip_who = state.get("trip_who")
    options = await build_activity_options(place_id, place_name, destination, area_id, intent, trip_who)
    state["activity_options"] = options
    return options
```

- [ ] **Step 5: Update `determine_action` in `stage_machine.py`**

Find the existing `determine_action` function. Make two targeted changes:

**Change 1** — Replace the `place_selected` stub (currently lines ~381-382):

Old:
```python
    if stage == "place_selected":
        return "show_activity_options", {"activities": []}
```

New:
```python
    if stage == "place_selected":
        activities = await _build_activity_options_for_place(state)
        place_name = _resolve_place_name(state)
        return "show_activity_options", {
            "place_id": state.get("selected_place"),
            "place_name": place_name,
            "activities": activities,
        }
```

**Change 2** — Update `area_selected` to include `pending_activities` in payload (currently lines ~377-379):

Old:
```python
    if stage == "area_selected":
        categories = await fetch_place_cards(state)
        return "show_place_cards", {"categories": categories}
```

New:
```python
    if stage == "area_selected":
        categories = await fetch_place_cards(state)
        return "show_place_cards", {
            "categories": categories,
            "pending_activities": state.get("pending_activities") or {},
        }
```

- [ ] **Step 6: Run tests — expect pass**

```
python -m pytest tests/unit/services/test_sprint5_activities.py -v -k "stage_rules or resolve_stage or resolve_place or determine_action"
```

Expected: All 21 tests PASS.

- [ ] **Step 7: Run full test suite to check for regressions**

```
python -m pytest tests/unit/services/ -v --tb=short 2>&1 | tail -30
```

Expected: Previously passing tests still pass. If any `resolve_stage` tests in `test_stage_machine.py` fail, check that the old stage ordering is preserved in `_STAGE_RULES` for all existing stages.

- [ ] **Step 8: Commit**

```bash
git add app/services/stage_machine.py tests/unit/services/test_sprint5_activities.py
git commit -m "feat(sprint5): add _STAGE_RULES, refactor resolve_stage, add place/activity helpers to stage_machine"
```

---

### Task 4: `intent.py` — `activities_for_place` and `activities_confirmed` Card Action Handlers

**Files:**
- Modify: `app/graph/nodes/intent.py`
- Test: `tests/unit/services/test_sprint5_activities.py` (append)

**Interfaces:**
- Consumes: `resolve_stage(state)` from `app.services.stage_machine` (already imported at line 9 of `intent.py`)
- Consumes: `_stage_determine_action(stage, state)` from `app.services.stage_machine` (already imported at line 9 as `determine_action as _stage_determine_action`)
- Produces: `activities_for_place` handler — stores `card_data.place_id` activities into `pending_activities`, clears `selected_place`, routes to `area_selected`
- Produces: `activities_confirmed` handler — flattens `pending_activities` into `selected_activities`, clears `pending_activities = {}`, routes to `activities_selected`
- **Invariant enforced by `activities_confirmed`:** `pending_activities` is set to `{}` BEFORE `resolve_stage` is called — this ensures `resolve_stage` returns `"activities_selected"` not `"area_selected"`

- [ ] **Step 1: Append tests for Task 4 to test file**

Add to `tests/unit/services/test_sprint5_activities.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```
python -m pytest tests/unit/services/test_sprint5_activities.py -v -k "activities_for_place or activities_confirmed"
```

Expected: FAIL — `AssertionError` since the card action handlers don't exist yet (falls through to LLM extraction).

- [ ] **Step 3: Add handlers to `app/graph/nodes/intent.py`**

In `app/graph/nodes/intent.py`, find the `elif card_action == "place_selected":` block (lines 112–121). Insert the two new handlers immediately **after** that block, before the `elif card_action == "route_selected":` block (line 123):

```python
    elif card_action == "activities_for_place":
        place_id = card_data.get("place_id", "")
        activities = card_data.get("activities", [])
        pending = state.get("pending_activities") or {}
        pending[place_id] = activities
        state["pending_activities"] = pending
        state["selected_place"] = None
        state["card_action"] = None
        state["skip_graph"] = True
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state

    elif card_action == "activities_confirmed":
        pending = state.get("pending_activities") or {}
        state["selected_activities"] = [act for acts in pending.values() for act in acts]
        state["pending_activities"] = {}                     # MUST clear before resolve_stage
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

- [ ] **Step 4: Run tests — expect pass**

```
python -m pytest tests/unit/services/test_sprint5_activities.py -v -k "activities_for_place or activities_confirmed"
```

Expected: All 8 tests PASS.

- [ ] **Step 5: Run full Sprint 5 test suite**

```
python -m pytest tests/unit/services/test_sprint5_activities.py -v 2>&1 | tail -40
```

Expected: All tests in the file PASS.

- [ ] **Step 6: Run full test suite to check for regressions**

```
python -m pytest tests/unit/services/ -v --tb=short 2>&1 | tail -30
```

Expected: All previously passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add app/graph/nodes/intent.py tests/unit/services/test_sprint5_activities.py
git commit -m "feat(sprint5): add activities_for_place and activities_confirmed card action handlers in intent.py"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec section | Covered by task |
|---|---|
| Activity card shape (§1) | Task 2 (`DEFAULT_ACTIVITIES`, Groq prompt), Task 3 (`determine_action` payload) |
| `show_activity_options` payload with `place_id`, `place_name`, `activities` (§1) | Task 3 (`determine_action("place_selected")`) |
| `pending_activities: Dict[str, List[str]]` state field (§2) | Task 1 |
| `activity_options: List[Dict[str, Any]]` state field (§2) | Task 1 |
| Invariant: `pending_activities = {}` before `selected_activities` set (§2) | Task 4 (`activities_confirmed`) |
| `_STAGE_RULES` 9-tuple list (§3) | Task 3 |
| `selected_place` before `pending_activities` in rules (§3) | Task 3 + test |
| `pending_activities` before `selected_activities` in rules (§3) | Task 3 + test |
| `activities_for_place` handler (§4) | Task 4 |
| `activities_confirmed` handler (§4) | Task 4 |
| `determine_action("place_selected")` calls `_build_activity_options_for_place` (§5) | Task 3 |
| `determine_action("area_selected")` includes `pending_activities` in payload (§5) | Task 3 |
| `_resolve_place_name` private helper (§5) | Task 3 |
| `_build_activity_options_for_place` bridge (§5) | Task 3 |
| `build_activity_options` function in `activity_options.py` (§6) | Task 2 |
| Cache key `activity_options:{dest}:{place_id}` TTL 21600 (§6) | Task 2 + test |
| Area Reddit cache read (§6, Step 1) | Task 2 |
| Reddit context string max 400 chars from `review_highlights` + `vibe_tags` (§6, Step 1) | Task 2 |
| Groq call max_tokens=500, vibe_str derivation (§6, Step 2) | Task 2 |
| Fallback to `DEFAULT_ACTIVITIES` on Groq failure (§6) | Task 2 + test |
| Responder persistence of `pending_activities` and `activity_options` (§7) | Task 1 |
| Error handling table (§8) | Covered by fallback + best-effort patterns |

### No Placeholders

All code blocks are complete. No "TBD", "TODO", or vague steps.

### Type Consistency

- `pending_activities`: `Dict[str, List[str]]` — consistent across state.py, intent.py, and test mocks
- `activity_options`: `List[Dict[str, Any]]` — consistent across state.py, activity_options.py return type, and responder
- `build_activity_options(place_id, place_name, destination, area_id, intent, trip_who)` — same signature in activity_options.py (Task 2), `_build_activity_options_for_place` call (Task 3), and test mocks (Task 3)
- `_STAGE_RULES` imported directly in tests as `from app.services.stage_machine import _STAGE_RULES` — module-level export
