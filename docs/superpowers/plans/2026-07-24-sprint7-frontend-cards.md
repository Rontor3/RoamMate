# Sprint 7: Frontend Card Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire `show_area_cards`, `show_activity_options`, `show_route_arcs`, and `open_day_planner` into the RoamMate Next.js frontend, and migrate area selection from single-select to multi-select end-to-end.

**Architecture:** Option C — one file per new card component in `frontend/components/roammate/`. `MessageBubble.tsx` imports and renders them alongside existing inline card components. Backend converts `selected_area: str` to `selected_areas: List[str]` and renames the `area_selected` card action to `areas_selected`. Day planner state lifts through `page.tsx` to populate the existing inline `DaySidebar`.

**Tech Stack:** Python 3.13, FastAPI, LangGraph, Next.js 16, React 18, TypeScript, inline `style={}` objects (no Tailwind in new card components), pytest/asyncio.

## Global Constraints

- Inline `style={}` objects only in new card components — no Tailwind utility classes
- Earthy palette (by index, cycling): `["#E07A5F","#7898B0","#D4A845","#C85050","#8EAB82","#D490AA"]`
- Typography: `var(--font-neuton)` for names/titles; `var(--font-dm-sans)` for body, labels, buttons
- Animation: `cubic-bezier(0.16,1,0.3,1)` 0.42s, stagger 0.06s per card; keyframe named `cardIn`
- Card sizing: `borderRadius:16`, `padding:18`, area cards `minHeight:148`; activity rows `borderRadius:12`, `padding:"13px 14px"`
- Filled card backgrounds: earthy palette color; text always `#0F0F0D`; secondary text `rgba(0,0,0,0.55)`, tag chips `background:rgba(0,0,0,0.12)`
- Dark surface tokens: bg `#0F0F0D`, surface `#161614`, border `#2A2A26`, light text `#F0EFE8`, muted `#8A8A80`
- Read `node_modules/next/dist/docs/` before writing any Next.js/React code (AGENTS.md)
- Run `pytest tests/` from project root for Python tests; `cd frontend && npm run build` for TypeScript checks
- No `selected_area` anywhere after Task 1 — all state uses `selected_areas: List[str]`
- Stage name throughout system (state, intent handler, `_STAGE_RULES`, `determine_action`): `"areas_selected"` (no longer `"area_selected"`)

---

## File Map

| Status | File | Responsibility |
|---|---|---|
| Modify | `app/graph/state.py` | Rename field: `selected_area` → `selected_areas` |
| Modify | `app/graph/nodes/intent.py` | Rename handler: `area_selected` → `areas_selected` |
| Modify | `app/services/stage_machine.py` | `fetch_place_cards` param, `_STAGE_RULES`, `_build_activity_options_for_place`, `determine_action` |
| Modify | `app/graph/nodes/responder.py` | `selected_area` → `selected_areas` in returned dict |
| Create | `tests/unit/services/test_sprint7_areas_multiselect.py` | New tests for multi-select behavior |
| Modify | `tests/unit/services/test_sprint5_activities.py` | Update 12 tests that used `selected_area`/`area_selected` |
| Modify | `tests/unit/services/test_sprint6_day_plan.py` | Update 1 state fixture |
| Modify | `tests/integration/test_pipeline.py` | Update step 4 post call |
| Modify | `frontend/lib/types.ts` | Append 5 new interfaces |
| Create | `frontend/components/roammate/AreaCardGrid.tsx` | Multi-select area cards with earthy fills |
| Create | `frontend/components/roammate/ActivityOptions.tsx` | Per-activity-row earthy fill, dark outer card |
| Create | `frontend/components/roammate/RouteArcCards.tsx` | Single-select route arc cards |
| Modify | `frontend/components/MessageBubble.tsx` | Import + render 3 new card types; update PlaceCardGrid |
| Modify | `frontend/app/page.tsx` | dayPlan/dayBrief state; open_day_planner handler; DaySidebar with real data |

---

### Task 1: Backend — multi-select areas

**Files:**
- Modify: `app/graph/state.py:92`
- Modify: `app/graph/nodes/intent.py:101-110`
- Modify: `app/services/stage_machine.py:220,323,331,365,403-408`
- Modify: `app/graph/nodes/responder.py:340`
- Create: `tests/unit/services/test_sprint7_areas_multiselect.py`
- Modify: `tests/unit/services/test_sprint5_activities.py`
- Modify: `tests/unit/services/test_sprint6_day_plan.py:96`
- Modify: `tests/integration/test_pipeline.py:203-207`

**Interfaces:**
- Produces: `resolve_stage(state_with_selected_areas)` → `"areas_selected"`; `determine_action("areas_selected", state)` → `("show_place_cards", {"places": [...], "pending_activities": {...}})`

- [ ] **Step 1: Write the failing tests in the new file**

