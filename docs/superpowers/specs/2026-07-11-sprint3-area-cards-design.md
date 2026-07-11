# Sprint 3 — Area Cards + Vibe Card Content
**Date:** 2026-07-11
**Scope:** `fetch_vibe_cards` + `fetch_area_cards` in `stage_machine.py`, new `area_selected` routing, Redis cache layer
**Goal:** Insert a geographic area-selection step between destination confirmation and place cards, and fill in destination-specific vibe card content for users who arrive without experience chips.

---

## Problem

When a destination is confirmed, the system jumps from "you're going to Goa" straight to venue-level place cards. For any non-trivial destination this is disorienting — Goa has dozens of distinct beaches and neighbourhoods with completely different characters. Users need to orient themselves geographically before picking specific places.

Additionally, `fetch_vibe_cards` returns `[]` — users who type a destination directly never see vibe selection, so the system has no signal about their travel style.

---

## Branch Context

Two paths reach `destination_known`:

| Branch | How they got here | `experience_types` set? |
|--------|-------------------|------------------------|
| A | Picked experience chips → selected a destination suggestion | Yes |
| B | Typed destination directly ("I want to go to Goa") | No |

Sprint 3 handles both.

---

## 1. Routing Changes

### `resolve_stage` — new `area_selected` stage

```python
# After destination known (insert before existing vibe_selected check)
if state.get("selected_area"):
    return "area_selected"
if state.get("vibes_confirmed"):
    return "vibe_selected"      # now leads to area cards, not place cards
return "destination_known"
```

### `determine_action` — branch logic

```python
if stage == "destination_known":
    if state.get("experience_types"):
        # Branch A: skip vibe cards, go straight to area cards
        areas = await fetch_area_cards(state)
        return "show_area_cards", {"areas": areas}
    else:
        # Branch B: capture travel style first
        vibes = await fetch_vibe_cards(state)
        return "show_vibe_cards", {"vibes": vibes}

if stage == "vibe_selected":
    # Branch B: vibes confirmed → now show area cards
    areas = await fetch_area_cards(state)
    return "show_area_cards", {"areas": areas}

if stage == "area_selected":
    # Sprint 4 stub — place cards filtered to selected area
    return "show_place_cards", {"places": []}
```

### `intent.py` — new card action handler

```python
elif card_action == "area_selected":
    state["selected_area"] = card_data.get("area_id", "")
    state["card_action"] = None
    state["skip_graph"] = True   # no data fetch needed
    stage = resolve_stage(state)
    state["conversation_stage"] = stage
    action, payload = await _stage_determine_action(stage, state)
    state["action"] = action
    state["payload"] = payload
    return state
```

---

## 2. New State Fields

```python
# app/graph/state.py
area_cards: List[Dict[str, Any]]   # preloaded area cards, set when fetch_area_cards runs
selected_area: str | None          # area_id chosen by user
```

---

## 3. `fetch_vibe_cards` — Branch B Implementation

```python
async def fetch_vibe_cards(state: dict) -> list[dict]:
```

**Inputs:** `destination`, `blog_signals` (already fetched by planning node), `trip_who`, `trip_season`

**Cache key:** `f"vibe_cards:{destination.lower()}"` — TTL 24h (destination-level, not vibe-level)

**On cache hit:** return cached list immediately.

**On cache miss:**

1. One Groq call with the destination + blog signals context, requesting a JSON object with one short destination-specific hook (≤ 70 chars) per vibe ID:

```json
{
  "adv": "Cliff jumps at Vagator, paragliding at Arambol, scuba off Grande Island",
  "loc": "Spice farms in Ponda, Portuguese churches, Goan thali in Panaji's old town",
  "spt": "Flea markets at Anjuna, sunset at Chapora Fort, night bazaar at Arpora",
  "hid": "Turtle nesting at Morjim, secluded Cola beach, Chapora village at dawn"
}
```

2. Merge with BASE_VIBE_CARDS (the 4 existing frontend vibe definitions), replacing `description` with the destination hook.

3. Write to Redis, return list.

**On Groq failure:** return BASE_VIBE_CARDS as-is (generic descriptions, still functional).

### Vibe card payload shape

```json
{
  "id": "adv",
  "label": "Adventure & Outdoors",
  "eyebrow": "Physical · Outdoors",
  "description": "Cliff jumps at Vagator, paragliding at Arambol, scuba off Grande Island",
  "tags": ["trekking", "water sports", "adrenaline"]
}
```

The 4 vibe IDs are fixed: `adv`, `loc`, `spt`, `hid`. Sprint 3 does not filter vibe cards by destination — all 4 always appear. Filtering can be added later if needed.

---

## 4. `fetch_area_cards` — Core Sprint 3 Feature

```python
async def fetch_area_cards(state: dict) -> list[dict]:
```

**Inputs:** `destination`, `experience_types` (may be empty for Branch B), `vibes_confirmed` / vibe IDs, `trip_season`, `trip_who`

**Cache key:** `f"area_cards:{destination.lower()}:{exp_key}"` where:
- Branch A: `exp_key = "|".join(sorted(state.get("experience_types", [])))`
- Branch B: `exp_key = "|".join(sorted(state.get("selected_vibe_ids", [])))` — populated in state after the `vibes_selected` card action

TTL 24h.

**On cache hit:** return immediately, also write to `state["area_cards"]`.

**On cache miss — 3-step pipeline:**

### Step 1 — Scale assessment (Groq)

One Groq call: "For [destination] with travel interest in [experience_types or vibes], does it need: (a) flat — just list areas directly, or (b) zoned — group areas under geographic zones? Return JSON: `{tier: 'flat'|'zoned', zones: ['North Goa', 'South Goa']}`"

