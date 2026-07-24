# Sprint 8: Place Card Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populate place cards with real vibe colors, an activity hint line, and the area they belong to; unify the card entrance animation across all components; extract the shared palette constant to a single file.

**Architecture:** Three sequential tasks — backend extends the Groq hook prompt to return `vibe_id`/`vibe_hint`/`area` per place; frontend types + render consumes those new fields; a third frontend-only task cleans up animation and palette duplication. Tasks 1 and 2 form a vertical slice (backend → frontend); Task 3 is independent polish.

**Tech Stack:** Python 3.13, FastAPI, LangGraph, Groq (llama-3.3-70b-versatile), Next.js 16, React 18, TypeScript, pytest/asyncio.

## Global Constraints

- Inline `style={}` objects only in card components — no Tailwind utility classes
- Animation spec (all card components): `cardIn 0.42s cubic-bezier(0.16,1,0.3,1) both`, stagger `60ms` per card
- Earthy palette (canonical): `["#E07A5F","#7898B0","#D4A845","#C85050","#8EAB82","#D490AA"]`
- Valid `vibe_id` values: `"adv"`, `"loc"`, `"spt"`, `"hid"` only
- `vibe_hint`: 3–4 comma-separated lowercase activity phrases, no trailing punctuation
- Run `python -m pytest tests/unit/ -q` from project root for Python tests
- Run `cd frontend && npm run build` for TypeScript checks
- No changes to `DAY_ACCENTS` in `frontend/app/page.tsx` — different color set, stays local

---

## File Map

| Status | File | Change |
|---|---|---|
| Modify | `app/services/stage_machine.py` | Extend hook prompt; parse `{hook,vibe_id,vibe_hint}`; add `area` field |
| Create | `tests/unit/services/test_sprint8_place_cards.py` | 3 new backend tests |
| Modify | `frontend/lib/types.ts` | Add `vibe_hint?: string` to `PlaceCardData` |
| Modify | `frontend/components/MessageBubble.tsx` | Render vibe hint in PlaceCardGrid; fix VibeCardGrid + PlaceCardGrid animation |
| Modify | `frontend/app/globals.css` | Replace `@keyframes cardEntrance` with `@keyframes cardIn` |
| Modify | `frontend/components/roammate/AreaCardGrid.tsx` | Remove inline `cardIn` style tag; import `EARTHY_PALETTE` |
| Modify | `frontend/components/roammate/ActivityOptions.tsx` | Same |
| Modify | `frontend/components/roammate/RouteArcCards.tsx` | Same |
| Create | `frontend/lib/palette.ts` | Export `EARTHY_PALETTE` |

---

### Task 1: Backend — extend `fetch_place_cards` Groq schema

**Files:**
- Modify: `app/services/stage_machine.py:281-310`
- Create: `tests/unit/services/test_sprint8_place_cards.py`

**Interfaces:**
- Consumes: `state["selected_vibe_ids"]` (already in scope in `fetch_place_cards`); `area_name` (already computed at line ~227)
- Produces: each place dict now contains `{"id", "name", "hook", "photo_url", "vibe_id", "vibe_hint", "area"}` — Tasks 2+ rely on `vibe_id`, `vibe_hint`, and `area` being present

- [ ] **Step 1: Write the three failing tests**

Create `tests/unit/services/test_sprint8_place_cards.py`:

```python
"""Sprint 8 — place card vibe_id, vibe_hint, and area field tests."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_fetch_place_cards_includes_vibe_id_and_vibe_hint():
    """Groq returns new {hook, vibe_id, vibe_hint} shape — place dicts include all three."""
    from app.services.stage_machine import fetch_place_cards

    state = {
        "destination": "Goa",
        "selected_areas": ["vagator"],
        "selected_vibe_ids": ["adv"],
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
        "experience_types": [],
        "travel_intent": None,
        "reddit_signals": {},
        "blog_signals": {},
    }
    mock_cats = [{"label": "Beaches", "query": "beach surf water"}]
    mock_places = [{"id": "baga", "name": "Baga Beach", "photo_url": None, "rating": 4.5}]
    mock_hooks = {
        "baga": {
            "hook": "Party meets the sea",
            "vibe_id": "adv",
            "vibe_hint": "surfing, swimming, beach volleyball",
        }
    }

    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock,
               side_effect=[mock_cats, mock_hooks]), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock,
               return_value=mock_places), \
         patch("app.services.stage_machine.asyncio.create_task"):
        result = await fetch_place_cards(state, area_id="vagator")

    assert result, "Expected non-empty result"
    place = result[0]["places"][0]
    assert place["vibe_id"] == "adv"
    assert place["vibe_hint"] == "surfing, swimming, beach volleyball"
    assert place["hook"] == "Party meets the sea"


@pytest.mark.asyncio
async def test_fetch_place_cards_backwards_compat_flat_hook():
    """Groq returns old flat-string hook — hook preserved, vibe_id defaults to 'adv', vibe_hint to ''."""
    from app.services.stage_machine import fetch_place_cards

    state = {
        "destination": "Goa",
        "selected_areas": ["vagator"],
        "selected_vibe_ids": [],
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
        "experience_types": [],
        "travel_intent": None,
        "reddit_signals": {},
        "blog_signals": {},
    }
    mock_cats = [{"label": "Beaches", "query": "beach"}]
    mock_places = [{"id": "baga", "name": "Baga Beach", "photo_url": None, "rating": 4.0}]
    mock_hooks = {"baga": "Party meets the sea"}  # old flat string format

    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock,
               side_effect=[mock_cats, mock_hooks]), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock,
               return_value=mock_places), \
         patch("app.services.stage_machine.asyncio.create_task"):
        result = await fetch_place_cards(state, area_id="vagator")

    place = result[0]["places"][0]
    assert place["hook"] == "Party meets the sea"
    assert place["vibe_id"] == "adv"
    assert place["vibe_hint"] == ""


@pytest.mark.asyncio
async def test_fetch_place_cards_includes_area_name():
    """Each place dict includes 'area' set to the human-readable area display name."""
    from app.services.stage_machine import fetch_place_cards

    state = {
        "destination": "Goa",
        "selected_areas": ["north_goa"],
        "selected_vibe_ids": ["hid"],
        "area_cards": [{"id": "north_goa", "name": "North Goa"}],
        "experience_types": [],
        "travel_intent": None,
        "reddit_signals": {},
        "blog_signals": {},
    }
    mock_cats = [{"label": "Forts", "query": "fort historical landmark"}]
    mock_places = [{"id": "chapora", "name": "Chapora Fort", "photo_url": None, "rating": 4.2}]
    mock_hooks = {
        "chapora": {
            "hook": "Dil Chahta Hai fort",
            "vibe_id": "hid",
            "vibe_hint": "photography, history walks, sunset views",
        }
    }

    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock,
               side_effect=[mock_cats, mock_hooks]), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock,
               return_value=mock_places), \
         patch("app.services.stage_machine.asyncio.create_task"):
        result = await fetch_place_cards(state, area_id="north_goa")

    assert result[0]["places"][0]["area"] == "North Goa"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/services/test_sprint8_place_cards.py -v
```

Expected: 3 FAILs — the place dicts do not yet include `vibe_id`, `vibe_hint`, or `area`.

- [ ] **Step 3: Update `fetch_place_cards` Step 4 in `app/services/stage_machine.py`**

Find the Step 4 block starting at the comment `# Step 4 — Hook generation (one batch Groq call)` (around line 281). Replace the entire block — from that comment through `categories_out.append(...)` — with:

```python
    # Step 4 — Hook + vibe generation (one batch Groq call)
    all_ids = [p["id"] for cat in categories_with_places for p in cat["places"]]
    all_names = [p["name"] for cat in categories_with_places for p in cat["places"]]
    vibe_desc = ", ".join(selected_vibe_ids) if selected_vibe_ids else "general travel"
    hook_prompt = (
        f"You are a travel expert. For each place in {area_name}, {destination}, "
        f"the traveller's vibe preference is: {vibe_desc}. "
        f"Return a JSON object mapping place_id to an object with: "
        f'"hook" (punchy one-liner under 15 words), '
        f'"vibe_id" (one of: adv=adventure/outdoor, loc=local food/culture/nightlife, '
        f'spt=spiritual/wellness/nature, hid=hidden gem/offbeat), '
        f'"vibe_hint" (3-4 comma-separated activities this place is best for, '
        f"matching the traveller's vibe, lowercase, no trailing punctuation). "
        f"Places: {json.dumps(dict(zip(all_ids, all_names)))}. "
        f"Return only valid JSON."
    )
    hooks_raw = await _groq_json(hook_prompt, max_tokens=1200)
    hooks: dict = hooks_raw if isinstance(hooks_raw, dict) else {}

    categories_out = []
    for cat in categories_with_places:
        places_out = []
        for p in cat["places"]:
            raw = hooks.get(p["id"])
            if isinstance(raw, dict):
                hook_str = raw.get("hook") or f"A great spot in {area_name}"
                vibe_id = raw.get("vibe_id", "adv")
                vibe_hint = raw.get("vibe_hint", "")
            elif isinstance(raw, str):
                # backwards compat: Groq returned old flat string format
                hook_str = raw
                vibe_id = "adv"
                vibe_hint = ""
            else:
                hook_str = f"A great spot in {area_name}"
                vibe_id = "adv"
                vibe_hint = ""
            places_out.append({
                "id": p["id"],
                "name": p["name"],
                "hook": hook_str,
                "photo_url": p["photo_url"],
                "vibe_id": vibe_id,
                "vibe_hint": vibe_hint,
                "area": area_name,
            })
        categories_out.append({"label": cat["label"], "places": places_out})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/services/test_sprint8_place_cards.py -v
```

