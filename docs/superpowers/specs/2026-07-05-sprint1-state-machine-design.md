# Sprint 1 — State Machine Foundation
**Date:** 2026-07-05  
**Scope:** B1, B7, B9, B13 from RoamMate_Spec.md  
**Goal:** Replace scattered if/else logic with a single adaptive stage resolver that knows where the conversation is regardless of what order the user took to get there.

---

## Problem

The backend has a rough `phase` field (DISCOVERY / PLANNING / IN_DESTINATION) but no fine-grained tracking of where in the conversation the user is. The responder decides what card to show next through scattered if/else conditions inline. This breaks the moment a user does anything non-linear — jumps ahead, skips a step, or types free text mid-flow.

Sprint 1 builds the plumbing that every future sprint depends on.

---

## What Sprint 1 Delivers

1. New `GraphState` fields for the full planning flow
2. `app/services/stage_machine.py` — `resolve_stage` + `determine_action`
3. API schema updated to accept Phase 0 structured fields
4. `responder.py` and `intent.py` wired to the stage machine
5. Dynamic experience chip generation (geo-filtered + live event enrichment)

---

## 1. New GraphState Fields

Added to `app/graph/state.py`. Existing fields are unchanged.

```python
# Phase 0 context — sent as structured fields from frontend
trip_mode: str | None          # "plan" | "now"
trip_who: str | None           # "solo" | "couple" | "friends" | "family_kids" | "family_elder"
trip_season: str | None        # "summer" | "monsoon" | "winter" | "flex"

# Experience type — multi-select, dynamic chips
experience_types: list[str]    # e.g. ["hills_nature", "festival_events"]

# Stage tracking
conversation_stage: str | None # set by resolve_stage each turn, written to state

# Trip planning fields
trip_duration: int | None      # number of days
selected_activities: list[str] # activities chosen at place level
route_arc: dict | None         # chosen geographic journey direction
day_plan: list[dict] | None    # generated day-by-day outline
destination_brief: dict | None # weather, alerts, events, permits, language tips

# Context buckets — populated in later sprints
card_context_by_vibe: dict     # { "adv": { "text": "bad knee", "tags": ["accessible"] } }
free_text_context: dict        # constraints from free text across all turns
in_destination_saves: list[str] # place ids saved from in-destination tab
```

---

## 2. API Schema Changes

`app/api/schemas.py` — `ChatRequest` gets three new optional fields:

```python
class ChatRequest(BaseModel):
    message: str
    thread_id: str
    location: LocationPayload | None = None
    card_action: str | None = None
    card_data: dict | None = None
    # New — Phase 0 structured fields sent by frontend
    trip_mode: str | None = None
    trip_who: str | None = None
    trip_season: str | None = None
```

All three are optional so existing API calls do not break. The backend reads them on the first message and writes them into `GraphState`. On subsequent turns they are ignored — state already has them from checkpointing.

`ChatResponse` gets no new fields. `action` and `payload` already exist; Sprint 1 ensures they are always populated.

**Frontend responsibility:** Phase 0 sends `trip_mode`, `trip_who`, `trip_season` as explicit fields in the API request body alongside the message string. The opening message text (e.g. "Going soon, solo — help me find somewhere to go") is generated dynamically by the LLM for display only. The backend never parses it.

---

## 3. New Action Types

New actions added to the known set (on top of existing `show_vibe_cards`, `show_place_cards`, `show_pace_options`, `show_route_cards`):

| Action | Payload shape | Triggered when |
|--------|--------------|----------------|
| `show_experience_chips` | `{ chips: [{ id, label, description, live_hook? }] }` | No destination, no experience type yet |
| `show_destination_chips` | `{ destinations: [{ name, distance, reason }] }` | Experience type known, no destination |
| `ask_trip_duration` | `{}` | Places shown, no trip duration yet |
| `show_activity_options` | `{ activities: [...] }` | Places confirmed, duration known |
| `show_route_arcs` | `{ arcs: [...] }` | Pace selected |
| `open_day_planner` | `{ plan: [...], brief: {...} }` | Route arc selected — opens separate tab |

---

## 4. The Full Planning Chain

The conversation can reach any stage in any order. `resolve_stage` always returns the correct stage from current state — it does not care about the path taken.

