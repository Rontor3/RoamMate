# Sprint 5 — Activity Options per Selected Place
**Date:** 2026-07-17
**Scope:** `app/services/activity_options.py` (new), `stage_machine.py` (`_STAGE_RULES`, `determine_action`), `intent.py` (two new handlers), `state.py`, `responder.py`
**Goal:** Replace the `show_activity_options, {"activities": []}` stub with real activity mini-cards for the selected place, enable a multi-place activity-selection loop, and refactor `resolve_stage` from cascading if-returns to a priority-ordered rule list.

---

## Problem

After a user selects a place (e.g. Chapora Fort), the system returns an empty `activities` list. Sprint 5 fills this in: generate 4–6 place-specific activity mini-cards using Groq (grounded by the cached area Reddit signals from Sprint 4), enable the user to pick activities across multiple places before confirming, and advance to pace selection.

---

## Context

The system already has:
- `selected_place: str | None` — set in Sprint 4 when user taps a place card
- `determine_action("place_selected")` returns `("show_activity_options", {"activities": []})` — the stub Sprint 5 replaces
- `reddit_area:{destination}:{area_id}` in Redis — area-level signals prefetched by Sprint 4's background task
- `get_cached` / `set_cached` in `area_cache.py` — Redis helpers
- `selected_activities: List[str]` already in `GraphState` — set when user confirms
- `_groq_json(prompt, max_tokens)` — shared Groq helper in `stage_machine.py`

What's new in Sprint 5:
- `app/services/activity_options.py` — owns data work (Groq + Redis)
- Multi-place loop via `pending_activities` state field
- `_STAGE_RULES` replaces the if-chain in `resolve_stage`
- Two new card actions: `activities_for_place` and `activities_confirmed`

---

## 1. Activity Card Shape

```json
{
  "id": "sunset_picnic",
  "label": "Sunset Picnic on the Rampart",
  "duration": "1h",
  "time": "evening",
  "vibe": "chill"
}
```

- `time`: `"morning"` | `"afternoon"` | `"evening"` | `"any"` — Sprint 6 day planner uses this for scheduling
- `vibe`: matches user's vibe — used by frontend to surface most relevant chips first
- `duration`: free string (`"45m"`, `"2h"`, `"half-day"`) — Sprint 6 uses for day packing
- 4–6 activities per place

**`show_activity_options` payload:**
```json
{
  "place_id": "chapora_fort",
  "place_name": "Chapora Fort",
  "activities": [
    {"id": "sunrise_trek", "label": "Sunrise Trek", "duration": "2h", "time": "morning", "vibe": "adventure"},
    {"id": "sunset_picnic", "label": "Sunset Picnic", "duration": "1h", "time": "evening", "vibe": "chill"},
    {"id": "cliff_photography", "label": "Cliff Photography", "duration": "1h", "time": "evening", "vibe": "cultural"},
    {"id": "history_walk", "label": "History Walk", "duration": "45m", "time": "morning", "vibe": "cultural"}
  ]
}
```

**Fallback on Groq failure:** 3 generic activities:
```python
[
    {"id": "explore_on_foot", "label": "Explore on foot",   "duration": "1h",  "time": "any", "vibe": "any"},
    {"id": "photo_walk",      "label": "Photo walk",        "duration": "1h",  "time": "any", "vibe": "any"},
    {"id": "try_food_nearby", "label": "Try food nearby",   "duration": "45m", "time": "any", "vibe": "any"},
]
```

---

## 2. New State Fields

```python
# app/graph/state.py — add after place_cards / selected_place block
pending_activities: Dict[str, List[str]]  # {place_id: [activity_labels]} — accumulates during multi-place loop
activity_options: List[Dict[str, Any]]    # current activity chips shown — persisted for frontend re-render
```

**Invariant enforced by `activities_confirmed` handler:**
`pending_activities` is cleared to `{}` before `selected_activities` is set. They must never both be non-empty simultaneously — `pending_activities` would win the `resolve_stage` check and block advance to pace selection.

---

## 3. `_STAGE_RULES` — Replaces `resolve_stage` if-chain

Defined at module level in `stage_machine.py`. A static list of `(predicate, stage_name)` tuples evaluated in order — first truthy predicate wins.

```python
_STAGE_RULES: list[tuple] = [
    # Late planning (most specific)
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

**Key priority decisions:**
- `selected_place` before `pending_activities` — if user taps a new place mid-loop, show that place's activity chips
- `pending_activities` before `selected_activities` — mid-loop state wins until user explicitly hits "Done"
- `pending_activities` returning `"area_selected"` — place cards re-render from Redis cache with ✓ marks

**Safety:** if `pending_activities` is non-empty AND `selected_activities` is also set (abnormal state), `pending_activities` fires first — user lands back at place cards rather than skipping unconfirmed activities.

---

## 4. Multi-Place Loop — Card Actions in `intent.py`

### `activities_for_place` — user taps "Save & back" at a place

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
    stage = resolve_stage(state)                              # → "area_selected"
    state["conversation_stage"] = stage
    action, payload = await _stage_determine_action(stage, state)
    state["action"] = action
    state["payload"] = payload
    return state
```

### `activities_confirmed` — user taps "Done →" tab

```python
elif card_action == "activities_confirmed":
    pending = state.get("pending_activities") or {}
    state["selected_activities"] = [act for acts in pending.values() for act in acts]
    state["pending_activities"] = {}                          # MUST clear before resolve_stage
    state["selected_place"] = None
    state["card_action"] = None
    state["skip_graph"] = True
    stage = resolve_stage(state)                              # → "activities_selected"
    state["conversation_stage"] = stage
    action, payload = await _stage_determine_action(stage, state)
    state["action"] = action
    state["payload"] = payload
    return state
```