```python
# tests/unit/services/test_sprint7_areas_multiselect.py
"""Unit tests for Sprint 7: multi-select area selection."""
import pytest
from unittest.mock import AsyncMock, patch


def test_resolve_stage_selected_areas_returns_areas_selected():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_areas": ["north_goa"]}
    assert resolve_stage(state) == "areas_selected"


def test_resolve_stage_multiple_areas():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_areas": ["north_goa", "south_goa"]}
    assert resolve_stage(state) == "areas_selected"


def test_resolve_stage_empty_selected_areas_does_not_fire():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_areas": []}
    # Empty list is falsy — should fall through to destination_known
    assert resolve_stage(state) == "destination_known"


def test_resolve_stage_pending_activities_returns_areas_selected():
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
        "selected_activities": ["Sunrise Walk"],
    }
    assert resolve_stage(state) == "areas_selected"


@pytest.mark.asyncio
async def test_determine_action_areas_selected_calls_fetch_per_area():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa", "south_goa"],
        "pending_activities": {},
    }
    cat_north = [{"label": "Beaches", "places": [{"id": "baga", "name": "Baga Beach", "hook": "Party beach", "photo_url": None}]}]
    cat_south = [{"label": "Peaceful", "places": [{"id": "palolem", "name": "Palolem Beach", "hook": "Calm cove", "photo_url": None}]}]

    call_count = 0

    async def fake_fetch(state_arg, area_id=None):
        nonlocal call_count
        call_count += 1
        return cat_north if area_id == "north_goa" else cat_south

    with patch("app.services.stage_machine.fetch_place_cards", side_effect=fake_fetch):
        action, payload = await determine_action("areas_selected", state)

    assert call_count == 2
    assert action == "show_place_cards"
    assert len(payload["places"]) == 2
    place_ids = {p["id"] for p in payload["places"]}
    assert place_ids == {"baga", "palolem"}


@pytest.mark.asyncio
async def test_determine_action_areas_selected_deduplicates_places():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa", "central_goa"],
        "pending_activities": {},
    }
    shared_place = {"id": "chapora_fort", "name": "Chapora Fort", "hook": "Famous fort", "photo_url": None}
    cats = [{"label": "Forts", "places": [shared_place]}]

    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = cats
        action, payload = await determine_action("areas_selected", state)

    # Same place from two areas must appear only once
    assert len(payload["places"]) == 1
    assert payload["places"][0]["id"] == "chapora_fort"


@pytest.mark.asyncio
async def test_determine_action_areas_selected_includes_pending_activities():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa"],
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"label": "Forts", "places": []}]
        action, payload = await determine_action("areas_selected", state)

    assert action == "show_place_cards"
    assert payload["pending_activities"] == {"chapora_fort": ["Sunrise Trek"]}


@pytest.mark.asyncio
async def test_determine_action_areas_selected_pending_activities_defaults_empty():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa"],
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        action, payload = await determine_action("areas_selected", state)

    assert action == "show_place_cards"
    assert payload["pending_activities"] == {}


@pytest.mark.asyncio
async def test_intent_areas_selected_stores_area_ids():
    from app.graph.nodes.intent import detect_intent
    state = {
        "card_action": "areas_selected",
        "card_data": {"area_ids": ["north_goa", "south_goa"]},
        "destination": "Goa",
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_place_cards", {"places": [], "pending_activities": {}})
        result = await detect_intent(state)

    assert result["selected_areas"] == ["north_goa", "south_goa"]


@pytest.mark.asyncio
async def test_intent_areas_selected_skips_graph():
    from app.graph.nodes.intent import detect_intent
    state = {
        "card_action": "areas_selected",
        "card_data": {"area_ids": ["north_goa"]},
        "destination": "Goa",
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action:
        mock_action.return_value = ("show_place_cards", {"places": [], "pending_activities": {}})
        result = await detect_intent(state)

    assert result["skip_graph"] is True
    assert result["action"] == "show_place_cards"
```

- [ ] **Step 2: Run the new tests to verify they fail**

```
pytest tests/unit/services/test_sprint7_areas_multiselect.py -v
```

Expected: all tests FAIL (functions don't exist yet or use wrong names)

- [ ] **Step 3: Update `app/graph/state.py:92`**

Find the line:
```python
    selected_area: str | None         # area_id chosen by the user
```

Replace with:
```python
    selected_areas: List[str]         # area_ids chosen by the user (multi-select)
```

Ensure `List` is imported — check the top of the file for `from typing import ...`.

- [ ] **Step 4: Update `app/graph/nodes/intent.py:101-110`**

Find:
```python
    elif card_action == "area_selected":
        state["selected_area"] = card_data.get("area_id", "")
        state["card_action"] = None
        state["skip_graph"] = True    # no data fetch needed
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state
```

Replace with:
```python
    elif card_action == "areas_selected":
        state["selected_areas"] = card_data.get("area_ids", [])
        state["card_action"] = None
        state["skip_graph"] = True    # no data fetch needed
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state
```

- [ ] **Step 5: Update `app/services/stage_machine.py` — 4 changes**

**Change 1 — `fetch_place_cards` signature (line 217-220):**

Find:
```python
async def fetch_place_cards(state: dict) -> list[dict]:
    """4-step pipeline: Groq categories → Maps search → rank → Groq hooks. Returns categorised place cards."""
    destination = state.get("destination", "")
    area_id = state.get("selected_area", "")
```

Replace with:
```python
async def fetch_place_cards(state: dict, area_id: str | None = None) -> list[dict]:
    """4-step pipeline: Groq categories → Maps search → rank → Groq hooks. Returns categorised place cards."""
    destination = state.get("destination", "")
    area_id = area_id or (state.get("selected_areas") or [""])[0]
```

**Change 2 — `_STAGE_RULES` line 323 (`pending_activities` rule):**

Find:
```python
    (lambda s: s.get("pending_activities"),                           "area_selected"),
```

Replace with:
```python
    (lambda s: s.get("pending_activities"),                           "areas_selected"),
```

**Change 3 — `_STAGE_RULES` line 331 (`selected_area` rule):**

Find:
```python
    (lambda s: s.get("selected_area"),                                "area_selected"),
```

Replace with:
```python
    (lambda s: bool(s.get("selected_areas")),                         "areas_selected"),
```

**Change 4 — `_build_activity_options_for_place` (line 365):**

Find:
```python
    area_id = state.get("selected_area", "")
```

Replace with:
```python
    area_id = (state.get("selected_areas") or [""])[0]
```

**Change 5 — `determine_action("area_selected")` case (line 403-408):**

Find:
```python
    if stage == "area_selected":
        categories = await fetch_place_cards(state)
        return "show_place_cards", {
            "categories": categories,
            "pending_activities": state.get("pending_activities") or {},
        }
```

Replace with:
```python
    if stage == "areas_selected":
        all_places: list[dict] = []
        seen_ids: set[str] = set()
        for aid in state.get("selected_areas") or []:
            cats = await fetch_place_cards(state, area_id=aid)
            for cat in cats:
                for p in cat.get("places", []):
                    pid = p.get("id", "")
                    if pid not in seen_ids:
                        seen_ids.add(pid)
                        all_places.append(p)
        state["place_cards"] = all_places
        pending = state.get("pending_activities") or {}
        return "show_place_cards", {"places": all_places, "pending_activities": pending}
```

- [ ] **Step 6: Update `app/graph/nodes/responder.py:340`**

Find:
```python
        "selected_area": state.get("selected_area"),
```

Replace with:
```python
        "selected_areas": state.get("selected_areas") or [],
```

- [ ] **Step 7: Update `tests/unit/services/test_sprint5_activities.py`**

Apply these targeted replacements (each is a distinct `old → new`):

**7a.** Find:
```python
def test_resolve_stage_pending_activities_wins_over_selected_activities():
    """pending_activities fires before selected_activities in _STAGE_RULES."""
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "pending_activities": {"baga_beach": ["Sunrise Walk"]},
        "selected_activities": ["Sunrise Walk"],
    }
    assert resolve_stage(state) == "area_selected"
```

Replace with:
```python
def test_resolve_stage_pending_activities_wins_over_selected_activities():
    """pending_activities fires before selected_activities in _STAGE_RULES."""
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "pending_activities": {"baga_beach": ["Sunrise Walk"]},
        "selected_activities": ["Sunrise Walk"],
    }
    assert resolve_stage(state) == "areas_selected"
```

**7b.** Find:
```python
def test_resolve_stage_selected_area():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_area": "north_goa"}
    assert resolve_stage(state) == "area_selected"
```

Replace with:
```python
def test_resolve_stage_selected_areas():
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_areas": ["north_goa"]}
    assert resolve_stage(state) == "areas_selected"
```

**7c.** Find:
```python
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
```

Replace with:
```python
async def test_determine_action_areas_selected_includes_pending_activities():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa"],
        "pending_activities": {"chapora_fort": ["Sunrise Trek"]},
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = [{"label": "Forts", "places": []}]
        action, payload = await determine_action("areas_selected", state)
    assert action == "show_place_cards"
    assert payload["pending_activities"] == {"chapora_fort": ["Sunrise Trek"]}
```

**7d.** Find:
```python
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

Replace with:
```python
async def test_determine_action_areas_selected_pending_activities_defaults_to_empty():
    from app.services.stage_machine import determine_action
    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa"],
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock) as mock_fetch:
        mock_fetch.return_value = []
        action, payload = await determine_action("areas_selected", state)
    assert action == "show_place_cards"
    assert payload["pending_activities"] == {}