```
Phase 0  (trip_mode, trip_who, trip_season)
    ↓
[Branch A — no destination]
    show_experience_chips  (geo-filtered + live event hooks)
    user selects one or more chips
    show_destination_chips  (Tavily + Reddit fetch using origin + experience_types + who + season)
    user taps a destination

[Branch B — destination already known from free text]
    skip both chip stages entirely

    ↓ (both branches meet here)
    
show_vibe_cards  (destination-specific from blog signals + live events at that place)
    ↓
show_place_cards  (ranked by vibe + crowd fit + quality, with photos)
    ↓
ask_trip_duration  ("How many days are you planning?")
    ↓
show_activity_options  (what to do at selected places — hiking, food trail, nightlife etc.)
    ↓
show_pace_options  (Slow drifter · Mix it up · Power day)
    ↓
show_route_arcs  (geographic journey narrative — South→North Goa, Central→Casinos→Beaches)
    ↓
open_day_planner  (opens separate tab — default plan + edit section + live data)
```

**Adaptive rule:** If the user jumps ahead ("just give me places in Coorg"), `resolve_stage` returns `destination_known` directly, skipping experience and destination chip stages. No context is lost. Missing fields default gracefully.

---

## 5. Dynamic Experience Chips

Experience chips are never hardcoded on the frontend. The backend builds the chip list and sends it in `payload.chips`. The frontend renders whatever arrives.

**Chip generation — two parallel fetches:**

```
1. Filter base set by geo relevance    (fast, no API call)
   — uses origin to determine which of the 6 base categories make sense
   — e.g. no "Beach & Coast" if origin is landlocked with no reachable coast

2. Tavily / events search near origin  (async, slight latency acceptable here)
   — surfaces live events or seasonal happenings as live_hook on relevant chips
   — e.g. "Hills & Nature" chip gets live_hook: "Kasol Nomad Festival this month"
```

Both run with `asyncio.gather`. Results are merged before responding.

**Base categories (backend fallback when no origin context):**

| ID | Label |
|----|-------|
| `beach_coast` | Beach & Coast |
| `hills_nature` | Hills & Nature |
| `small_town` | Small Town |
| `festival_events` | Festival & Events |
| `new_city` | New City |
| `retreat_rest` | Retreat & Rest |

**Chip payload shape:**
```json
{
  "chips": [
    {
      "id": "hills_nature",
      "label": "Hills & Nature",
      "description": "Altitude, trails, forests, quiet",
      "live_hook": "Kasol Nomad Festival this month in Himachal"
    },
    {
      "id": "festival_events",
      "label": "Festival & Events",
      "description": "Something happening, cultural moment",
      "live_hook": "Sunburn Festival this weekend in Goa"
    }
  ]
}
```

**Multi-select + combination logic:** User can pick one or two chips. Destination suggestions use the combination to find places that satisfy multiple interests simultaneously — e.g. `hills_nature` + `festival_events` → Kasol, Shillong, Mcleodganj (trekking + music festivals), not just either one.

---

## 6. The Stage Machine

`app/services/stage_machine.py` — shared module imported by both `responder.py` and `intent.py`.

### resolve_stage

```python
def resolve_stage(state: dict) -> str:
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
```

### determine_action

```python
async def determine_action(stage: str, state: dict) -> tuple[str | None, dict | None]:
    if stage == "experience_type_unknown":
        chips = build_experience_chips(state)        # geo-filter + live hook fetch
        return "show_experience_chips", {"chips": chips}

    if stage == "experience_type_known":
        destinations = fetch_destination_suggestions(state)  # Tavily + Reddit
        return "show_destination_chips", {"destinations": destinations}

    if stage == "destination_known":
        vibes = fetch_vibe_cards(state)              # blog signals for destination
        return "show_vibe_cards", {"vibes": vibes}

    if stage == "vibe_selected":
        places = state.get("ranked_places", [])
        return "show_place_cards", {"places": places}

    if stage == "duration_pending":
        return "ask_trip_duration", {}               # plain text response, no card

    if stage == "places_shown":
        activities = build_activity_options(state)
        return "show_activity_options", {"activities": activities}

    if stage == "activities_selected":
        return "show_pace_options", {}

    if stage == "pace_selected":
        arcs = build_route_arcs(state)
        return "show_route_arcs", {"arcs": arcs}

    if stage == "route_arc_selected":
        plan = build_day_plan(state)
        brief = build_destination_brief(state)
        return "open_day_planner", {"plan": plan, "brief": brief}

    return None, None
```

`build_experience_chips`, `fetch_destination_suggestions`, `fetch_vibe_cards`, `build_activity_options`, `build_route_arcs`, `build_day_plan`, `build_destination_brief` are helper functions within the same module. Their implementations are Sprint 2+ work — Sprint 1 defines the signatures only.

---

## 7. Responder Wiring

`app/graph/nodes/responder.py` — at the end of every text turn:

```python
from app.services.stage_machine import resolve_stage, determine_action

stage = resolve_stage(state)
action, payload = determine_action(stage, state)

return {
    **state,
    "conversation_stage": stage,
    "response": intro_text,
    "action": action,
    "payload": payload,
}
```

---

## 8. Intent Handler Wiring