---

## 5. `determine_action` Changes

### `"place_selected"` — replaces stub

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

### `"area_selected"` — extended payload with ✓ marks

```python
if stage == "area_selected":
    categories = await fetch_place_cards(state)
    return "show_place_cards", {
        "categories": categories,
        "pending_activities": state.get("pending_activities") or {},
    }
```

### Private helpers added to `stage_machine.py`

```python
def _resolve_place_name(state: dict) -> str:
    """Resolve selected_place id → name from place_cards."""
    place_id = state.get("selected_place", "")
    for cat in (state.get("place_cards") or []):
        for p in cat.get("places", []):
            if p.get("id") == place_id:
                return p.get("name", place_id)
    return place_id


async def _build_activity_options_for_place(state: dict) -> list[dict]:
    """Bridge: read state fields, delegate to activity_options.py, persist result."""
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

---

## 6. `app/services/activity_options.py` — New File

```python
async def build_activity_options(
    place_id: str,
    place_name: str,
    destination: str,
    area_id: str,
    intent: Any,
    trip_who: str | None,
) -> list[dict]:
```

**Cache key:** `f"activity_options:{destination.lower()}:{place_id.lower()}"`, TTL 21600 (6h)

**On cache hit:** return cached list immediately.

**On cache miss — 2-step pipeline:**

### Step 1 — Read cached area Reddit signals (best-effort)

```python
cached_reddit = await get_cached(f"reddit_area:{destination.lower()}:{area_id.lower()}")
area_signals = cached_reddit[0] if cached_reddit else {}
```

Extract place-specific mentions from `area_signals.get("place_signals", {})` — look for keys where `place_name.lower()` appears as substring. Build a `reddit_context` string (max 400 chars) from `review_highlights` and `vibe_tags` for any matching signal. Empty string if no match.

### Step 2 — Groq call (single, max_tokens=500)

Derive `vibe_str` from intent before building the prompt:
```python
vibe_str = ", ".join(v.value for v in intent.vibe) if intent and intent.vibe else ""
```

```python
prompt = (
    f"Generate 4-6 specific activities a traveller can do at {place_name} in {destination}. "
    f"Group: {trip_who or 'solo'}. "
    f"Vibe: {vibe_str or 'general'}. "
    f"{f'Local intel: {reddit_context}' if reddit_context else ''} "
    f"Return a JSON array. Each object must have: "
    f"id (snake_case), label (display name, max 6 words), duration (e.g. '1h', '45m', 'half-day'), "
    f"time ('morning'|'afternoon'|'evening'|'any'), vibe ('adventure'|'chill'|'cultural'|'party'|'any'). "
    f"Return only valid JSON, no explanation."
)
```

On Groq failure or invalid JSON: return `DEFAULT_ACTIVITIES` (3 generic fallback activities).

**Cache and return:**
```python
await set_cached(cache_key, activities, ttl=21600)
return activities
```

---

## 7. Responder Persistence

Add to `responder.py` return dict:

```python
"pending_activities": state.get("pending_activities") or {},
"activity_options": state.get("activity_options") or [],
```

---

## 8. Error Handling

| Failure | Behaviour |
|---------|-----------|
| Groq activity generation fails | Return `DEFAULT_ACTIVITIES` (3 generic) |
| Redis unavailable | Skip cache read/write; generate fresh every request |
| `place_name` not found in `place_cards` | Fall back to `place_id` as the name |
| `pending_activities` and `selected_activities` both set | `pending_activities` wins in `_STAGE_RULES`; user returns to place cards |
| `activities_for_place` called with empty activities list | Store `[]` for that place_id — user can re-tap the place to add activities |
| Area Reddit cache cold (Sprint 4 prefetch not yet done) | `reddit_context = ""` — Groq uses its own knowledge; no error |

---

## 9. Files Changed in Sprint 5

| File | Change |
|------|--------|
| `app/graph/state.py` | Add `pending_activities: Dict[str, List[str]]`, `activity_options: List[Dict[str, Any]]` |
| `app/services/activity_options.py` | New file — `build_activity_options`, `DEFAULT_ACTIVITIES` |
| `app/services/stage_machine.py` | Add `_STAGE_RULES`, refactor `resolve_stage`; update `determine_action` for `place_selected` and `area_selected`; add `_resolve_place_name`, `_build_activity_options_for_place` |
| `app/graph/nodes/intent.py` | Add `activities_for_place` and `activities_confirmed` card action handlers |
| `app/graph/nodes/responder.py` | Persist `pending_activities`, `activity_options` |
| `tests/unit/services/test_sprint5_activities.py` | New test file |

---

## 10. What Sprint 5 Does NOT Build

- Day-by-day scheduling of confirmed activities (Sprint 6 — `build_day_plan`)
- Per-activity detail view (frontend concern, future sprint)
- Distance / travel time between selected places (OSRM, future sprint)
- Activity deduplication across places (e.g. "Sunrise trek" at two places — Sprint 6 handles this during day planning)
- Full activity object (duration/time/vibe) in `selected_activities` — Sprint 5 stores only labels (`List[str]`) consistent with the existing TypedDict. Sprint 6's `build_day_plan` will need to re-fetch or reconstruct full objects from the Redis `activity_options` cache.
- User ability to edit / remove activities after confirming (future sprint)
