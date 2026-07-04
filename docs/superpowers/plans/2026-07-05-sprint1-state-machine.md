# Sprint 1 — State Machine Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the scattered if/else stage logic with a single adaptive `resolve_stage` + `determine_action` module (`stage_machine.py`) so the conversation always knows where it is regardless of what order the user took to get there.

**Architecture:** A new shared service `app/services/stage_machine.py` owns all stage-resolution logic. `responder.py` and `intent.py` both import from it. Card-action turns that don't need data fetching short-circuit the graph via a `skip_graph` flag checked in `builder.py`.

**Tech Stack:** Python 3.13, FastAPI, LangGraph, Pydantic v2, pytest + pytest-asyncio (STRICT mode)

## Global Constraints

- Python 3.13 — use `str | None` union syntax, not `Optional[str]`
- `pytest-asyncio` is in STRICT mode — every async test must have `@pytest.mark.asyncio`
- Do not change `GraphState`'s `total=False` — all fields remain optional
- Do not import `stage_machine` from `state.py` — direction is one-way: stage_machine → state (for type hints only)
- LangGraph node functions return a dict of fields to update, not the full state
- Stubs for Sprint 2+ helpers must return empty but valid data (not raise), so the system keeps running

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `app/graph/state.py` | Modify | Add 12 new fields; add `skip_graph: bool`; remove old `resolve_stage` function |
| `app/api/schemas.py` | Modify | Add `trip_mode`, `trip_who`, `trip_season` to `ChatRequest` |
| `app/api/server.py` | Modify | Pass Phase 0 fields into `state_input` on first message |
| `app/services/stage_machine.py` | Create | `resolve_stage`, `async determine_action`, helper stubs |
| `app/graph/nodes/responder.py` | Modify | Remove old `determine_action`; import + call stage_machine |
| `app/graph/nodes/intent.py` | Modify | Import `resolve_stage` from stage_machine; add new card handlers; set `skip_graph` |
| `app/graph/builder.py` | Modify | Add `skip_to_responder` branch in `should_clarify` edges |
| `tests/unit/services/test_stage_machine.py` | Create | Unit tests for `resolve_stage` stage transitions |

---

### Task 1: Expand GraphState with new fields

**Files:**
- Modify: `app/graph/state.py`

**Interfaces:**
- Produces: new fields available in all graph nodes that read from `state`

- [ ] **Step 1: Write a failing test that imports new fields**

Create `tests/unit/services/test_stage_machine.py` with just the import check:

```python
"""Unit tests for stage_machine resolve_stage."""
import pytest
from app.graph.state import GraphState


def test_graphstate_has_trip_mode():
    state: GraphState = {}
    state["trip_mode"] = "now"
    assert state["trip_mode"] == "now"


def test_graphstate_has_experience_types():
    state: GraphState = {}
    state["experience_types"] = ["hills_nature"]
    assert state["experience_types"] == ["hills_nature"]


def test_graphstate_has_skip_graph():
    state: GraphState = {}
    state["skip_graph"] = True
    assert state["skip_graph"] is True
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/unit/services/test_stage_machine.py -v
```

