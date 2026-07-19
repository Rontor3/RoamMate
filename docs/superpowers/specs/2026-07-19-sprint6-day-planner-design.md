# Sprint 6 — Day Planner + Destination Brief
**Date:** 2026-07-19
**Scope:** `app/services/day_planner.py` (new), `app/services/stage_machine.py` (3 stub bridges), `tests/unit/services/test_sprint6_day_plan.py` (new), `tests/integration/test_pipeline.py` (new)
**Goal:** Replace the three Sprint 6 stubs (`build_route_arcs`, `build_day_plan`, `build_destination_brief`) with real implementations, producing a `open_day_planner` payload that the frontend can render as a day-by-day itinerary with destination intel.

---

## Problem

After the user selects a pace and route arc, the system fires `open_day_planner` with `{"plan": [], "brief": {}}` — empty stubs. Sprint 6 fills these in: Groq generates 2–3 geographic route arc options, the user picks one (or reorders it on the frontend), then Groq schedules the confirmed activities into a day-by-day timed itinerary, and a Tavily + Groq pipeline produces a destination brief with weather, transport, events, permits, safety, currency, and local lingo.

---

## Context

Already in place from Sprints 1–5:
- `selected_activities: List[str]` — activity labels confirmed by user (labels only, not full objects)
- `pending_activities: Dict[str, List[str]]` — cleared after `activities_confirmed`; mapping of `{place_id: [labels]}` is gone
- `place_cards: List[Dict]` in state — has place IDs for Redis lookups

**New state field added in Sprint 6:**
- `selected_places: List[str]` — place IDs the user actually selected (not all place cards). Set by `activities_confirmed` before clearing `pending_activities`. Without this, `generate_route_arcs` would see all place cards instead of only the user's chosen places.
- `activity_options:{destination}:{place_id}` in Redis (TTL 21600) — full activity objects `{id, label, duration, time, vibe}` from Sprint 5
- `selected_pace: "slow" | "mix" | "power"` — activity density signal
- `trip_duration: int` — number of days
- `route_arc: Dict[str, Any]` — set when user taps a route arc card; contains `place_order`
- `day_plan: List[Dict[str, Any]]` and `destination_brief: Dict[str, Any]` — already in `GraphState`, Sprint 6 populates them
- `_groq_json(prompt, max_tokens)` — shared Groq helper in `stage_machine.py`
- `tavily_search(query)` — in `app/services/tavily_client.py`
- `get_cached` / `set_cached` in `app/services/area_cache.py`

Three stubs in `stage_machine.py` (lines 838–850):
```python
async def build_route_arcs(state: dict) -> list[dict]:     # returns []
async def build_day_plan(state: dict) -> list[dict]:       # returns []
async def build_destination_brief(state: dict) -> dict:    # returns {}
```

---

## 1. Architecture

`app/services/day_planner.py` owns all data work. The three stubs in `stage_machine.py` become thin bridges:

```python
# stage_machine.py
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

`day_planner.py` uses `aiohttp` directly for Groq (same pattern as `activity_options.py`) and imports `tavily_search` from `app.services.tavily_client`.

---

## 2. Route Arcs

### `generate_route_arcs(state: dict) -> list[dict]`

**Reads from state:** `destination`, `selected_area`, `place_cards`, `selected_places`, `experience_types`, `trip_who`

**Place name resolution:** Filter `place_cards` by `selected_places` IDs to get only the user's chosen places:
```python
selected_ids = set(state.get("selected_places") or [])
place_names = [
    p.get("name", p.get("id", ""))
    for cat in (state.get("place_cards") or [])
    for p in cat.get("places", [])
    if not selected_ids or p.get("id") in selected_ids
]
```
If `selected_places` is empty (edge case), fall back to all place cards.

**Groq call:** single call, `max_tokens=400`

**Prompt:**
```
You are a travel expert. The user is visiting {destination}, focusing on the {selected_area} area.
Places selected: {place_names}.
Experience types: {experience_types}. Group: {trip_who or "solo"}.
Trip duration: {trip_duration} days.

Generate 2-3 geographic route arcs — different orderings of these places that make physical sense
(e.g. north-to-south, coastal loop, base-camp style).