`app/graph/nodes/intent.py` — when a card action comes in:

```python
from app.services.stage_machine import resolve_stage, determine_action

# After updating state from card_action (vibes_selected, destination_selected, etc.)
stage = resolve_stage(updated_state)
action, payload = determine_action(stage, updated_state)

return {
    **updated_state,
    "conversation_stage": stage,
    "action": action,
    "payload": payload,
    "skip_graph": True,    # signal to short-circuit planning/discovery nodes
}
```

Card action turns resolve their own next action without running the full graph. The `skip_graph` flag gates the planning and discovery nodes in the graph builder.

---

## 9. Destination Intelligence Brief

Populated when destination is confirmed. Refreshed if trip dates change. Sent to the frontend as part of `open_day_planner` payload and available in the day planner tab.

```python
destination_brief = {
    "weather": {
        "summary": "Partly cloudy · 31°C · No rain next 5 days",
        "warning": None   # or "Landslide risk on NH road to Kasol"
    },
    "alerts": [
        "NH66 roadworks near Panaji — delays likely Tue–Thu"
    ],
    "events": [
        { "name": "Sunburn Festival", "date": "Dec 28–30", "location": "Vagator Beach" }
    ],
    "permits": {
        "required": False,
        "note": "Carry government ID for hotel check-in"
    },
    "language": {
        "local": "Konkani / Marathi",
        "phrases": [
            { "phrase": "Deva borem korum", "meaning": "God bless you (greeting)" },
            { "phrase": "Kitlo zaala?",     "meaning": "How much? (bargaining)" },
            { "phrase": "Bore asa",         "meaning": "It's good" }
        ]
    }
}
```

**Data sources:**

| Field | Source |
|-------|--------|
| Weather + warning | OpenWeatherMap |
| Alerts | Tavily news search scoped to destination |
| Events | Tavily events search for destination + trip dates |
| Permits | Tavily + curated rules (Inner Line Permit, PAP etc.) |
| Language phrases | LLM generated — destination → local language → 8–10 phrases |

---

## 10. Day Planner Tab

A separate frontend tab (not inline in chat). Opened by `open_day_planner` action.

**Default plan:** Generated from route arc + selected places + activities + pace. Backed by real data — not LLM hallucination.

**Edit section:** Every slot in the plan has:
- Remove button
- Swap button — opens "fill this slot" suggestions from live search
- Add button between slots — inserts a new activity from suggestions

**Live data layer (alongside the plan):**
- Weather forecast per day per location
- Events happening on each day of the trip
- Travel news / advisories relevant to the route
- Language tips for the destination

**Philosophy:** User gets a solid starting point. Nothing is locked. Every slot has alternatives. They never need to open another tab.

---

## 11. Conversation Stage Values

```
experience_type_unknown   — Phase 0 complete, no experience type or destination
experience_type_known     — experience chips selected, no destination yet
destination_known         — destination resolved (any path)
vibe_selected             — vibes confirmed (places may or may not be ranked yet)
duration_pending          — places shown, trip duration not yet given
places_shown              — places confirmed, duration known, ready for activities
activities_selected       — activities confirmed, ready for pace
pace_selected             — pace confirmed, ready for route arc
route_arc_selected        — route arc chosen, ready to open day planner
in_destination            — user is physically at location (existing phase)
```

---

## 12. What Sprint 1 Does NOT Build

Sprint 1 defines the structure and wiring. The following are stubs — signatures exist, implementations come in later sprints:

- `build_experience_chips` — chip list generation with geo filter + live hook (Sprint 2)
- `fetch_destination_suggestions` — Tavily + Reddit destination fetch (Sprint 2)
- `fetch_vibe_cards` — destination-specific vibe descriptions (Sprint 3)
- `build_activity_options` — activity suggestions per place (Sprint 4)
- `build_route_arcs` — geographic journey arc generation (Sprint 6)
- `build_day_plan` — day-by-day plan generation (Sprint 6)
- `build_destination_brief` — weather + events + permits + language (Sprint 6)
- Day planner tab frontend component (Sprint 6)
- Card context collection from expanded vibe/place cards (Sprint 3)
- Free text context tracking (Sprint 5)

---

## Files Changed in Sprint 1

| File | Change |
|------|--------|
| `app/graph/state.py` | Add new state fields |
| `app/api/schemas.py` | Add `trip_mode`, `trip_who`, `trip_season` to `ChatRequest` |
| `app/services/stage_machine.py` | New file — `resolve_stage`, `determine_action`, helper stubs |
| `app/graph/nodes/responder.py` | Wire in `resolve_stage` + `determine_action` |
| `app/graph/nodes/intent.py` | Wire in stage machine for card action turns |
| `app/graph/builder.py` | Add `skip_graph` edge condition |
