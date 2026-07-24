# Sprint 8: Place Card Polish — Design Spec

**Date:** 2026-07-25
**Status:** Approved

---

## Goal

Make place cards informative and visually correct:
1. Show a vibe-relevant activity hint on each card ("surfing, cliff jumping, kayaking")
2. Show which area the place belongs to (important after multi-area selection)
3. Give each card its correct VIBE_THEME accent color instead of falling back to muted grey
4. Unify the card entrance animation (`cardEntrance` → `cardIn`) across all components
5. Extract the shared `EARTHY_PALETTE` constant to a single source of truth

---

## Architecture

Three independent change sets, all self-contained:

- **Backend (Python):** Extend `fetch_place_cards` Step 4 Groq prompt to return `vibe_id` + `vibe_hint` per place. Tag each place dict with `area_name`. Tag places with `area_name` in the `areas_selected` handler.
- **Frontend — place cards:** Add `vibe_hint: string` to `PlaceCardData`; render hint line + area pill in `PlaceCardGrid`.
- **Frontend — polish:** Move `@keyframes cardIn` to `globals.css`; update VibeCardGrid + PlaceCardGrid animation values; extract `EARTHY_PALETTE` to `frontend/lib/palette.ts`.

---

## Tech Stack

Python 3.13, FastAPI, LangGraph, Groq (llama-3.3-70b-versatile), Next.js 16, React 18, TypeScript, inline `style={}` objects (no Tailwind in card components), pytest/asyncio.

---

## Global Constraints

- All new/changed card styling uses inline `style={}` objects only — no Tailwind utility classes
- Animation spec: `cardIn 0.42s cubic-bezier(0.16,1,0.3,1) both`, stagger `60ms` per card
- Earthy palette (canonical): `["#E07A5F","#7898B0","#D4A845","#C85050","#8EAB82","#D490AA"]`
- VIBE_THEME keys: `"adv"`, `"loc"`, `"spt"`, `"hid"` — these are the only valid `vibe_id` values
- `vibe_hint`: max 4 activity/experience phrases, comma-separated, lowercase, no trailing punctuation
- `area_name`: display name string (e.g. "Vagator"), sourced from `state["area_cards"]` lookup
- Run `pytest tests/` from project root for Python tests; `cd frontend && npm run build` for TypeScript checks
- No changes to `DAY_ACCENTS` in `page.tsx` — different color set, stays local

---

## Detailed Design

### 1. Backend: extend `fetch_place_cards` hook prompt

**File:** `app/services/stage_machine.py` — Step 4 of `fetch_place_cards` (lines ~290–310)

**Current hook prompt** asks Groq for a JSON object mapping `place_id → hook_string`.

**New hook prompt** asks for a JSON object mapping `place_id → {hook, vibe_id, vibe_hint}`:

```
Write a hook and vibe descriptor for each place in {area_name}, {destination}.
User vibe preference: {vibe_desc}.
Return a JSON object mapping place_id to an object with:
  - "hook": punchy one-liner under 15 words
  - "vibe_id": one of "adv" (adventure/outdoor), "loc" (local food/culture/nightlife),
               "spt" (spiritual/wellness/nature), "hid" (hidden gem/offbeat)
  - "vibe_hint": 3-4 comma-separated activities this place is best for, matching the user's vibe
Places: {json.dumps(dict(zip(all_ids, all_names)))}.
Return only valid JSON.
```

Where `vibe_desc` = `", ".join(selected_vibe_ids) or "general travel"`.

**Parsing change** — update the place dict builder at lines ~295–302:

```python
hook_data = hooks_raw.get(p["id"]) if isinstance(hooks_raw, dict) else {}
if isinstance(hook_data, str):
    # backwards compat: old flat string format
    hook_str = hook_data
    vibe_id = "adv"
    vibe_hint = ""
elif isinstance(hook_data, dict):
    hook_str = hook_data.get("hook") or f"A great spot in {area_name}"
    vibe_id = hook_data.get("vibe_id", "adv")
    vibe_hint = hook_data.get("vibe_hint", "")
else:
    hook_str = f"A great spot in {area_name}"
    vibe_id = "adv"
    vibe_hint = ""

place_dict = {
    "id": p["id"],
    "name": p["name"],
    "hook": hook_str,
    "photo_url": p["photo_url"],
    "vibe_id": vibe_id,
    "vibe_hint": vibe_hint,
    "area": area_name,   # <-- new: sourced from area_name already in scope
}
```

`area_name` is already computed at the top of `fetch_place_cards` (lines ~226–230) from `state["area_cards"]`. No additional lookup needed.

---

### 2. Backend: tag places with `area_name` in `areas_selected` handler

**File:** `app/services/stage_machine.py` — `determine_action`, `"areas_selected"` branch (lines ~403–420)

The handler already loops over `selected_areas`. Each area's places now arrive from `fetch_place_cards` with an `area` field already set (from fix above). No additional tagging needed in the handler — the `area` field flows through naturally since `fetch_place_cards` now sets it.

Verify: `flat_places` (used in the payload) will contain `{id, name, hook, photo_url, vibe_id, vibe_hint, area}` for each place.

---

### 3. Frontend: `PlaceCardData` interface

**File:** `frontend/lib/types.ts`

Current interface:
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

Add `vibe_hint`:
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

---

### 4. Frontend: render vibe hint + area pill in `PlaceCardGrid`

**File:** `frontend/components/MessageBubble.tsx` — `PlaceCardGrid` component

Inside each place card button (after the place name), add:

**Area pill** (above name, first child after the pending-activities badge):
```tsx
{p.area && (
  <div style={{
    display: "inline-block",
    background: "rgba(0,0,0,0.10)",
    color: "rgba(0,0,0,0.35)",
    fontSize: 9,
    fontFamily: "var(--font-dm-sans)",
    fontWeight: 600,
    borderRadius: 20,
    padding: "2px 7px",
    marginBottom: 4,
    letterSpacing: "0.02em",
  }}>
    {p.area}
  </div>
)}
```

**Vibe hint line** (below hook text):
```tsx
{p.vibe_hint && (
  <div style={{
    fontSize: 10,
    color: "rgba(240,239,232,0.55)",
    fontFamily: "var(--font-dm-sans)",
    marginTop: 4,
    lineHeight: 1.4,
  }}>
    {p.vibe_hint}
  </div>
)}
```

Both are guarded — they render nothing when the backend sends empty strings or the field is absent.

---

### 5. Frontend: animation unification

**File:** `frontend/app/globals.css`

Add `@keyframes cardIn` (identical to what the 3 Sprint 7 components currently define inline):
```css
@keyframes cardIn {
  from { opacity: 0; transform: translateY(16px) scale(0.97); }
  to   { opacity: 1; transform: none; }
}
```

Remove `@keyframes cardEntrance` from `globals.css` (nothing will reference it after this sprint).

**File:** `frontend/components/roammate/AreaCardGrid.tsx`, `ActivityOptions.tsx`, `RouteArcCards.tsx`

Remove the inline `<style>{`@keyframes cardIn{...}`}</style>` block from each component. The keyframe is now global.

**File:** `frontend/components/MessageBubble.tsx` — `VibeCardGrid` component

Find animation at line ~155:
```tsx
animation: `cardEntrance 0.38s cubic-bezier(0.34,1.3,0.64,1) both`,
animationDelay: `${index * 90}ms`,
```
Replace with:
```tsx
animation: `cardIn 0.42s cubic-bezier(0.16,1,0.3,1) both`,
animationDelay: `${index * 60}ms`,
```

**File:** `frontend/components/MessageBubble.tsx` — `PlaceCardGrid` component

Find animation at line ~312:
```tsx
animation: `cardEntrance 0.38s cubic-bezier(0.34,1.3,0.64,1) both`,
animationDelay: `${index * 80}ms`,
```
Replace with:
```tsx
animation: `cardIn 0.42s cubic-bezier(0.16,1,0.3,1) both`,
animationDelay: `${index * 60}ms`,
```

---

### 6. Frontend: extract `EARTHY_PALETTE` to shared module

**File to create:** `frontend/lib/palette.ts`
```typescript
export const EARTHY_PALETTE: string[] = [
  "#E07A5F", "#7898B0", "#D4A845", "#C85050", "#8EAB82", "#D490AA",
]
```

**Files to update** — remove local const, add import:
- `frontend/components/roammate/AreaCardGrid.tsx` — remove line 5, add `import { EARTHY_PALETTE } from "@/lib/palette"`
- `frontend/components/roammate/ActivityOptions.tsx` — same
- `frontend/components/roammate/RouteArcCards.tsx` — same

`DAY_ACCENTS` in `frontend/app/page.tsx` is a different array and stays local.

---

## Data Flow

```
state["selected_vibe_ids"] = ["adv", "hid"]
        ↓
fetch_place_cards (per area)
  Step 4 Groq prompt includes vibe context
        ↓
place dict: { id, name, hook, photo_url, vibe_id, vibe_hint, area }
        ↓
areas_selected handler → flat_places payload
        ↓
PlaceCardGrid receives { places: PlaceCardData[] }
  → VIBE_THEME[p.vibe_id].accent  (card accent color)
  → p.area pill                   (area label)
  → p.vibe_hint line              (activity hint)
```

---

## Testing

**Backend:**
- New test: `test_fetch_place_cards_includes_vibe_id_and_vibe_hint` — mock Groq to return the new `{hook, vibe_id, vibe_hint}` shape; assert place dicts contain all three fields
- New test: `test_fetch_place_cards_backwards_compat_flat_hook` — mock Groq to return old flat string shape; assert hook is preserved, vibe_id defaults to `"adv"`, vibe_hint defaults to `""`
- New test: `test_fetch_place_cards_includes_area_name` — assert `place["area"] == area_name` in output
- Existing `test_sprint7_areas_multiselect.py` — run to confirm `flat_places` payload now includes `vibe_id`, `vibe_hint`, `area` fields

**Frontend:**
- `cd frontend && npm run build` — TypeScript must compile clean

---

## File Map

| Status | File | Change |
|---|---|---|
| Modify | `app/services/stage_machine.py` | Extend hook prompt + parse `{hook, vibe_id, vibe_hint}` + add `area` field |
| Modify | `frontend/lib/types.ts` | Add `vibe_hint?: string` to `PlaceCardData` |
| Modify | `frontend/components/MessageBubble.tsx` | Render area pill + vibe hint in PlaceCardGrid; fix VibeCardGrid + PlaceCardGrid animation |
| Modify | `frontend/app/globals.css` | Add `@keyframes cardIn`; remove `@keyframes cardEntrance` |
| Modify | `frontend/components/roammate/AreaCardGrid.tsx` | Remove inline `cardIn` keyframe; import EARTHY_PALETTE |
| Modify | `frontend/components/roammate/ActivityOptions.tsx` | Remove inline `cardIn` keyframe; import EARTHY_PALETTE |
| Modify | `frontend/components/roammate/RouteArcCards.tsx` | Remove inline `cardIn` keyframe; import EARTHY_PALETTE |
| Create | `frontend/lib/palette.ts` | Export `EARTHY_PALETTE` |
| Create | `tests/unit/services/test_sprint8_place_cards.py` | 3 new backend tests |