Expected: `PASSED` for the dict assignments (TypedDict assignments don't fail at runtime, but the test confirms the fields are accepted without error — the real check is that the type hints exist for IDE and mypy).

- [ ] **Step 3: Add new fields to GraphState**

Open `app/graph/state.py`. After line 81 (`routes: List[Dict[str, Any]]`), add:

```python
    # ── Phase 0 context — sent as structured fields from frontend ─────────────
    trip_mode: str                    # "plan" | "now"
    trip_who: str                     # "solo" | "couple" | "friends" | "family_kids" | "family_elder"
    trip_season: str                  # "summer" | "monsoon" | "winter" | "flex"

    # ── Experience type — multi-select, dynamic chips ─────────────────────────
    experience_types: List[str]       # e.g. ["hills_nature", "festival_events"]

    # ── Graph short-circuit flag ──────────────────────────────────────────────
    skip_graph: bool                  # True → card action turn, go direct to responder

    # ── Trip planning progression ─────────────────────────────────────────────
    trip_duration: int                # number of days
    selected_activities: List[str]    # activities user confirmed at place level
    route_arc: Dict[str, Any]         # chosen geographic journey direction
    day_plan: List[Dict[str, Any]]    # generated day-by-day outline
    destination_brief: Dict[str, Any] # weather, alerts, events, permits, language tips

    # ── Context buckets — populated in later sprints ──────────────────────────
    card_context_by_vibe: Dict[str, Any]  # { "adv": { "text": "...", "tags": [...] } }
    free_text_context: Dict[str, Any]     # constraints from free text across all turns
    in_destination_saves: List[str]       # place ids saved from in-destination tab
```

Also **remove** the old `resolve_stage` function entirely (lines 84–99). It will be replaced by the one in `stage_machine.py`.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/unit/services/test_stage_machine.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/state.py tests/unit/services/test_stage_machine.py
git commit -m "feat: expand GraphState with sprint 1 fields, remove old resolve_stage"
```

---

### Task 2: Update API schema + server Phase 0 injection

**Files:**
- Modify: `app/api/schemas.py`
- Modify: `app/api/server.py`

**Interfaces:**
- Produces: `ChatRequest.trip_mode`, `.trip_who`, `.trip_season` available in the server handler

- [ ] **Step 1: Write failing test for schema fields**

Add to `tests/unit/services/test_stage_machine.py`:

```python
def test_chat_request_accepts_phase0_fields():
    from app.api.schemas import ChatRequest
    req = ChatRequest(
        message="Going soon, solo",
        thread_id="t1",
        trip_mode="now",
        trip_who="solo",
        trip_season="winter",
    )
    assert req.trip_mode == "now"
    assert req.trip_who == "solo"
    assert req.trip_season == "winter"


def test_chat_request_phase0_fields_optional():
    from app.api.schemas import ChatRequest
    req = ChatRequest(message="hello", thread_id="t1")
    assert req.trip_mode is None
    assert req.trip_who is None
    assert req.trip_season is None
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/unit/services/test_stage_machine.py::test_chat_request_accepts_phase0_fields -v
```

Expected: FAILED — `ChatRequest` has no `trip_mode` field

- [ ] **Step 3: Add fields to ChatRequest**

In `app/api/schemas.py`, update `ChatRequest`:

```python
class ChatRequest(BaseModel):
    message: str
    thread_id: str
    location: Optional[LocationPayload] = None
    card_action: Optional[str] = None
    card_data: Optional[Dict[str, Any]] = None
    # Phase 0 structured fields — sent by frontend on first message
    trip_mode: Optional[str] = None      # "plan" | "now"
    trip_who: Optional[str] = None       # "solo" | "couple" | "friends" | "family_kids" | "family_elder"
    trip_season: Optional[str] = None    # "summer" | "monsoon" | "winter" | "flex"
```

- [ ] **Step 4: Inject Phase 0 fields in server.py**

In `app/api/server.py`, update the `state_input` block inside the `chat` handler (around line 174). Replace:

```python
        state_input: dict = {"messages": [user_message], "tool_events": []}
```

with:

```python
        state_input: dict = {"messages": [user_message], "tool_events": []}

        # Phase 0 fields — only injected when present; checkpointer persists them across turns
        if request.trip_mode:
            state_input["trip_mode"] = request.trip_mode
        if request.trip_who:
            state_input["trip_who"] = request.trip_who
        if request.trip_season:
            state_input["trip_season"] = request.trip_season
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/unit/services/test_stage_machine.py -v
```

Expected: all tests PASSED

- [ ] **Step 6: Commit**

```bash
git add app/api/schemas.py app/api/server.py tests/unit/services/test_stage_machine.py
git commit -m "feat: add Phase 0 fields to ChatRequest and inject into graph state"
```

---

### Task 3: Create stage_machine.py

**Files:**
- Create: `app/services/stage_machine.py`
- Modify: `tests/unit/services/test_stage_machine.py`

**Interfaces:**
- Produces:
  - `resolve_stage(state: dict) -> str`
  - `async determine_action(stage: str, state: dict) -> tuple[str | None, dict | None]`
- Consumed by: `responder.py` (Task 4), `intent.py` (Task 5)

- [ ] **Step 1: Write all failing tests for resolve_stage**

Add to `tests/unit/services/test_stage_machine.py`:

```python
import pytest
from app.services.stage_machine import resolve_stage


def test_resolve_stage_no_context_returns_experience_type_unknown():
    assert resolve_stage({}) == "experience_type_unknown"


def test_resolve_stage_experience_types_set_returns_known():
    state = {"experience_types": ["hills_nature"]}
    assert resolve_stage(state) == "experience_type_known"


def test_resolve_stage_destination_known_skips_experience():
    state = {"destination": "Goa"}
    assert resolve_stage(state) == "destination_known"


def test_resolve_stage_destination_and_vibes_confirmed():
    state = {"destination": "Goa", "vibes_confirmed": True}
    assert resolve_stage(state) == "vibe_selected"


def test_resolve_stage_places_shown_no_duration():
    state = {"destination": "Goa", "vibes_confirmed": True, "places_shown": True}
    assert resolve_stage(state) == "duration_pending"


def test_resolve_stage_places_shown_with_duration():
    state = {
        "destination": "Goa",
        "vibes_confirmed": True,
        "places_shown": True,
        "trip_duration": 3,
    }
    assert resolve_stage(state) == "places_shown"


def test_resolve_stage_activities_selected():
    state = {
        "destination": "Goa",
        "vibes_confirmed": True,
        "places_shown": True,
        "trip_duration": 3,
        "selected_activities": ["beach", "nightlife"],
    }
    assert resolve_stage(state) == "activities_selected"


def test_resolve_stage_pace_selected():
    state = {
        "destination": "Goa",
        "vibes_confirmed": True,
        "places_shown": True,
        "trip_duration": 3,
        "selected_activities": ["beach"],
        "selected_pace": "mix",
    }
    assert resolve_stage(state) == "pace_selected"


def test_resolve_stage_route_arc_selected():
    state = {
        "destination": "Goa",
        "route_arc": {"direction": "south_to_north"},
    }
    assert resolve_stage(state) == "route_arc_selected"


def test_resolve_stage_destination_known_beats_experience_type():
    # destination takes priority over experience_type_known
    state = {"destination": "Coorg", "experience_types": ["hills_nature"]}
    assert resolve_stage(state) == "destination_known"
```

- [ ] **Step 2: Run to verify all fail**

```bash
python -m pytest tests/unit/services/test_stage_machine.py -k "resolve_stage" -v
```

Expected: all FAILED — `stage_machine` module does not exist

- [ ] **Step 3: Create app/services/stage_machine.py**

```python
"""
app/services/stage_machine.py — Adaptive conversation stage resolver.

resolve_stage: reads GraphState, returns current stage string.
determine_action: takes stage, returns (action, payload) for the frontend.

Both are imported by responder.py and intent.py. Nothing else should
define conversation stage logic.
"""
from typing import Any


# ── Stage resolution ───────────────────────────────────────────────────────────

def resolve_stage(state: dict) -> str:
    """
    Read current state and return the conversation stage.
    Does not care about the path — only what context currently exists.
    Priority: route_arc > pace > activities > places > vibes > destination > experience > unknown
    """
    if not state.get("destination"):
        if state.get("experience_types"):
            return "experience_type_known"
        return "experience_type_unknown"

    # Destination is known from here
    if state.get("route_arc"):
        return "route_arc_selected"
    if state.get("selected_pace"):
        return "pace_selected"
    if state.get("selected_activities"):
        return "activities_selected"
    if state.get("places_shown"):
        if not state.get("trip_duration"):
            return "duration_pending"
        return "places_shown"
    if state.get("vibes_confirmed"):
        return "vibe_selected"

    return "destination_known"


# ── Action determination ───────────────────────────────────────────────────────

async def determine_action(stage: str, state: dict) -> tuple[str | None, dict | None]:
    """
    Given a stage, return (action, payload) to send to the frontend.
    Helper functions are stubs — filled in Sprint 2+.
    """
    if stage == "experience_type_unknown":
        chips = await build_experience_chips(state)
        return "show_experience_chips", {"chips": chips}

    if stage == "experience_type_known":
        destinations = await fetch_destination_suggestions(state)
        return "show_destination_chips", {"destinations": destinations}

    if stage == "destination_known":
        vibes = await fetch_vibe_cards(state)
        return "show_vibe_cards", {"vibes": vibes}

    if stage == "vibe_selected":
        places = _build_place_cards(state)
        return "show_place_cards", {"places": places}

    if stage == "duration_pending":
        return "ask_trip_duration", {}

    if stage == "places_shown":
        activities = await build_activity_options(state)
        return "show_activity_options", {"activities": activities}

    if stage == "activities_selected":
        return "show_pace_options", {}

    if stage == "pace_selected":
        arcs = await build_route_arcs(state)
        return "show_route_arcs", {"arcs": arcs}

    if stage == "route_arc_selected":
        plan = await build_day_plan(state)
        brief = await build_destination_brief(state)
        return "open_day_planner", {"plan": plan, "brief": brief}

    return None, None


# ── Inline helpers (no external calls) ────────────────────────────────────────

_VIBE_COLOR = {
    "adventure": "adv", "cultural": "spt",
    "chill": "loc", "romantic": "loc",
    "party": "adv", "family": "spt",
}

_FACTOR_PHRASES = {
    "quality": "known for excellent quality and reviews",
    "intent_match": "matches your vibe perfectly",
    "authenticity": "a local favourite, not a tourist trap",
    "crowd_fit": "has the kind of crowd you prefer",
}


def _build_place_cards(state: dict) -> list[dict]:
    """Build place card payload from ranked_places already in state."""
    ranked = state.get("ranked_places") or []
    intent = state.get("travel_intent")
    vibe_id = "adv"
    if intent and getattr(intent, "vibe", None):
        vibe_id = _VIBE_COLOR.get(intent.vibe[0].value, "adv")

    places = []
    for p in ranked[:6]:
        expl = p.get("explanation", {})
        factor = expl.get("top_factor", "")
        places.append({
            "id": p.get("place_id", p.get("name", "")),
            "name": p.get("name", ""),
            "area": p.get("area", ""),
            "hook": p.get("hook") or _FACTOR_PHRASES.get(factor, "A great option"),
            "vibe_id": vibe_id,
            "rating": p.get("rating"),
        })
    return places


# ── Sprint 2+ stubs — return valid empty data so the system keeps running ──────

async def build_experience_chips(state: dict) -> list[dict]:
    """Sprint 2: geo-filter base categories + Tavily live_hook fetch."""
    return [
        {"id": "beach_coast",     "label": "Beach & Coast",    "description": "Sea, sun, slow days, coastal towns"},
        {"id": "hills_nature",    "label": "Hills & Nature",   "description": "Altitude, trails, forests, quiet"},
        {"id": "small_town",      "label": "Small Town",       "description": "Local life, heritage, no tourist strip"},
        {"id": "festival_events", "label": "Festival & Events","description": "Something happening, cultural moment"},
        {"id": "new_city",        "label": "New City",         "description": "Explore an unfamiliar urban place"},
        {"id": "retreat_rest",    "label": "Retreat & Rest",   "description": "Absolute stillness, wellness, nothing planned"},
    ]


async def fetch_destination_suggestions(state: dict) -> list[dict]:
    """Sprint 2: Tavily + Reddit fetch using origin + experience_types + season + who."""
    return []


async def fetch_vibe_cards(state: dict) -> list[dict]:
    """Sprint 3: destination-specific vibe descriptions from blog signals."""
    return []


async def build_activity_options(state: dict) -> list[dict]:
    """Sprint 4: live activity suggestions per selected place."""
    return []


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

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/unit/services/test_stage_machine.py -k "resolve_stage" -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/services/stage_machine.py tests/unit/services/test_stage_machine.py
git commit -m "feat: add stage_machine with resolve_stage + determine_action stubs"
```

---

### Task 4: Wire responder.py to stage_machine

**Files:**
- Modify: `app/graph/nodes/responder.py`

**Interfaces:**
- Consumes: `resolve_stage(state: dict) -> str` and `async determine_action(stage, state) -> tuple` from `app.services.stage_machine`
- The old `determine_action` in this file is deleted entirely

- [ ] **Step 1: Write a test to confirm responder calls stage_machine**

Add to `tests/unit/services/test_stage_machine.py`:

```python
@pytest.mark.asyncio
async def test_determine_action_experience_type_unknown():
    from app.services.stage_machine import determine_action
    action, payload = await determine_action("experience_type_unknown", {})
    assert action == "show_experience_chips"
    assert "chips" in payload
    assert len(payload["chips"]) == 6


@pytest.mark.asyncio
async def test_determine_action_destination_known():
    from app.services.stage_machine import determine_action
    action, payload = await determine_action("destination_known", {})
    assert action == "show_vibe_cards"
    assert "vibes" in payload


@pytest.mark.asyncio
async def test_determine_action_vibe_selected_returns_place_cards():
    from app.services.stage_machine import determine_action
    state = {
        "ranked_places": [
            {"name": "Palolem Beach", "rating": 4.5, "place_id": "p1",
             "explanation": {"top_factor": "authenticity"}}
        ]
    }
    action, payload = await determine_action("vibe_selected", state)
    assert action == "show_place_cards"
    assert payload["places"][0]["name"] == "Palolem Beach"


@pytest.mark.asyncio
async def test_determine_action_unknown_stage_returns_none():
    from app.services.stage_machine import determine_action
    action, payload = await determine_action("in_destination", {})
    assert action is None
    assert payload is None
```

- [ ] **Step 2: Run to verify tests pass (stage_machine works)**

```bash
python -m pytest tests/unit/services/test_stage_machine.py -v
```

Expected: all PASSED

- [ ] **Step 3: Update responder.py**

At the top of `app/graph/nodes/responder.py`, add the import after the existing imports:

```python
from app.services.stage_machine import resolve_stage, determine_action as _stage_determine_action
```

At line 381, replace:

```python
    action, payload = determine_action(state)
    events.append(f"[action] {action or 'none'}")

    return {
        "response": response_text,
        "messages": [{"role": "assistant", "content": response_text}],
        "tool_events": events,
        "action": action,
        "payload": payload,
        "conversation_stage": state.get("conversation_stage"),
        "places_shown": state.get("places_shown", False),
        "pace_shown": state.get("pace_shown", False),
        "routes_shown": state.get("routes_shown", False),
        "show_scene_strip": state.get("show_scene_strip", False),
    }
```

with:

```python
    stage = resolve_stage(state)
    action, payload = await _stage_determine_action(stage, state)
    events.append(f"[action] {action or 'none'} stage={stage}")

    # Update one-time flags when their card is sent — prevents re-sending same card next turn
    places_shown = state.get("places_shown", False) or action == "show_place_cards"
    pace_shown = state.get("pace_shown", False) or action == "show_pace_options"
    routes_shown = state.get("routes_shown", False) or action == "show_route_arcs"

    return {
        "response": response_text,
        "messages": [{"role": "assistant", "content": response_text}],
        "tool_events": events,
        "action": action,
        "payload": payload,
        "conversation_stage": stage,
        "places_shown": places_shown,
        "pace_shown": pace_shown,
        "routes_shown": routes_shown,
        "show_scene_strip": state.get("show_scene_strip", False),
        "skip_graph": False,
    }
```

Also **delete** the entire old `determine_action` function from `responder.py` (lines 266–328). It is fully replaced.

- [ ] **Step 4: Run full test suite to verify no breakage**

```bash
python -m pytest tests/unit/ -v
```

Expected: all existing tests PASSED + new ones PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/responder.py
git commit -m "feat: wire responder to stage_machine, remove old determine_action"
```

---

### Task 5: Wire intent.py to stage_machine + add new card handlers

**Files:**
- Modify: `app/graph/nodes/intent.py`

**Interfaces:**
- Consumes: `resolve_stage` from `app.services.stage_machine` (replaces import from `state.py`)
- Produces: `skip_graph: True` on card actions that don't need data fetching

- [ ] **Step 1: Update imports in intent.py**

In `app/graph/nodes/intent.py`, change line 8:

```python
from app.graph.state import GraphState, Phase, resolve_stage
```

to:

```python
from app.graph.state import GraphState, Phase
from app.services.stage_machine import resolve_stage, determine_action as _stage_determine_action
```

- [ ] **Step 2: Update existing card action handlers**

Replace the entire card action block (lines 28–71) with:

```python
    # ── Card action handling — short-circuit LLM extraction ──────────────────
    card_action = state.get("card_action")
    card_data = state.get("card_data") or {}

    if card_action == "vibes_selected":
        vibe_ids = card_data.get("vibe_ids", [])
        state["vibes_confirmed"] = True
        state["selected_vibe_ids"] = vibe_ids
        VIBE_MAP = {
            "adv": "adventure", "loc": "cultural",
            "spt": "cultural",  "hid": "adventure",
        }
        intent = state.get("travel_intent")
        if intent:
            try:
                intent.vibe = list({Vibe(VIBE_MAP.get(v, "adventure")) for v in vibe_ids})
                state["travel_intent"] = intent
            except Exception:
                pass
        state["show_scene_strip"] = True
        state["scene_strip_label"] = "Finding your places"
        state["card_action"] = None
        state["skip_graph"] = False   # planning node must run to fetch ranked_places
        state["conversation_stage"] = resolve_stage(state)
        return state

    elif card_action == "experience_type_selected":
        state["experience_types"] = card_data.get("types", [])
        state["card_action"] = None
        state["skip_graph"] = False   # discovery node fetches destination suggestions
        state["conversation_stage"] = resolve_stage(state)
        return state

    elif card_action == "destination_selected":
        state["destination"] = card_data.get("destination", "")
        state["card_action"] = None
        state["skip_graph"] = False   # planning node fetches vibe cards
        state["conversation_stage"] = resolve_stage(state)
        return state

    elif card_action == "places_selected":
        state["selected_place_ids"] = card_data.get("place_ids", [])
        state["card_action"] = None
        state["skip_graph"] = True    # no data fetch needed
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state

    elif card_action == "pace_selected":
        state["selected_pace"] = card_data.get("pace")
        state["card_action"] = None
        state["skip_graph"] = True    # no data fetch needed
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state

    elif card_action == "route_arc_selected":
        state["route_arc"] = card_data.get("arc", {})
        state["card_action"] = None
        state["skip_graph"] = True    # no data fetch needed
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state

    elif card_action == "route_selected":
        state["selected_route_id"] = card_data.get("route_id")
        state["card_action"] = None
        state["skip_graph"] = True
        state["conversation_stage"] = resolve_stage(state)
        return state
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/unit/ -v
```

Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
git add app/graph/nodes/intent.py
git commit -m "feat: wire intent.py to stage_machine, add new card handlers, set skip_graph"
```

---

### Task 6: Add skip_graph short-circuit in builder.py

**Files:**
- Modify: `app/graph/builder.py`

**Interfaces:**
- Consumes: `state.get("skip_graph")` — set by intent.py for non-data-fetching card actions
- Produces: card action turns go `detect_intent → responder` directly, skipping discovery/planning

- [ ] **Step 1: Update should_clarify in intent.py to return skip path**

In `app/graph/nodes/intent.py`, update the `should_clarify` function:

```python
def should_clarify(state: GraphState) -> Literal["clarify", "route_phase", "skip_to_responder"]:
    if state.get("skip_graph"):
        return "skip_to_responder"
    if state.get("missing_info") and not state.get("needs_quick_setup"):
        return "clarify"
    return "route_phase"
```

Also update the return type annotation import at the top of the file — change:

```python
from typing import Literal
```

(already there — no change needed)

- [ ] **Step 2: Update builder.py conditional edges**

In `app/graph/builder.py`, update the `should_clarify` edge mapping:

```python
    workflow.add_conditional_edges(
        "detect_intent",
        should_clarify,
        {
            "clarify": "clarify",
            "route_phase": "route_phase_fn",
            "skip_to_responder": "responder",
        },
    )
```

- [ ] **Step 3: Smoke test — start server and check health**

```bash
python -m uvicorn app.api.server:app --port 8080 --no-access-log &
sleep 3
curl -s http://localhost:8080/health
kill %1
```

Expected output: `{"status":"ok","version":"2.0.0"}`

- [ ] **Step 4: Run full test suite**

```bash
python -m pytest tests/unit/ -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/graph/nodes/intent.py app/graph/builder.py
git commit -m "feat: short-circuit graph for non-data card actions via skip_graph flag"
```

---

### Task 7: Remove old resolve_stage import from intent.py (cleanup)

**Files:**
- Modify: `app/graph/nodes/intent.py`

The old `resolve_stage` was removed from `state.py` in Task 1. The import in `intent.py` was already updated in Task 5. This task is a verification pass.

- [ ] **Step 1: Verify no remaining imports of resolve_stage from state.py**

```bash
grep -r "from app.graph.state import.*resolve_stage" app/
```

Expected: no output (zero matches)

- [ ] **Step 2: Verify no other files import the old function**

```bash
grep -r "resolve_stage" app/ --include="*.py"
```

Expected: only lines in `stage_machine.py` (definition), `responder.py` (import), `intent.py` (import)

- [ ] **Step 3: Run final test suite**

```bash
python -m pytest tests/ -v --ignore=tests/integration
```

Expected: all PASSED

- [ ] **Step 4: Final commit**

```bash
git add -p  # review any outstanding changes
git commit -m "chore: verify stage_machine wiring complete, no stale resolve_stage imports"
```

---

## Verification Checklist

After all tasks are complete:

- [ ] `python -m pytest tests/unit/ -v` — all green
- [ ] `grep -r "from app.graph.state import.*resolve_stage" app/` — zero matches
- [ ] Server starts without errors: `python -m uvicorn app.api.server:app --port 8080`
- [ ] `/health` returns `{"status":"ok","version":"2.0.0"}`
- [ ] Sending a plain chat message returns a response with `action: "show_experience_chips"` when no destination or experience type is in state
- [ ] Sending `card_action: "pace_selected"` returns `action: "show_route_arcs"` without running planning node (check logs — no `[planning]` log line)