- Small destinations (Lonavala, Coorg, Coorg) → `flat`, no zones
- Medium (Goa, Manali, Pondicherry) → `zoned`, 2-3 zones
- Large (Rajasthan, Kerala, Himachal Pradesh) → `zoned`, 3-5 major zones as top-level entries (each zone card IS the selectable item — no second tier)

For large destinations, the zone cards are the area cards. User picks "Udaipur" or "Jaisalmer" as their area, and place cards in Sprint 4 scope within that city.

### Step 2 — Tavily enrichment (parallel, per zone)

For each zone (or for the destination itself if flat): one Tavily search:
- Query: `"[zone or destination] [experience_type] areas things to do [season]"`
- `max_results=5`

Run in parallel via `asyncio.gather`. Total HTTP calls: 1 for flat, 2-3 for zoned.

### Step 3 — Area generation (Groq, one batch call)

One Groq call with all zone+Tavily context, requesting a JSON array of area objects:

```json
[
  {
    "id": "vagator",
    "name": "Vagator",
    "zone": "North Goa",
    "teaser": "Rocky cliffs plunging into the Arabian Sea, Goa's rawest nightlife, and sunsets that draw crowds to the ridge every evening. Best for those who want edge over comfort.",
    "summary": "Full paragraph — geography, vibe, what to do, best season, who it suits, insider note",
    "tags": ["cliffs", "nightlife", "sunsets", "raw"]
  }
]
```

- `zone` is `null` for flat-tier destinations.
- Return 3-5 areas total (not per zone).
- `teaser` is 3-4 lines — punchy, specific, honest about who it's for.
- `summary` is one full paragraph covering: what it feels like, best things to do, when to go, who it suits.

### Step 4 — Photos (parallel)

`fetch_place_photos([area["name"]], GOOGLE_MAPS_KEY)` per area, parallel. `photo_url: null` on failure.

### Write to state and cache

```python
state["area_cards"] = areas
# write to Redis with TTL 24h
```

### Area card payload shape

```json
{
  "id": "vagator",
  "name": "Vagator",
  "zone": "North Goa",
  "teaser": "Rocky cliffs plunging into the Arabian Sea...",
  "summary": "Full paragraph...",
  "tags": ["cliffs", "nightlife", "sunsets"],
  "photo_url": "https://..."
}
```

---

## 5. Redis Cache Layer

New file: `app/services/area_cache.py`

```python
async def get_cached(key: str) -> list[dict] | None:
    """Return parsed JSON list from Redis, or None on miss/error."""

async def set_cached(key: str, data: list[dict], ttl: int = 86400) -> None:
    """Write JSON-serialised data to Redis with TTL. Silent on error."""
```

Uses the same pattern as `planning.py`: `import redis.asyncio as aioredis`, `REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")`, own `_get_redis()` factory. Self-contained — no import from planning.py. If Redis is unavailable, `get_cached` returns `None` (cache miss) and `set_cached` is a no-op — never raises.

---

## 6. Error Handling

| Failure | Behaviour |
|---------|-----------|
| Groq scale assessment fails | Default to `flat` tier, use destination name as single zone |
| Tavily enrichment fails for a zone | Proceed with empty context for that zone; Groq generates from LLM knowledge only |
| Groq area generation fails | Return `[]` — frontend shows "couldn't find areas, try typing one" |
| Redis unavailable | Skip cache entirely; fetch on every request |
| Photo fetch fails | `photo_url: null` |
| No `experience_types` AND no `vibes_confirmed` | Use destination name only for area search; still works |

---

## 7. BASE_VIBE_CARDS constant

Add to `stage_machine.py` alongside `BASE_CHIPS`:

```python
BASE_VIBE_CARDS = [
    {"id": "adv", "label": "Adventure & Outdoors", "eyebrow": "Physical · Outdoors",
     "description": "Trails, altitude, water, adrenaline", "tags": ["trekking", "water sports", "adrenaline"]},
    {"id": "loc", "label": "Culture & Food", "eyebrow": "Culture · Food · People",
     "description": "History, local cuisine, markets, people", "tags": ["heritage", "food", "local life"]},
    {"id": "spt", "label": "Spots & Scenes", "eyebrow": "Spots · Scenes",
     "description": "Viewpoints, sunsets, cafés, photo moments", "tags": ["sunsets", "cafes", "scenic"]},
    {"id": "hid", "label": "Hidden & Slow", "eyebrow": "Hidden · Slow",
     "description": "Off-path, quiet, unhurried, local secrets", "tags": ["offbeat", "quiet", "slow travel"]},
]
```

---

## 8. Files Changed in Sprint 3

| File | Change |
|------|--------|
| `app/graph/state.py` | Add `area_cards: List[Dict[str, Any]]`, `selected_area: str \| None` |
| `app/services/area_cache.py` | New file — `get_cached`, `set_cached` with Redis |
| `app/services/stage_machine.py` | Add `BASE_VIBE_CARDS`; implement `fetch_vibe_cards`, `fetch_area_cards`; update `resolve_stage`, `determine_action` |
| `app/graph/nodes/intent.py` | Add `area_selected` card action handler |
| `app/graph/nodes/responder.py` | Persist `area_cards`, `selected_area` in return dict |
| `tests/unit/services/test_sprint3_areas.py` | New test file |

---

## 9. What Sprint 3 Does NOT Build

- Place cards filtered by area (Sprint 4)
- Multi-area selection (user picks one area only for now)
- Filtering vibe cards based on destination type (all 4 always shown)
- Area-level weather or event enrichment (Sprint 6)
- The distance slider for area cards (no OSRM at area level — areas are already within the confirmed destination)
