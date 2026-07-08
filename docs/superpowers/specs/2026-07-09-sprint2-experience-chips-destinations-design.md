# Sprint 2 — Experience Chips + Destination Suggestions
**Date:** 2026-07-09
**Scope:** `build_experience_chips` + `fetch_destination_suggestions` in `stage_machine.py`
**Goal:** Replace the two empty stubs with real implementations so users see geo-relevant experience chips and get actual destination suggestions with road travel times and photos.

---

## Problem

`build_experience_chips` returns a hardcoded list of 6 chips regardless of where the user is. `fetch_destination_suggestions` returns `[]`. The experience chip → destination suggestion flow is the first thing a new user hits when they have no destination in mind — it must work.

---

## Branch Context

Sprint 2 only runs on **Branch A** — the user has no destination set yet. If a user types a destination explicitly ("I want to go to Goa", "North East"), `resolve_stage` returns `"destination_known"` and both Sprint 2 functions are skipped entirely. OSRM filtering never applies to user-named destinations.

---

## 1. New State Field

```python
# app/graph/state.py
destination_candidates: Dict[str, List[str]]
# e.g. {"hills_nature": ["Lonavala", "Mahabaleshwar"], "beach_coast": ["Alibaug", "Goa"]}
```

Pre-cached at chip time, consumed at destination suggestion time. Persisted via LangGraph checkpointer across turns — no second Tavily call needed when the user picks chips.

---

## 2. New Utility File

`app/services/geo_utils.py` — all geographic helpers. Keeps `stage_machine.py` clean.

```python
async def geocode(place_name: str) -> dict | None:
    """Nominatim: city name → {lat, lng}. Returns None on failure."""

async def driving_time(origin: dict, destination: dict) -> dict | None:
    """OSRM public API: {lat, lng} pairs → {distance_km, duration_mins, travel_time_str}.
    Returns None on failure. Uses router.project-osrm.org — free, no API key."""

async def batch_driving_times(origin: dict, destinations: list[dict]) -> list[dict | None]:
    """Run driving_time for multiple destinations in parallel via asyncio.gather."""
```

**Origin resolution priority** (used by both functions):
1. `state["current_location"]["lat"] + ["lng"]` + label — GPS (most precise)
2. `intent.origin_city` — LLM-extracted from message ("weekend trip from Mumbai")
3. Neither available → skip geo-filter, return all candidates unfiltered

---

## 3. `build_experience_chips`

```python
async def build_experience_chips(state: dict) -> list[dict]:
```

### trip_mode == "plan"

Return all 6 base chips immediately. No Tavily call, no geo-filter. User is planning for future dates — any destination type is valid.

```python
return BASE_CHIPS  # the existing 6-chip list in stage_machine.py
```

### trip_mode == "now" (or None — treat as "now")

Two parallel Tavily calls via `asyncio.gather`:

**Call 1 — Destination pre-fetch:**
- Query: `"weekend getaway destinations from [origin] road trip"`
- Parse raw results → extract destination names (Groq structured extraction)
- Groq classifies each name into one of 6 category IDs
- Store result in `state["destination_candidates"]`
- Only return chips for categories with ≥1 candidate

**Call 2 — Live hook fetch:**
- Query: `"events festivals concerts near [origin] this month"`
- Groq extracts one short `live_hook` string per relevant chip
- e.g. `"Sunburn Festival this weekend in Pune"`

**Merge:** attach `live_hook` to chips where found. Return filtered chip list.

### Chip payload shape (unchanged from Sprint 1 spec)

```json
{
  "id": "hills_nature",
  "label": "Hills & Nature",
  "description": "Altitude, trails, forests, quiet",
  "live_hook": "Kasol Nomad Festival next weekend"
}
```

---

## 4. `fetch_destination_suggestions`

```python
async def fetch_destination_suggestions(state: dict) -> list[dict]:
```

**Inputs:** `experience_types`, `destination_candidates`, `current_location` / `origin_city`, `trip_who`, `trip_season`

### Step-by-step

**Step 1 — Gather candidates**

Read `destination_candidates` filtered to selected `experience_types`:
```python
candidates = []
for exp_type in state.get("experience_types", []):
    candidates += state.get("destination_candidates", {}).get(exp_type, [])
```

If `destination_candidates` is empty (user came via `trip_mode: "plan"`, no pre-cache):
- Fallback Tavily search: `"[experience_types joined] destinations [season] India"`

**Step 2 — Geocode candidates**

Nominatim geocodes each candidate name → lat/lng via `asyncio.gather`.
Candidates that fail geocoding are dropped silently.

**Step 3 — OSRM road filter**

`batch_driving_times(origin, geocoded_candidates)` → driving time + distance per candidate.
Keep only candidates with `duration_mins ≤ 720` (12 hours).

**Step 4 — Hook generation (Groq)**