```

**7e.** For all remaining test functions in the file that have `"selected_area": "north_goa"` as a state key, replace `"selected_area": "north_goa"` with `"selected_areas": ["north_goa"]`. Apply this replacement globally in the file.

**7f.** Find:
```python
    assert result["conversation_stage"] == "area_selected"
```

Replace with:
```python
    assert result["conversation_stage"] == "areas_selected"
```

- [ ] **Step 8: Update `tests/unit/services/test_sprint6_day_plan.py:96`**

Find:
```python
    "selected_area": "north_goa",
```

Replace with:
```python
    "selected_areas": ["north_goa"],
```

- [ ] **Step 9: Update `tests/integration/test_pipeline.py:203-207`**

Find:
```python
            # Step 4: area_selected → show_place_cards
            r = await post("area_selected", {"area_id": "north_goa"})
            assert r.status_code == 200
            data = r.json()
            assert data["action"] == "show_place_cards"
```

Replace with:
```python
            # Step 4: areas_selected → show_place_cards
            r = await post("areas_selected", {"area_ids": ["north_goa"]})
            assert r.status_code == 200
            data = r.json()
            assert data["action"] == "show_place_cards"
```

- [ ] **Step 10: Run all tests to verify they pass**

```
pytest tests/unit/services/test_sprint7_areas_multiselect.py tests/unit/services/test_sprint5_activities.py tests/unit/services/test_sprint6_day_plan.py -v
```

Expected: all tests PASS

- [ ] **Step 11: Run full unit test suite**

```
pytest tests/unit/ -v
```

Expected: all tests PASS

- [ ] **Step 12: Commit**

```bash
git add app/graph/state.py app/graph/nodes/intent.py app/services/stage_machine.py app/graph/nodes/responder.py tests/unit/services/test_sprint7_areas_multiselect.py tests/unit/services/test_sprint5_activities.py tests/unit/services/test_sprint6_day_plan.py tests/integration/test_pipeline.py
git commit -m "feat(sprint7): multi-select area selection — selected_areas, areas_selected action, deduplicated place fetch"
```

---

### Task 2: TypeScript interfaces

**Files:**
- Modify: `frontend/lib/types.ts` (append at end of file)
- Test: `cd frontend && npm run build`

**Interfaces:**
- Produces: `AreaCard`, `ActivityCard`, `RouteArc`, `DayPlanDay`, `DestinationBrief` (used by Tasks 3–7)

- [ ] **Step 1: Append 5 interfaces to `frontend/lib/types.ts`**

Add at the end of the file:

```typescript
export interface AreaCard {
  id: string
  name: string
  zone: string | null
  teaser: string
  summary: string
  tags: string[]
  photo_url: string | null
}

export interface ActivityCard {
  id: string
  label: string
  duration: string
  time: "morning" | "afternoon" | "evening"
  vibe: string
}

export interface RouteArc {
  id: string
  label: string
  description: string
  place_order: string[]
}

export interface DayPlanDay {
  day: number
  title: string
  activities: Array<{ time: string; activity: string; place: string; duration: string }>
  note: string
}