Return a JSON array. Each object: id (snake_case), label (short name), description (1 sentence — who it suits),
place_order (list of place names in visit order).
Return only valid JSON, no explanation.
```

**Arc shape:**
```json
{
  "id": "north_to_south",
  "label": "North → South",
  "description": "Classic flow — start lively, end chill at Palolem",
  "place_order": ["Chapora Fort", "Baga Beach", "Palolem Beach"]
}
```

**Fallback on Groq failure:** 2 generic arcs:
```python
DEFAULT_ARCS = [
    {
        "id": "selection_order",
        "label": "In Order",
        "description": "Visit places in the order you selected them",
        "place_order": place_names,          # from place_cards, original order
    },
    {
        "id": "reverse_order",
        "label": "Reverse Order",
        "description": "Start from the last place and work back",
        "place_order": list(reversed(place_names)),
    },
]
```

**Frontend contract:** User may reorder `place_order` before confirming. Backend accepts any `place_order` in the `route_arc_selected` card payload — no validation needed.

---

## 3. Day Plan

### `generate_day_plan(state: dict) -> list[dict]`

**Reads from state:** `route_arc`, `selected_activities`, `selected_pace`, `trip_duration`, `destination`, `place_cards`, `travel_intent`

### Step 1 — Reconstruct full activity objects from Redis

`selected_activities` stores only labels. `generate_day_plan` rebuilds full objects (duration, time, vibe) before scheduling:

```python
place_ids = [
    p.get("id") for cat in (state.get("place_cards") or [])
    for p in cat.get("places", [])
]
all_cached_activities: list[dict] = []
for place_id in place_ids:
    cache_key = f"activity_options:{destination.lower()}:{place_id.lower()}"
    cached = await get_cached(cache_key)
    if cached:
        all_cached_activities.extend(cached)