Expected: 3 PASSes.

- [ ] **Step 5: Run full unit suite to check for regressions**

```bash
python -m pytest tests/unit/ -q
```

Expected: 193 passed, 2 pre-existing flaky failures (test_tavily and test_places_fetcher — both pass when run individually; pre-existing isolation issue).

- [ ] **Step 6: Commit**

```bash
git add app/services/stage_machine.py tests/unit/services/test_sprint8_place_cards.py
git commit -m "feat(sprint8): extend place card Groq schema — vibe_id, vibe_hint, area per place"
```

---

### Task 2: Frontend — `PlaceCardData` type + vibe hint render

**Files:**
- Modify: `frontend/lib/types.ts:73-80`
- Modify: `frontend/components/MessageBubble.tsx` (PlaceCardGrid component — hook div section)
- Test: `cd frontend && npm run build`

**Interfaces:**
- Consumes: `vibe_hint?: string` field produced by Task 1 (backend sends it in `payload.places[*].vibe_hint`)
- Produces: `PlaceCardData` interface with `vibe_hint?: string`; `PlaceCardGrid` renders the hint line below hook text

**Context:** The `area` field is already rendered in `PlaceCardGrid` as a small text label next to the vibe dot (it just shows blank because the backend didn't send it before). Once Task 1 is deployed it will populate automatically — no new area UI code needed. The only new render element is `vibe_hint`.

- [ ] **Step 1: Add `vibe_hint` to `PlaceCardData` in `frontend/lib/types.ts`**

Find the `PlaceCardData` interface (currently lines 73–80):

```typescript
export interface PlaceCardData {
  id: string;
  name: string;
  area: string;
  hook: string;
  vibe_id: string;
  rating?: number | null;
}
```

Replace with:

```typescript
export interface PlaceCardData {
  id: string;
  name: string;
  area: string;
  hook: string;
  vibe_id: string;
  vibe_hint?: string;
  rating?: number | null;
}
```

- [ ] **Step 2: Add vibe hint render in `PlaceCardGrid` inside `frontend/components/MessageBubble.tsx`**

Inside `PlaceCardGrid`, find the hook render block (inside the `.map((p, index) => { ... })` in the 2×2 grid). It currently looks like:

```tsx
              {/* Hook */}
              {p.hook && (
                <div style={{
                  fontSize: 10.5, color: "rgba(240,239,232,0.5)",
                  fontFamily: "'DM Sans', sans-serif", lineHeight: 1.45,
                }}>
                  {p.hook}
                </div>
              )}
```

Add the vibe hint immediately after the closing `)}` of the hook block:

```tsx
              {/* Vibe hint */}
              {p.vibe_hint && (
                <div style={{
                  fontSize: 10,
                  color: "rgba(240,239,232,0.55)",
                  fontFamily: "'DM Sans', sans-serif",
                  marginTop: 4,
                  lineHeight: 1.4,
                }}>
                  {p.vibe_hint}
                </div>
              )}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: compiled successfully, 0 errors. The `vibe_hint` is optional so no existing places break if the field is absent.

- [ ] **Step 4: Commit (from inside `frontend/`)**

```bash
git -C /Users/rakshitsingh/Desktop/My_project/RoamMate/frontend add lib/types.ts components/MessageBubble.tsx
git -C /Users/rakshitsingh/Desktop/My_project/RoamMate/frontend commit -m "feat(sprint8): add vibe_hint to PlaceCardData; render hint line in PlaceCardGrid"
```

---

### Task 3: Frontend — animation unification + palette extraction

**Files:**
- Modify: `frontend/app/globals.css:55-59` (replace `cardEntrance` with `cardIn`)
- Modify: `frontend/components/MessageBubble.tsx` (lines ~155-156 and ~312-313)
- Modify: `frontend/components/roammate/AreaCardGrid.tsx` (remove inline style tag; swap const for import)
- Modify: `frontend/components/roammate/ActivityOptions.tsx` (same)
- Modify: `frontend/components/roammate/RouteArcCards.tsx` (same)
- Create: `frontend/lib/palette.ts`
- Test: `cd frontend && npm run build`

**Interfaces:**
- Produces: `EARTHY_PALETTE` exported from `@/lib/palette` — all three card components import it from there

- [ ] **Step 1: Create `frontend/lib/palette.ts`**

```typescript
export const EARTHY_PALETTE: string[] = [
  "#E07A5F", "#7898B0", "#D4A845", "#C85050", "#8EAB82", "#D490AA",
]
```

- [ ] **Step 2: Update `frontend/app/globals.css` — replace `cardEntrance` with `cardIn`**

Find the `/* Card system animations */` comment and the `@keyframes cardEntrance` block below it (lines ~55–59):

```css
/* Card system animations */
@keyframes cardEntrance {
  from { opacity: 0; transform: translateY(20px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0)    scale(1); }
}
```

Replace with:

```css
/* Card system animations */
@keyframes cardIn {
  from { opacity: 0; transform: translateY(16px) scale(0.97); }
  to   { opacity: 1; transform: none; }
}
```

- [ ] **Step 3: Fix animation in `VibeCardGrid` inside `frontend/components/MessageBubble.tsx`**

Find (around line 155–156):

```tsx
                animation: "cardEntrance 0.38s cubic-bezier(0.34,1.3,0.64,1) both",
                animationDelay: `${index * 90}ms`,
```

Replace with:

```tsx
                animation: "cardIn 0.42s cubic-bezier(0.16,1,0.3,1) both",
                animationDelay: `${index * 60}ms`,
```

- [ ] **Step 4: Fix animation in `PlaceCardGrid` inside `frontend/components/MessageBubble.tsx`**

Find (around line 312–313):

```tsx
                animation: "cardEntrance 0.38s cubic-bezier(0.34,1.3,0.64,1) both",
                animationDelay: `${index * 80}ms`,
```

Replace with:

```tsx
                animation: "cardIn 0.42s cubic-bezier(0.16,1,0.3,1) both",
                animationDelay: `${index * 60}ms`,
```

- [ ] **Step 5: Update `frontend/components/roammate/AreaCardGrid.tsx`**

**5a.** Remove the local `EARTHY_PALETTE` const (line 5):

```typescript
const EARTHY_PALETTE = ["#E07A5F", "#7898B0", "#D4A845", "#C85050", "#8EAB82", "#D490AA"]
```

Replace with the import (insert at line 4, after the existing imports):

```typescript
import { EARTHY_PALETTE } from "@/lib/palette"
```

**5b.** Remove the inline `<style>` tag (currently around line 24 of the file — the first line inside the `return` block):

```tsx
      <style>{`@keyframes cardIn{from{opacity:0;transform:translateY(16px) scale(0.97)}to{opacity:1;transform:none}}`}</style>
```

Delete that line entirely. The `cardIn` keyframe is now in `globals.css`.

- [ ] **Step 6: Update `frontend/components/roammate/ActivityOptions.tsx`**

**6a.** Remove local const (line 5), add import after existing imports:

```typescript
import { EARTHY_PALETTE } from "@/lib/palette"
```

**6b.** Remove the inline `<style>` tag (around line 36 of the file):

```tsx
      <style>{`@keyframes cardIn{from{opacity:0;transform:translateY(16px) scale(0.97)}to{opacity:1;transform:none}}`}</style>
```

Delete that line.

- [ ] **Step 7: Update `frontend/components/roammate/RouteArcCards.tsx`**

**7a.** Remove local const (line 5), add import after existing imports:

```typescript
import { EARTHY_PALETTE } from "@/lib/palette"
```

**7b.** Remove the inline `<style>` tag (around line 15 of the file):

```tsx
      <style>{`@keyframes cardIn{from{opacity:0;transform:translateY(16px) scale(0.97)}to{opacity:1;transform:none}}`}</style>
```

Delete that line.

- [ ] **Step 8: Verify TypeScript compiles**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: compiled successfully, 0 errors.

- [ ] **Step 9: Commit (from inside `frontend/`)**

```bash
git -C /Users/rakshitsingh/Desktop/My_project/RoamMate/frontend add \
  lib/palette.ts \
  app/globals.css \
  components/MessageBubble.tsx \
  components/roammate/AreaCardGrid.tsx \
  components/roammate/ActivityOptions.tsx \
  components/roammate/RouteArcCards.tsx
git -C /Users/rakshitsingh/Desktop/My_project/RoamMate/frontend commit -m "refactor(sprint8): unify cardIn animation in globals.css; extract EARTHY_PALETTE to lib/palette.ts"
```