export interface DestinationBrief {
  weather: string
  language_tip: string
  lingo: string[]
  transport: string
  local_events: string
  permits: string
  safety: string
  currency: string
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds, no type errors in `lib/types.ts`

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts
git commit -m "feat(sprint7): add AreaCard, ActivityCard, RouteArc, DayPlanDay, DestinationBrief interfaces"
```

---

### Task 3: AreaCardGrid component

**Files:**
- Create: `frontend/components/roammate/AreaCardGrid.tsx`
- Test: `cd frontend && npm run build`

**Interfaces:**
- Consumes: `AreaCard` from `@/lib/types` (Task 2)
- Produces: exported default `AreaCardGrid`; fires `onConfirm(ids: string[])` on confirm button

- [ ] **Step 1: Create `frontend/components/roammate/AreaCardGrid.tsx`**

```tsx
"use client"
import React, { useState } from "react"
import type { AreaCard } from "@/lib/types"

const EARTHY_PALETTE = ["#E07A5F", "#7898B0", "#D4A845", "#C85050", "#8EAB82", "#D490AA"]

interface Props {
  areas: AreaCard[]
  onConfirm: (ids: string[]) => void
}

export default function AreaCardGrid({ areas, onConfirm }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggle = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  return (
    <div style={{ marginTop: 8 }}>
      <style>{`@keyframes cardIn{from{opacity:0;transform:translateY(16px) scale(0.97)}to{opacity:1;transform:none}}`}</style>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
        {areas.map((area, i) => {
          const color = EARTHY_PALETTE[i % EARTHY_PALETTE.length]
          const isSelected = selected.has(area.id)
          return (
            <div
              key={area.id}
              onClick={() => toggle(area.id)}
              style={{
                background: color,
                border: `1.5px solid ${isSelected ? "rgba(0,0,0,0.3)" : "rgba(0,0,0,0.12)"}`,
                borderRadius: 16,
                padding: 18,
                minHeight: 148,
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                cursor: "pointer",
                position: "relative",
                animation: "cardIn 0.42s cubic-bezier(0.16,1,0.3,1) both",
                animationDelay: `${i * 0.06}s`,
              }}
            >
              {/* Checkbox */}
              <div style={{
                position: "absolute", top: 14, right: 16,
                width: 20, height: 20, borderRadius: "50%",
                border: `1.5px solid ${isSelected ? "transparent" : "rgba(0,0,0,0.22)"}`,
                background: isSelected ? "rgba(0,0,0,0.18)" : "transparent",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, color: "#0F0F0D",
              }}>
                {isSelected ? "✓" : ""}
              </div>

              <div style={{ flex: 1 }}>
                {area.zone && (
                  <div style={{
                    fontFamily: "var(--font-dm-sans)", fontSize: 9,
                    letterSpacing: "0.12em", textTransform: "uppercase",
                    color: "rgba(0,0,0,0.45)", fontWeight: 600, marginBottom: 5,
                  }}>
                    {area.zone}
                  </div>
                )}
                <div style={{
                  fontFamily: "var(--font-neuton)", fontSize: 18, fontWeight: 700,
                  color: "#0F0F0D", marginBottom: 7, lineHeight: 1.2,
                }}>
                  {area.name}
                </div>
                <div style={{
                  fontFamily: "var(--font-dm-sans)", fontSize: 11.5,
                  color: "rgba(0,0,0,0.62)", lineHeight: 1.5,
                }}>
                  {area.teaser}
                </div>
              </div>

              {area.tags.length > 0 && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
                  {area.tags.map(tag => (
                    <span key={tag} style={{
                      fontSize: 9.5,
                      background: "rgba(0,0,0,0.12)",
                      color: "rgba(0,0,0,0.55)",
                      borderRadius: 20, padding: "3px 9px",
                      fontFamily: "var(--font-dm-sans)",
                    }}>
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {selected.size > 0 && (
        <button
          onClick={() => onConfirm(Array.from(selected))}
          style={{
            marginTop: 14, width: "100%",
            background: EARTHY_PALETTE[0],
            color: "#0F0F0D", border: "none",
            borderRadius: 20, padding: "12px 0",
            fontFamily: "var(--font-dm-sans)", fontSize: 13, fontWeight: 700,
            cursor: "pointer",
          }}
        >
          Explore these areas →
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds, no errors in `AreaCardGrid.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/components/roammate/AreaCardGrid.tsx
git commit -m "feat(sprint7): add AreaCardGrid — earthy multi-select area cards"
```

---

### Task 4: ActivityOptions component

**Files:**
- Create: `frontend/components/roammate/ActivityOptions.tsx`
- Test: `cd frontend && npm run build`

**Interfaces:**
- Consumes: `ActivityCard` from `@/lib/types` (Task 2)
- Produces: exported default `ActivityOptions`; fires `onAdd(placeId, activities)` and `onDone()`

- [ ] **Step 1: Create `frontend/components/roammate/ActivityOptions.tsx`**

```tsx
"use client"
import React, { useState } from "react"
import type { ActivityCard } from "@/lib/types"

const EARTHY_PALETTE = ["#E07A5F", "#7898B0", "#D4A845", "#C85050", "#8EAB82", "#D490AA"]

interface Props {
  activities: ActivityCard[]
  placeId: string
  placeName: string
  onAdd: (placeId: string, activities: string[]) => void
  onDone: () => void
}

export default function ActivityOptions({ activities, placeId, placeName, onAdd, onDone }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggle = (id: string) =>
    setSelected(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const handleAdd = () => {
    const labels = activities
      .filter(a => selected.has(a.id))
      .map(a => a.label)
    onAdd(placeId, labels)
  }

  const noneSelected = selected.size === 0

  return (
    <div style={{ marginTop: 8 }}>
      <style>{`@keyframes cardIn{from{opacity:0;transform:translateY(16px) scale(0.97)}to{opacity:1;transform:none}}`}</style>

      {/* Dark outer card */}
      <div style={{
        background: "#161614",
        border: "1.5px solid #2A2A26",
        borderRadius: 16,
        padding: 18,
      }}>
        {/* Header */}
        <div style={{ marginBottom: 14 }}>
          <div style={{
            fontFamily: "var(--font-dm-sans)", fontSize: 9,
            letterSpacing: "0.12em", textTransform: "uppercase",
            color: "#8A8A80", fontWeight: 600, marginBottom: 3,
          }}>
            Pick activities
          </div>
          <div style={{
            fontFamily: "var(--font-neuton)", fontSize: 18, fontWeight: 700,
            color: "#F0EFE8",
          }}>
            {placeName}
          </div>
        </div>

        {/* Activity rows */}
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {activities.map((act, i) => {
            const color = EARTHY_PALETTE[i % EARTHY_PALETTE.length]
            const isSelected = selected.has(act.id)
            return (
              <div
                key={act.id}
                onClick={() => toggle(act.id)}
                style={{
                  display: "flex", alignItems: "center", gap: 12,
                  background: color,
                  border: "1.5px solid rgba(0,0,0,0.1)",
                  borderRadius: 12,
                  padding: "13px 14px",
                  minHeight: 48,
                  cursor: "pointer",
                  animation: "cardIn 0.42s cubic-bezier(0.16,1,0.3,1) both",
                  animationDelay: `${i * 0.05}s`,
                }}
              >
                {/* Toggle */}
                <div style={{
                  width: 20, height: 20, borderRadius: "50%", flexShrink: 0,
                  border: `1.5px solid ${isSelected ? "transparent" : "rgba(0,0,0,0.22)"}`,
                  background: isSelected ? "rgba(0,0,0,0.18)" : "transparent",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 11, color: "#0F0F0D",
                }}>
                  {isSelected ? "✓" : ""}
                </div>

                {/* Label */}
                <div style={{
                  fontFamily: "var(--font-dm-sans)", fontSize: 13,
                  fontWeight: 500, color: "#0F0F0D", flex: 1, lineHeight: 1.3,
                }}>
                  {act.label}
                </div>

                {/* Meta */}
                <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
                  <span style={{
                    fontSize: 10, background: "rgba(0,0,0,0.12)",
                    color: "rgba(0,0,0,0.55)", borderRadius: 20, padding: "3px 9px",
                    fontFamily: "var(--font-dm-sans)",
                  }}>
                    {act.duration}
                  </span>
                  <span style={{
                    fontSize: 9.5, background: "rgba(0,0,0,0.12)",
                    color: "rgba(0,0,0,0.55)", borderRadius: 20, padding: "3px 9px",
                    fontFamily: "var(--font-dm-sans)", fontWeight: 600,
                  }}>
                    {act.time}
                  </span>
                </div>
              </div>
            )
          })}
        </div>

        {/* Buttons */}
        <div style={{ display: "flex", flexDirection: "column", gap: 9, marginTop: 16 }}>
          <button
            onClick={handleAdd}
            disabled={noneSelected}
            style={{
              width: "100%", background: EARTHY_PALETTE[0],
              color: "#0F0F0D", border: "none",
              borderRadius: 20, padding: "12px 0",
              fontFamily: "var(--font-dm-sans)", fontSize: 13, fontWeight: 700,
              cursor: noneSelected ? "default" : "pointer",
              opacity: noneSelected ? 0.4 : 1,
              pointerEvents: noneSelected ? "none" : "auto",
            }}
          >
            Add to my trip →
          </button>
          <button
            onClick={onDone}
            style={{
              width: "100%", background: "transparent",
              border: "1.5px solid #2A2A26",
              borderRadius: 20, padding: "11px 0",
              fontFamily: "var(--font-dm-sans)", fontSize: 13, fontWeight: 600,
              cursor: "pointer", color: "#F0EFE8",
            }}
          >
            Done — finalise plan
          </button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds, no errors in `ActivityOptions.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/components/roammate/ActivityOptions.tsx
git commit -m "feat(sprint7): add ActivityOptions — per-row earthy fills, dark outer card"
```

---

### Task 5: RouteArcCards component

**Files:**
- Create: `frontend/components/roammate/RouteArcCards.tsx`
- Test: `cd frontend && npm run build`

**Interfaces:**
- Consumes: `RouteArc` from `@/lib/types` (Task 2)
- Produces: exported default `RouteArcCards`; fires `onSelect(arc)` on tap — no confirm button

- [ ] **Step 1: Create `frontend/components/roammate/RouteArcCards.tsx`**

```tsx
"use client"
import React from "react"
import type { RouteArc } from "@/lib/types"

const EARTHY_PALETTE = ["#E07A5F", "#7898B0", "#D4A845", "#C85050", "#8EAB82", "#D490AA"]

interface Props {
  arcs: RouteArc[]
  onSelect: (arc: RouteArc) => void
}

export default function RouteArcCards({ arcs, onSelect }: Props) {
  return (
    <div style={{ marginTop: 8 }}>
      <style>{`@keyframes cardIn{from{opacity:0;transform:translateY(16px) scale(0.97)}to{opacity:1;transform:none}}`}</style>

      {arcs.map((arc, i) => {
        const color = EARTHY_PALETTE[i % EARTHY_PALETTE.length]
        return (
          <div
            key={arc.id}
            onClick={() => onSelect(arc)}
            style={{
              background: color,
              border: "1.5px solid rgba(0,0,0,0.12)",
              borderRadius: 16,
              overflow: "hidden",
              marginBottom: 12,
              cursor: "pointer",
              animation: "cardIn 0.42s cubic-bezier(0.16,1,0.3,1) both",
              animationDelay: `${i * 0.06}s`,
            }}
          >
            {/* Header */}
            <div style={{
              padding: "16px 18px 13px",
              borderBottom: "1px solid rgba(0,0,0,0.1)",
            }}>
              <div style={{
                fontFamily: "var(--font-neuton)", fontSize: 18, fontWeight: 800,
                color: "#0F0F0D",
              }}>
                {arc.label}
              </div>
            </div>

            {/* Body */}
            <div style={{ padding: "13px 18px 16px" }}>
              <div style={{
                fontFamily: "var(--font-dm-sans)", fontSize: 12,
                color: "rgba(0,0,0,0.58)", lineHeight: 1.5, marginBottom: 12,
              }}>
                {arc.description}
              </div>

              {/* Place flow */}
              <div style={{
                display: "flex", alignItems: "center",
                flexWrap: "wrap", gap: 6,
              }}>
                {arc.place_order.map((place, j) => (
                  <React.Fragment key={place}>
                    <span style={{
                      fontSize: 10.5,
                      background: "rgba(0,0,0,0.12)",
                      color: "rgba(0,0,0,0.65)",
                      borderRadius: 20, padding: "4px 11px",
                      fontFamily: "var(--font-dm-sans)",
                    }}>
                      {place}
                    </span>
                    {j < arc.place_order.length - 1 && (
                      <span style={{ fontSize: 11, color: "rgba(0,0,0,0.35)" }}>→</span>
                    )}
                  </React.Fragment>
                ))}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds, no errors in `RouteArcCards.tsx`

- [ ] **Step 3: Commit**

```bash
git add frontend/components/roammate/RouteArcCards.tsx
git commit -m "feat(sprint7): add RouteArcCards — single-select earthy arc cards"
```

---

### Task 6: MessageBubble wiring

**Files:**
- Modify: `frontend/components/MessageBubble.tsx`
- Test: `cd frontend && npm run build`

**Interfaces:**
- Consumes: `AreaCardGrid`, `ActivityOptions`, `RouteArcCards` (Tasks 3–5); `AreaCard`, `ActivityCard`, `RouteArc` from types (Task 2)
- Produces: renders `show_area_cards`, `show_activity_options`, `show_route_arcs` actions; updates `PlaceCardGrid` with `pendingActivities` badges

- [ ] **Step 1: Add imports to `MessageBubble.tsx`**

Find the existing import block near the top of `MessageBubble.tsx`. After the last `import` from `"./roammate/..."`, add:

```tsx
import AreaCardGrid from "./roammate/AreaCardGrid"
import ActivityOptions from "./roammate/ActivityOptions"
import RouteArcCards from "./roammate/RouteArcCards"
```

Also add to the types import from `@/lib/types`:
```tsx
import type { AreaCard, ActivityCard, RouteArc } from "@/lib/types"
```

(If there's already a types import line, add `AreaCard, ActivityCard, RouteArc` to it.)

- [ ] **Step 2: Update `PlaceCardGrid` to accept `pendingActivities` and `onDone`**

Find the `PlaceCardGrid` component definition:
```tsx
const PlaceCardGrid = ({
  places,
  onConfirm,
}: {
  places: PlaceCardData[];
  onConfirm: (ids: string[]) => void;
}) => {
```

Replace with:
```tsx
const PlaceCardGrid = ({
  places,
  onConfirm,
  pendingActivities,
  onDone,
}: {
  places: PlaceCardData[];
  onConfirm: (ids: string[]) => void;
  pendingActivities?: Record<string, string[]>;
  onDone?: () => void;
}) => {
```

- [ ] **Step 3: Add "N acts" badge and "Done — finalise plan" button to PlaceCardGrid**

Inside the `PlaceCardGrid` component, find where each place card is rendered (the `<button key={p.id}` element). Add a green badge overlay at the top of each card when the place has pending activities. Find the line where the card `<button>` closes and locate a suitable inner element. Add immediately inside the outermost card button element (as its first child):

```tsx
{pendingActivities?.[p.id]?.length ? (
  <div style={{
    position: "absolute", top: 6, left: 6, zIndex: 2,
    background: "#03C03C", color: "#0F0F0D",
    fontSize: 9, fontWeight: 700,
    borderRadius: 20, padding: "2px 7px",
    fontFamily: "var(--font-dm-sans)",
  }}>
    {pendingActivities[p.id].length} acts
  </div>
) : null}
```

Then, after the closing `</div>` of the place card grid (the `</div>` that closes the 2×2 grid), add the ghost button:

```tsx
{onDone && pendingActivities && Object.keys(pendingActivities).length > 0 && (
  <button
    onClick={onDone}
    style={{
      marginTop: 10, width: "100%",
      background: "transparent",
      border: "1.5px solid #2A2A26",
      borderRadius: 20, padding: "10px 0",
      fontFamily: "var(--font-dm-sans)", fontSize: 12, fontWeight: 600,
      cursor: "pointer", color: "#F0EFE8",
    }}
  >
    Done — finalise plan
  </button>
)}
```

- [ ] **Step 4: Update the `show_place_cards` render block to pass `pendingActivities` and `onDone`**

Find:
```tsx
        {/* Place cards */}
        {message.action === "show_place_cards" && message.payload?.places && (
          <PlaceCardGrid
            places={message.payload.places as PlaceCardData[]}
            onConfirm={(ids) => cardAction("places_selected", { place_ids: ids })}
          />
        )}
```

Replace with:
```tsx
        {/* Place cards */}
        {message.action === "show_place_cards" && message.payload?.places && (
          <PlaceCardGrid
            places={message.payload.places as PlaceCardData[]}
            onConfirm={(ids) => cardAction("place_selected", { place_id: ids[0] })}
            pendingActivities={message.payload.pending_activities as Record<string, string[]> | undefined}
            onDone={() => cardAction("activities_confirmed", {})}
          />
        )}
```

- [ ] **Step 5: Add three new render blocks after the existing ones**

Find the closing of the `RouteCards` render block:
```tsx
        {/* Route cards */}
        {message.action === "show_route_cards" && message.payload?.routes && (
          <RouteCards
            routes={message.payload.routes as any[]}
            onSelect={(id) => cardAction("route_selected", { route_id: id })}
          />
        )}
      </div>
    </AISlot>
```

Replace with:
```tsx
        {/* Route cards */}
        {message.action === "show_route_cards" && message.payload?.routes && (
          <RouteCards
            routes={message.payload.routes as any[]}
            onSelect={(id) => cardAction("route_selected", { route_id: id })}
          />
        )}

        {/* Area cards — multi-select */}
        {message.action === "show_area_cards" && message.payload?.areas && (
          <AreaCardGrid
            areas={message.payload.areas as AreaCard[]}
            onConfirm={(ids) => cardAction("areas_selected", { area_ids: ids })}
          />
        )}

        {/* Activity options */}
        {message.action === "show_activity_options" && message.payload?.activities && (
          <ActivityOptions
            activities={message.payload.activities as ActivityCard[]}
            placeId={message.payload.place_id as string ?? ""}
            placeName={message.payload.place_name as string ?? ""}
            onAdd={(placeId, activities) => cardAction("activities_for_place", { place_id: placeId, activities })}
            onDone={() => cardAction("activities_confirmed", {})}
          />
        )}

        {/* Route arc cards */}
        {message.action === "show_route_arcs" && message.payload?.arcs && (
          <RouteArcCards
            arcs={message.payload.arcs as RouteArc[]}
            onSelect={(arc) => cardAction("route_arc_selected", { arc })}
          />
        )}
      </div>
    </AISlot>
```

- [ ] **Step 6: Verify TypeScript compiles**

```
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds, no errors in `MessageBubble.tsx`

- [ ] **Step 7: Commit**

```bash
git add frontend/components/MessageBubble.tsx
git commit -m "feat(sprint7): wire show_area_cards, show_activity_options, show_route_arcs in MessageBubble; add pending_activities badges to PlaceCardGrid"
```

---

### Task 7: page.tsx — day plan state and DaySidebar

**Files:**
- Modify: `frontend/app/page.tsx`
- Test: `cd frontend && npm run build`

**Interfaces:**
- Consumes: `DayPlanDay`, `DestinationBrief` from `@/lib/types` (Task 2)
- Produces: `DaySidebar` renders real plan data when `open_day_planner` fires

- [ ] **Step 1: Add DayPlanDay and DestinationBrief imports to `page.tsx`**

Find the existing import from `@/lib/types` in `page.tsx`:
```tsx
import type { Message, ChatResponse } from "@/lib/types"
```

Replace with:
```tsx
import type { Message, ChatResponse, DayPlanDay, DestinationBrief } from "@/lib/types"
```

- [ ] **Step 2: Add `dayPlan` and `dayBrief` state variables**

Inside `HomePage`, find the existing state declarations:
```tsx
  const [sidebarOpen, setSidebarOpen] = useState(false);
```

Add immediately after:
```tsx
  const [dayPlan, setDayPlan] = useState<DayPlanDay[] | null>(null);
  const [dayBrief, setDayBrief] = useState<DestinationBrief | null>(null);
```

- [ ] **Step 3: Handle `open_day_planner` in `sendMessage` response handler**

Find in `sendMessage`:
```tsx
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: "assistant",
        content: data.response ?? "",
        phase: data.phase,
        action: data.action ?? null,
        payload: data.payload ?? null,
      }]);
    } catch (err) {
```

Replace with:
```tsx
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: "assistant",
        content: data.response ?? "",
        phase: data.phase,
        action: data.action ?? null,
        payload: data.payload ?? null,
      }]);
      if (data.action === "open_day_planner" && data.payload?.plan) {
        setDayPlan(data.payload.plan as DayPlanDay[]);
        setDayBrief((data.payload.brief as DestinationBrief) ?? null);
        setSidebarOpen(true);
      }
    } catch (err) {
```

- [ ] **Step 4: Handle `open_day_planner` in `sendCardAction` response handler**

Find in `sendCardAction`:
```tsx
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: "assistant",
        content: data.response ?? "",
        action: data.action ?? null,
        payload: data.payload ?? null,
        phase: data.phase,
      }]);
    } catch (err) {
      console.error("Card action failed:", err);
```

Replace with:
```tsx
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: "assistant",
        content: data.response ?? "",
        action: data.action ?? null,
        payload: data.payload ?? null,
        phase: data.phase,
      }]);
      if (data.action === "open_day_planner" && data.payload?.plan) {
        setDayPlan(data.payload.plan as DayPlanDay[]);
        setDayBrief((data.payload.brief as DestinationBrief) ?? null);
        setSidebarOpen(true);
      }
    } catch (err) {
      console.error("Card action failed:", err);
```

- [ ] **Step 5: Replace `DaySidebar` function with real-data version**

Find the entire `DaySidebar` function definition (lines 54–107 in the original file — from `function DaySidebar` through its closing `}`):

```tsx
function DaySidebar({ open }: { open: boolean }) {
  const DAYS = [
    { num: 1, title: "Arrival day", accent: "#03C03C" },
    { num: 2, title: "Full day", accent: "#C23B23" },
    { num: 3, title: "Departure day", accent: "#F39A27" },
  ];
  return (
    <div style={{
      width: 252, flexShrink: 0,
      borderRight: "0.5px solid rgba(255,255,255,0.06)",
      background: "#161614", display: "flex", flexDirection: "column",
      transform: open ? "translateX(0)" : "translateX(-100%)",
      transition: "transform 0.46s cubic-bezier(0.77,0,0.18,1)",
      position: "absolute", left: 0, top: 0, bottom: 0, zIndex: 10,
    }}>
      <div style={{ padding: "13px 16px 11px", borderBottom: "0.5px solid rgba(255,255,255,0.06)" }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#F0EFE8", fontFamily: "'Neuton', serif" }}>Your day plan</div>
        <div style={{ fontSize: 10.5, color: "rgba(240,239,232,0.35)", marginTop: 2, fontFamily: "'DM Sans', sans-serif" }}>Tap a day to plan it</div>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: 10, display: "flex", flexDirection: "column", gap: 9 }}>
        {DAYS.map(d => (
          <div key={d.num} style={{
            borderRadius: 12, background: "#161614",
            border: "1px solid rgba(255,255,255,0.06)",
            position: "relative", overflow: "hidden", padding: "11px 13px",
          }}
            onMouseEnter={e => {
              const sw = e.currentTarget.querySelector<HTMLElement>(".swoop");
              if (sw) sw.style.transform = "translateX(0)";
              e.currentTarget.style.borderColor = d.accent;
            }}
            onMouseLeave={e => {
              const sw = e.currentTarget.querySelector<HTMLElement>(".swoop");
              if (sw) sw.style.transform = "translateX(-105%)";
              e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
            }}>
            <div className="swoop" style={{
              position: "absolute", inset: 0,
              background: `linear-gradient(115deg,${d.accent}48 0%,${d.accent}12 80%,transparent 100%)`,
              transform: "translateX(-105%)",
              transition: "transform 0.52s cubic-bezier(0.77,0,0.18,1)", zIndex: 0,
            }} />
            <div style={{ position: "relative", zIndex: 1 }}>
              <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: "rgba(240,239,232,0.4)", marginBottom: 2, fontFamily: "'DM Sans', sans-serif" }}>Day {d.num}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#F0EFE8", marginBottom: 8, fontFamily: "'Neuton', serif" }}>{d.title}</div>
              <div style={{ fontSize: 10, color: "rgba(240,239,232,0.3)", fontStyle: "italic", fontFamily: "'DM Sans', sans-serif" }}>No stops yet</div>
              <div style={{ marginTop: 10, fontSize: 10, fontWeight: 700, color: "rgba(240,239,232,0.35)" }}>Plan this day →</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

Replace with:

```tsx
function DaySidebar({ open, plan, brief }: {
  open: boolean;
  plan: DayPlanDay[] | null;
  brief: DestinationBrief | null;
}) {
  const DAY_ACCENTS = ["#03C03C", "#C23B23", "#F39A27", "#7898B0", "#D4A845", "#E07A5F"];

  return (
    <div style={{
      width: 252, flexShrink: 0,
      borderRight: "0.5px solid rgba(255,255,255,0.06)",
      background: "#161614", display: "flex", flexDirection: "column",
      transform: open ? "translateX(0)" : "translateX(-100%)",
      transition: "transform 0.46s cubic-bezier(0.77,0,0.18,1)",
      position: "absolute", left: 0, top: 0, bottom: 0, zIndex: 10,
      overflowY: "auto",
    }}>
      {/* Header */}
      <div style={{ padding: "13px 16px 11px", borderBottom: "0.5px solid rgba(255,255,255,0.06)", flexShrink: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#F0EFE8", fontFamily: "'Neuton', serif" }}>Your day plan</div>
        <div style={{ fontSize: 10.5, color: "rgba(240,239,232,0.35)", marginTop: 2, fontFamily: "'DM Sans', sans-serif" }}>
          {plan ? `${plan.length} day${plan.length !== 1 ? "s" : ""}` : "Building your trip…"}
        </div>
      </div>

      {!plan ? (
        /* Empty state */
        <div style={{
          flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
          padding: 20, textAlign: "center",
        }}>
          <div style={{ fontSize: 11, color: "rgba(240,239,232,0.28)", fontFamily: "'DM Sans', sans-serif", lineHeight: 1.6 }}>
            Your day plan will appear here once you complete the trip setup.
          </div>
        </div>
      ) : (
        <div style={{ flex: 1, overflowY: "auto", padding: 10, display: "flex", flexDirection: "column", gap: 9 }}>

          {/* Destination intel */}
          {brief && (
            <div style={{
              borderRadius: 12, background: "#1A1A18",
              border: "1px solid rgba(255,255,255,0.06)",
              padding: "11px 13px",
            }}>
              <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: ".12em", textTransform: "uppercase", color: "rgba(240,239,232,0.35)", marginBottom: 8, fontFamily: "'DM Sans', sans-serif" }}>
                Destination intel
              </div>
              {[
                { label: "Weather", value: brief.weather },
                { label: "Transport", value: brief.transport },
                { label: "Currency", value: brief.currency },
                { label: "Safety", value: brief.safety },
              ].map(row => (
                <div key={row.label} style={{ display: "flex", gap: 6, marginBottom: 5 }}>
                  <div style={{ fontSize: 9.5, color: "rgba(240,239,232,0.35)", fontFamily: "'DM Sans', sans-serif", width: 52, flexShrink: 0 }}>{row.label}</div>
                  <div style={{ fontSize: 9.5, color: "rgba(240,239,232,0.7)", fontFamily: "'DM Sans', sans-serif", lineHeight: 1.4 }}>{row.value}</div>
                </div>
              ))}
              {brief.language_tip && (
                <div style={{ fontSize: 9.5, color: "rgba(240,239,232,0.45)", fontFamily: "'DM Sans', sans-serif", marginTop: 6, fontStyle: "italic" }}>
                  {brief.language_tip}
                </div>
              )}
              {/* Lingo chips */}
              {brief.lingo && brief.lingo.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                  {brief.lingo.map((entry, i) => {
                    const dashIdx = entry.indexOf(" — ");
                    const phrase = dashIdx >= 0 ? entry.slice(0, dashIdx) : entry;
                    const meaning = dashIdx >= 0 ? entry.slice(dashIdx + 3) : "";
                    return (
                      <span key={i} style={{
                        fontSize: 9, borderRadius: 20,
                        background: "rgba(255,255,255,0.05)",
                        padding: "2px 8px",
                        fontFamily: "'DM Sans', sans-serif",
                      }}>
                        <span style={{ color: "#03C03C", fontWeight: 600 }}>{phrase}</span>
                        {meaning && <span style={{ color: "rgba(240,239,232,0.38)", marginLeft: 3 }}>{meaning}</span>}
                      </span>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Day cards */}
          {plan.map((d, idx) => {
            const accent = DAY_ACCENTS[idx % DAY_ACCENTS.length];
            return (
              <div key={d.day} style={{
                borderRadius: 12, background: "#161614",
                border: "1px solid rgba(255,255,255,0.06)",
                position: "relative", overflow: "hidden", padding: "11px 13px",
              }}
                onMouseEnter={e => {
                  const sw = e.currentTarget.querySelector<HTMLElement>(".swoop");
                  if (sw) sw.style.transform = "translateX(0)";
                  e.currentTarget.style.borderColor = accent;
                }}
                onMouseLeave={e => {
                  const sw = e.currentTarget.querySelector<HTMLElement>(".swoop");
                  if (sw) sw.style.transform = "translateX(-105%)";
                  e.currentTarget.style.borderColor = "rgba(255,255,255,0.06)";
                }}
              >
                <div className="swoop" style={{
                  position: "absolute", inset: 0,
                  background: `linear-gradient(115deg,${accent}48 0%,${accent}12 80%,transparent 100%)`,
                  transform: "translateX(-105%)",
                  transition: "transform 0.52s cubic-bezier(0.77,0,0.18,1)", zIndex: 0,
                }} />
                <div style={{ position: "relative", zIndex: 1 }}>
                  <div style={{ fontSize: 9.5, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase", color: accent, marginBottom: 2, fontFamily: "'DM Sans', sans-serif", opacity: 0.85 }}>
                    Day {d.day}
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#F0EFE8", marginBottom: 8, fontFamily: "'Neuton', serif" }}>{d.title}</div>

                  {d.activities && d.activities.length > 0 ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                      {d.activities.map((act, ai) => (
                        <div key={ai} style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
                          <div style={{ fontSize: 9.5, color: "rgba(240,239,232,0.35)", fontFamily: "'DM Sans', sans-serif", width: 44, flexShrink: 0, paddingTop: 1 }}>{act.time}</div>
                          <div style={{ flex: 1 }}>
                            <div style={{ fontSize: 10.5, color: "#F0EFE8", fontFamily: "'DM Sans', sans-serif", fontWeight: 500 }}>{act.activity}</div>
                            <div style={{ fontSize: 9.5, color: "rgba(240,239,232,0.38)", fontFamily: "'DM Sans', sans-serif" }}>{act.place}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div style={{ fontSize: 10, color: "rgba(240,239,232,0.3)", fontStyle: "italic", fontFamily: "'DM Sans', sans-serif" }}>No stops yet</div>
                  )}

                  {d.note && (
                    <div style={{ marginTop: 8, fontSize: 9.5, color: "rgba(240,239,232,0.3)", fontStyle: "italic", fontFamily: "'DM Sans', sans-serif" }}>{d.note}</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Update `DaySidebar` JSX usage in the return statement**

Find:
```tsx
        <DaySidebar open={sidebarOpen} />
```

Replace with:
```tsx
        <DaySidebar open={sidebarOpen} plan={dayPlan} brief={dayBrief} />
```

- [ ] **Step 7: Verify TypeScript compiles**

```
cd frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds, no type errors. If there are errors related to the `DaySidebar` props or state types, fix them before committing.

- [ ] **Step 8: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(sprint7): lift day plan state to page.tsx; DaySidebar renders real plan data from open_day_planner"
```

---

## Self-Review

### Spec coverage

| Spec section | Task |
|---|---|
| `show_area_cards` → `AreaCardGrid` multi-select | Tasks 3 + 6 |
| `show_activity_options` → `ActivityOptions` per-row earthy fills | Tasks 4 + 6 |
| `show_route_arcs` → `RouteArcCards` single-select | Tasks 5 + 6 |
| `open_day_planner` → DaySidebar real data | Task 7 |
| Backend: `selected_area` → `selected_areas` | Task 1 |
| Backend: `area_selected` → `areas_selected` | Task 1 |
| `fetch_place_cards` multi-area loop + deduplication | Task 1 |
| TypeScript interfaces for 5 new types | Task 2 |
| Earthy palette, filled card backgrounds, dark text | Tasks 3–5 |
| Animation `cubic-bezier(0.16,1,0.3,1)` 0.42s + stagger | Tasks 3–5 |
| `PlaceCardGrid` pending_activities badges + Done button | Task 6 |
| DaySidebar destination intel + lingo chips + day cards | Task 7 |
| Day planner empty state | Task 7 |

### Placeholder scan

No TBD or vague steps — every step contains the actual code.

### Type consistency

- `AreaCard.id: string` → used in `AreaCardGrid` toggle (`Set<string>`) ✓
- `ActivityCard.label: string` → used in `handleAdd` to filter by id and map to label ✓
- `RouteArc` shape `{id, label, description, place_order}` → used in `RouteArcCards` and `onSelect(arc)` fires with full object ✓
- `DayPlanDay` and `DestinationBrief` → imported in `page.tsx`, passed as `plan` and `brief` props ✓
- `cardAction("areas_selected", { area_ids: ids })` in MessageBubble → matches intent.py handler that reads `card_data.get("area_ids", [])` ✓
- `cardAction("activities_for_place", { place_id, activities })` → matches intent.py handler ✓
- `cardAction("route_arc_selected", { arc })` → matches intent.py handler ✓

---

Plan complete and saved to `docs/superpowers/plans/2026-07-24-sprint7-frontend-cards.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