# Match by label (case-insensitive)
label_to_obj: dict[str, dict] = {
    a["label"].lower(): a for a in all_cached_activities
}
full_activities = [
    label_to_obj.get(label.lower(), {"label": label, "duration": "1h", "time": "any", "vibe": "any"})
    for label in selected_activities
]
```

Fallback when cache is cold: synthetic object `{"label": label, "duration": "1h", "time": "any", "vibe": "any"}` — Groq receives these and uses its own knowledge to schedule them reasonably.

### Step 2 — Pace → activities per day

```python
PACE_DENSITY = {"slow": 2, "mix": 3, "power": 5}
acts_per_day = PACE_DENSITY.get(selected_pace, 3)
```

### Step 3 — Groq call (single, `max_tokens=800`)

```python
prompt = (
    f"Create a {trip_duration}-day itinerary for {destination}. "
    f"Place visit order: {route_arc.get('place_order', [])}. "
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
```

**Output — one day:**
```json
{
  "day": 1,
  "title": "North Goa — Forts & Coastline",
  "activities": [
    {"time": "7:00 AM", "activity": "Sunrise Trek", "place": "Chapora Fort", "duration": "2h"},
    {"time": "12:00 PM", "activity": "Beach Volleyball", "place": "Baga Beach", "duration": "2h"},
    {"time": "5:30 PM", "activity": "Sunset Picnic", "place": "Chapora Fort", "duration": "1h"}
  ],
  "note": "Easy start — settle in and explore the fort before hitting the beach."
}
```

**Fallback on Groq failure:**
```python
# Distribute activities evenly, no times
chunks = [selected_activities[i::trip_duration] for i in range(trip_duration)]
return [
    {"day": i + 1, "title": f"Day {i + 1}", "activities": [{"activity": a} for a in chunk], "note": ""}
    for i, chunk in enumerate(chunks)
]
```

---

## 4. Destination Brief

### `generate_destination_brief(state: dict) -> dict`

**Reads from state:** `destination`, `experience_types`, `trip_who`, `travel_intent`

### Step 1 — Parallel Tavily searches (best-effort)

```python
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
```

### Step 2 — Groq synthesis (single call, `max_tokens=600`)

```python
prompt = (
    f"You are a local travel expert for {destination}. "
    f"Group: {trip_who or 'solo'}. Experience: {', '.join(experience_types) or 'general'}. "
    f"{'Context from recent travel sources: ' + snippets[:2000] if snippets else ''} "
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
```

**Output:**
```json
{
  "weather": "Hot & humid, 30–34°C. Evening rain possible — carry a light rain layer.",
  "language_tip": "Konkani locally; English and Hindi widely spoken at all tourist spots.",
  "lingo": [
    "Say 'Dev borem korum' to greet locals — means God bless you, widely appreciated",
    "Call older men 'Bab' and older women 'Mai' — respectful, locals love it",
    "Kitlem zaata? — how much? — use it when bargaining at markets",
    "Ek chai de — one tea please — works at any shack or stall",
    "'Susegad' — if a local says this, they mean slow down and enjoy"
  ],
  "transport": "Rent a scooter for North Goa (₹300–400/day). Metered taxis exist but negotiate first.",
  "local_events": "Sunburn Festival runs Dec 27–29 in Vagator — book accommodation early.",
  "permits": "No permits needed for beaches. Dudhsagar waterfall requires forest entry fee ₹400.",
  "safety": "Swim only at flagged beaches — riptides are common at unsupervised spots.",
  "currency": "Beach shacks and local markets are cash-only. ATMs available in Calangute and Panaji."
}
```

**Fallback on Groq failure:**
```python
{"destination": destination, "note": "Destination intel unavailable — check local sources on arrival."}
```

---

## 5. Integration Test

**File:** `tests/integration/test_pipeline.py`

**Transport:** `httpx.AsyncClient` with `ASGITransport` (no real network), pointing at the FastAPI app from `app.api.server`.

**Mocks:** `aiohttp.ClientSession` (Groq) and `tavily_search` mocked at the module level so no real API calls fire.

**Thread ID:** single UUID across all steps; real LangGraph `SqliteSaver` checkpointer accumulates state.

**Full card action sequence:**
```
POST /chat  card_action=experience_type_selected  types=["beach_coast"]
POST /chat  card_action=destination_selected      destination="Goa"
POST /chat  card_action=trip_duration_set         days=3
POST /chat  card_action=area_selected             area_id="north_goa"
POST /chat  card_action=place_selected            place_id="chapora_fort"
POST /chat  card_action=activities_for_place      place_id="chapora_fort" activities=["Sunrise Trek","Sunset Picnic"]
POST /chat  card_action=activities_confirmed      (no data)
POST /chat  card_action=pace_selected             pace="mix"
POST /chat  card_action=route_arc_selected        arc={"id":"north_to_south","label":"North → South","place_order":["Chapora Fort"]}
```

Note: `trip_duration_set` fires before area selection because `destination_selected` triggers `show_area_cards` — but in the real flow, `places_shown` gets set after place cards are shown, which triggers `duration_pending`. For the integration test, `trip_duration_set` is sent early (before area selection) to pre-set the field and avoid the `duration_pending` detour. The handler is idempotent — safe to call at any point.

**Final assertions:**
```python
assert data["action"] == "open_day_planner"
plan = data["payload"]["plan"]
brief = data["payload"]["brief"]
assert isinstance(plan, list) and len(plan) > 0
assert all("day" in d and "activities" in d for d in plan)
assert "weather" in brief
assert "lingo" in brief
assert isinstance(brief["lingo"], list) and len(brief["lingo"]) >= 3
```

Each intermediate step also asserts `data["action"]` matches expected stage action before proceeding to the next.

---

## 6. `activities_confirmed` Handler — `selected_places` Fix

The existing `activities_confirmed` handler in `intent.py` clears `pending_activities` without saving the place IDs. Sprint 6 adds `selected_places` extraction before the clear:

```python
elif card_action == "activities_confirmed":
    pending = dict(state.get("pending_activities") or {})
    state["selected_places"] = list(pending.keys())          # NEW — save before clearing
    state["selected_activities"] = [act for acts in pending.values() for act in acts]
    state["pending_activities"] = {}
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

`generate_route_arcs` uses `selected_places` to filter `place_cards` to only the user's chosen places before asking Groq to generate arcs.

---

## 7. `trip_duration_set` Card Action Handler

The `duration_pending` stage fires when `places_shown=True` and `trip_duration` is not yet set — the frontend shows a duration picker and sends back the number of days. No handler exists yet. Sprint 6 adds it to `intent.py`:

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

After this handler fires, `resolve_stage` sees `places_shown=True` AND `trip_duration` set → returns `"places_shown"` → `determine_action("places_shown")` → `show_activity_options` (existing stub, fine for now). This closes the gap in the pipeline that prevented `duration_pending` from advancing.

The integration test uses `card_action="trip_duration_set"` with `{"days": 3}` for this step.

---

## 8. Files Changed in Sprint 6

| File | Change |
|------|--------|
| `app/graph/state.py` | Add `selected_places: List[str]` field |
| `app/services/day_planner.py` | **New** — `generate_route_arcs`, `generate_day_plan`, `generate_destination_brief`, fallback constants |
| `app/services/stage_machine.py` | Replace 3 stubs with bridge functions that import from `day_planner.py` |
| `app/graph/nodes/intent.py` | Update `activities_confirmed` to save `selected_places`; add `trip_duration_set` handler |
| `app/graph/nodes/responder.py` | Persist `selected_places` |
| `tests/unit/services/test_sprint6_day_plan.py` | **New** — unit tests for all three functions + `trip_duration_set` handler |
| `tests/integration/test_pipeline.py` | **New** — full pipeline integration test |

---

## 8. Error Handling

| Failure | Behaviour |
|---------|-----------|
| Groq fails in `generate_route_arcs` | Return 2 generic arcs (selection order + reversed) |
| Groq fails in `generate_day_plan` | Distribute activities evenly across days, no times |
| Groq fails in `generate_destination_brief` | Return `{"destination": dest, "note": "intel unavailable"}` |
| Tavily unavailable in brief | Skip snippets, Groq uses its own knowledge; no error |
| Redis cold (activity_options cache miss) | Use synthetic `{"label": label, "duration": "1h", "time": "any", "vibe": "any"}` per activity |
| `route_arc` missing `place_order` | Fall back to place names from `selected_places`/`place_cards` in original order |
| `selected_places` empty | Fall back to all place cards (edge case: user skipped activity loop) |
| `trip_duration` is 0 or missing | Default to 1 day |

---

## 9. What Sprint 6 Does NOT Build

- Per-activity detail view or editing after plan is generated (frontend concern)
- Hotel / restaurant booking integration (future sprint)
- Real-time weather API (uses Tavily-scraped snippets instead)
- Distance / travel time between activities (OSRM, future sprint)
- PDF / share export of the day plan (frontend concern)
- Deduplication of identical activity names across places (Groq handles gracefully by context)