For each surviving candidate, Groq writes a one-line hook given:
- Destination name
- `trip_who`, `trip_season`, `experience_types`
- e.g. → `"Perfect monsoon trek for solo travellers — waterfalls at peak flow"`

All hook calls run in parallel via `asyncio.gather`.

**Step 5 — Photos (Google Places)**

`fetch_place_photos([name], GOOGLE_MAPS_KEY)` per destination — already used in `server.py`, same function. Run in parallel.

**Step 6 — Sort and return**

Sort by `duration_mins ASC` (closer first). Return top 10.

### Destination card shape

```json
{
  "name": "Mahabaleshwar",
  "experience_type": "hills_nature",
  "distance_km": 263,
  "travel_time": "5h 30min",
  "hook": "Monsoon season turns the valleys electric green — best strawberry season too",
  "photo_url": "https://..."
}
```

`experience_type` is included so the frontend can group or filter cards by chip type when the user selected multiple chips.

---

## 5. The 12-Hour Rule

The OSRM ≤12h filter applies **only to our generated suggestions**. It does not apply when:
- User explicitly names a destination ("I want to go to Leh") → Branch B, skip Sprint 2 entirely
- User names a region ("North East") → same, skip Sprint 2

The 12h constraint is our suggestion quality bar, not a gate on user intent.

---

## 6. Tavily Query Design

| Purpose | Query |
|---------|-------|
| Destination pre-fetch | `"weekend getaway road trip destinations from [origin]"` |
| Live event hook | `"events festivals concerts near [origin] this month"` |
| Plan-mode fallback | `"[experience_type] destinations [season] India"` |

The existing `_tavily_search` helper in `blog_signals.py` is private (underscore prefix). Sprint 2 extracts it to `app/services/tavily_client.py` as a public `tavily_search(query, max_results)` function. Both `blog_signals.py` and `stage_machine.py` then import from there. No new HTTP wiring — same implementation, just moved.

---

## 7. OSRM Integration

Public endpoint, no API key, free:
```
GET http://router.project-osrm.org/route/v1/driving/{lng1},{lat1};{lng2},{lat2}?overview=false
```

Returns:
```json
{ "routes": [{ "distance": 263000, "duration": 19800 }] }
```

`distance` is metres → divide by 1000 for `distance_km`.
`duration` is seconds → divide by 60 for `duration_mins`, format as `"5h 30min"`.

Timeout: 5s per call. On failure, candidate is dropped (not surfaced as an error).

---

## 8. Groq Usage in Sprint 2

Two Groq calls per chip request (only in "now" mode):

| Call | Purpose | Output |
|------|---------|--------|
| Classify Tavily results | Map raw destination names to 6 category IDs | `{category: [names]}` |
| Extract live hooks | Pull event text per chip from events search results | `{chip_id: hook_str}` |

One Groq call per destination suggestion batch:

| Call | Purpose | Output |
|------|---------|--------|
| Hook generation | One-line vibe+season+who fit per destination | `[hook_str]` |

All Groq calls use the existing `GROQ_API` key and `meta-llama/llama-4-scout-17b-16e-instruct` model.

---

## 9. Error Handling

| Failure | Behaviour |
|---------|-----------|
| Tavily pre-fetch fails | Fall back to all 6 chips unfiltered |
| Nominatim geocoding fails for a candidate | Drop that candidate silently |
| OSRM fails for a candidate | Drop that candidate silently |
| OSRM service unreachable | Skip distance filter, return all Tavily candidates |
| Groq hook generation fails | Use destination name as hook (`"Visit [name]"`) |
| Google Places photo fails | `photo_url: null` |
| No candidates survive filter | Return empty list — frontend shows "no destinations found" |

---

## 10. Files Changed in Sprint 2

| File | Change |
|------|--------|
| `app/graph/state.py` | Add `destination_candidates: Dict[str, List[str]]` |
| `app/services/tavily_client.py` | New file — extract `_tavily_search` from `blog_signals.py` as public `tavily_search` |
| `app/services/blog_signals.py` | Replace local `_tavily_search` with import from `tavily_client.py` |
| `app/services/geo_utils.py` | New file — `geocode`, `driving_time`, `batch_driving_times` |
| `app/services/stage_machine.py` | Implement `build_experience_chips` + `fetch_destination_suggestions` |
| `tests/unit/services/test_geo_utils.py` | Unit tests for geo_utils helpers |
| `tests/unit/services/test_sprint2_chips.py` | Unit tests for chip + destination logic |

---

## 11. What Sprint 2 Does NOT Build

- Live event hooks for `trip_mode: "plan"` (hooks are only relevant for "now" mode trips)
- Distance slider frontend component (backend sends `distance_km`, frontend implements slider in a later sprint)
- Vibe cards for confirmed destinations (Sprint 3)
- Any change to the existing discovery / planning / in-destination phase nodes
