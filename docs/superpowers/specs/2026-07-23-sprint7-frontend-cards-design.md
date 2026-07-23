# Sprint 7: Frontend Card Wiring Design Spec

## Goal

Wire four missing card actions into the RoamMate Next.js frontend (`show_area_cards`, `show_activity_options`, `show_route_arcs`, `open_day_planner`) and fix area selection to be multi-select end-to-end, enabling a full visual playthrough from experience selection to day planner.

## Architecture

**Option C — one file per card component.** Each new card lives in its own file under `frontend/components/roammate/`. `MessageBubble.tsx` imports and renders them. The existing inline card pattern (`VibeCardGrid`, `PlaceCardGrid`, etc.) stays untouched.

The day planner doesn't produce an in-chat card — it auto-populates and opens the existing `DaySidebar` by lifting state through `page.tsx`.

A small backend change accompanies this sprint: area selection becomes multi-select (`area_selected` → `areas_selected`, `selected_area: str` → `selected_areas: List[str]`).

## Design Tokens

Base dark tokens (page shell, activity card container, sidebar):

| Token | Value | Usage |
|---|---|---|
| `bg` | `#0F0F0D` | Page background |
| `surface` | `#161614` | Activity card container background |
| `border` | `#2A2A26` | Activity card border, ghost button border |
| `text` | `#F0EFE8` | Light text on dark surfaces |
| `muted` | `#8A8A80` | Eyebrows, secondary text on dark surfaces |

**Earthy card palette** — assigned by index (0–5), cycling for longer lists:

| Index | Name | Hex | Used on |
|---|---|---|---|
| 0 | Coral | `#E07A5F` | Area card 1, activity row 1, arc card 1 |
| 1 | Warm steel | `#7898B0` | Area card 2, activity row 2, arc card 2 |
| 2 | Gold | `#D4A845` | Area card 3, activity row 3, arc card 3 |
| 3 | Brick red | `#C85050` | Area card 4, activity row 4 |
| 4 | Sage | `#8EAB82` | Activity row 5+ |
| 5 | Blush | `#D490AA` | Activity row 6+ |

**Filled card style** — all area cards, activity rows, and arc cards use their earthy color as `background`. Text on colored backgrounds is always `#0F0F0D` (near-black). Secondary/muted text uses `rgba(0,0,0,0.55)`. Tags use `rgba(0,0,0,0.12)` background with `rgba(0,0,0,0.55)` text. Borders use `rgba(0,0,0,0.12)`.

**Typography:** `var(--font-neuton)` for titles/names (18px 700); `var(--font-dm-sans)` for all body, labels, buttons.

**Animation:** `ease-out-expo` `cubic-bezier(0.16, 1, 0.3, 1)` at 0.42s with staggered `animationDelay` per card (0.06s increments). Replaces the existing `cardEntrance` bounce easing throughout the new components.

**Sizing:** Cards use `borderRadius: 16`, `padding: 18px`. Area cards have `minHeight: 148px` with flex-column layout so tags pin to the bottom. Activity rows use `borderRadius: 12`, `padding: 13px 14px`. Arc card header padding `16px 18px 13px`, body `13px 18px 16px`.

**Layout:** All layout via inline `style={}` objects. No Tailwind utility classes in new card components. Chat column max-width 680px matches existing page layout.

---

## Backend Changes

### 1. `app/graph/state.py`
- Remove: `selected_area: Optional[str]`
- Add: `selected_areas: List[str]`

### 2. `app/graph/nodes/intent.py`
- Remove handler for `card_action == "area_selected"`
- Add handler for `card_action == "areas_selected"`:
  ```python
  elif card_action == "areas_selected":
      state["selected_areas"] = card_data.get("area_ids", [])
  ```

### 3. `app/services/stage_machine.py`
- `_STAGE_RULES`: update lambda that checked `state.get("selected_area")` → `bool(state.get("selected_areas"))`
- `determine_action("areas_selected")`: call `fetch_place_cards` for each area ID, merge and deduplicate results, return `show_place_cards` payload
- `resolve_stage` / `determine_action`: anywhere `selected_area` is read, switch to `selected_areas`

### 4. `app/graph/nodes/responder.py`
- Replace `"selected_area": state.get("selected_area")` with `"selected_areas": state.get("selected_areas") or []`

---

## Frontend Changes

### New File 1: `AreaCardGrid.tsx`

**Path:** `frontend/components/roammate/AreaCardGrid.tsx`

**Triggered by:** `message.action === "show_area_cards"`

**Payload shape:**
```ts
areas: Array<{
  id: string
  name: string
  zone: string | null      // eyebrow label e.g. "Popular zone"
  teaser: string           // 1-sentence description
  summary: string          // longer text (not shown in card)
  tags: string[]           // shown as small chips
  photo_url: string | null // reserved for future photo support
}>
```

**Behaviour:**
- Multi-select toggle grid (2 columns)
- Tapping a card toggles selected state; multiple areas can be selected
- "Explore these areas →" confirm button appears below grid once ≥1 area selected
- On confirm: fires `cardAction("areas_selected", { area_ids: string[] })`

**Visual spec (per card):**
- `borderRadius: 16`, `padding: 18px`, `minHeight: 148px`, flex-column with `justifyContent: space-between`
- `background`: earthy palette color by index (see palette table above)
- `border: 1.5px solid rgba(0,0,0,0.12)`
- Top-right circular checkbox (20px): `border: 1.5px solid rgba(0,0,0,0.22)`, filled + ✓ on selection
- Selected state: checkbox fills `rgba(0,0,0,0.18)`, border removed
- Zone eyebrow: 9px DM Sans uppercase `rgba(0,0,0,0.45)`
- Area name: Neuton 18px 700, `color: #0F0F0D`
- Teaser: DM Sans 11.5px `rgba(0,0,0,0.62)`, `lineHeight: 1.5`, `flex: 1`
- Tags row pinned to bottom: chips `background: rgba(0,0,0,0.12)`, `color: rgba(0,0,0,0.55)`, 9.5px, `borderRadius: 20`, `padding: 3px 9px`
- Confirm button: `background` of index-0 color (Coral), `color: #0F0F0D`, `borderRadius: 20`, `padding: 12px 0`, 13px 700
- Animation: `cardIn` keyframe, `ease-out-expo`, 0.42s, stagger 0.06s per card

---

### New File 2: `ActivityOptions.tsx`

**Path:** `frontend/components/roammate/ActivityOptions.tsx`

**Triggered by:** `message.action === "show_activity_options"`

**Payload shape:**
```ts
activities: Array<{
  id: string
  label: string
  duration: string   // e.g. "2h", "45m"
  time: string       // "morning" | "afternoon" | "evening"
  vibe: string
}>
place_id: string
place_name: string
```

**Behaviour:**
- Multi-select toggle list (vertical, not grid)
- All activities deselected by default
- "Add to my trip →" (primary): sends `activities_for_place` with `{ place_id, activities: string[] }` where `activities` is the array of selected `label` strings. Returns user to place cards.
- "Done — finalise plan" (ghost): sends `activities_confirmed` with `{}`. Moves to pace selection.
- Both buttons always visible; "Add to my trip →" disabled when nothing selected.

**Visual spec:**
- Outer card: `background: #161614`, `border: 1.5px solid #2A2A26`, `borderRadius: 16`, `padding: 18`
- Header: eyebrow "Pick activities" (9px DM Sans uppercase `#8A8A80`) + place name (Neuton 18px 700, `color: #F0EFE8`)
- Each activity row: `display: flex`, `alignItems: center`, `gap: 12`, `borderRadius: 12`, `padding: 13px 14px`, `minHeight: 48px`
  - `background`: earthy palette color by row index (0 = Coral, 1 = Warm steel, 2 = Gold, etc.)
  - `border: 1.5px solid rgba(0,0,0,0.1)`
  - Toggle circle (20px): `border: 1.5px solid rgba(0,0,0,0.22)` unselected; `background: rgba(0,0,0,0.18)` + ✓ selected
  - Label: DM Sans 13px 500, `color: #0F0F0D`, `flex: 1`
  - Meta group (right): duration pill + time badge, both `background: rgba(0,0,0,0.12)`, `color: rgba(0,0,0,0.55)`, `borderRadius: 20`, `padding: 3px 9px`
- Rows stacked with `gap: 10` (not border-separated)
- Buttons: `marginTop: 16`, `flexDirection: column`, `gap: 9`
  - "Add to my trip →": `background` of index-0 row color (Coral `#E07A5F`), `color: #0F0F0D`, `borderRadius: 20`, `padding: 12px 0`, DM Sans 13px 700. `opacity: 0.4` + `pointerEvents: none` when nothing selected.
  - "Done — finalise plan": transparent bg, `border: 1.5px solid #2A2A26`, `borderRadius: 20`, `padding: 11px 0`, DM Sans 13px 600, `color: #F0EFE8`

---

### New File 3: `RouteArcCards.tsx`

**Path:** `frontend/components/roammate/RouteArcCards.tsx`

**Triggered by:** `message.action === "show_route_arcs"`

**Payload shape:**
```ts
arcs: Array<{
  id: string
  label: string         // e.g. "North → South"
  description: string   // 1-sentence rationale
  place_order: string[] // ordered place names
}>
```

**Behaviour:**
- Single-select: tapping a card fires `route_arc_selected` immediately
- Sends: `cardAction("route_arc_selected", { arc: { id, label, place_order } })`
- No confirm button — selection is instant

**Visual spec (per card):**
- Outer wrapper: `background` of earthy palette color by index, `border: 1.5px solid rgba(0,0,0,0.12)`, `borderRadius: 16`, `overflow: hidden`, `marginBottom: 12`
- Header: `padding: 16px 18px 13px`, `borderBottom: 1px solid rgba(0,0,0,0.1)`
  - Arc label: Neuton 18px 800, `color: #0F0F0D`
- Body: `padding: 13px 18px 16px`
  - Description: DM Sans 12px `rgba(0,0,0,0.58)`, `lineHeight: 1.5`, `marginBottom: 12`
  - Place flow: `display: flex`, `flexWrap: wrap`, `gap: 6`, `alignItems: center`
    - Stop chip: `background: rgba(0,0,0,0.12)`, `color: rgba(0,0,0,0.65)`, `borderRadius: 20`, `padding: 4px 11px`, 10.5px text
    - Arrow: `color: rgba(0,0,0,0.35)`, 11px
- Animation: `cardIn` keyframe, `ease-out-expo`, stagger 0.06s per card

---

### Modified File 4: `MessageBubble.tsx`

**Changes only — no restructuring:**

1. Add imports at top:
   ```ts
   import AreaCardGrid from "./roammate/AreaCardGrid"
   import ActivityOptions from "./roammate/ActivityOptions"
   import RouteArcCards from "./roammate/RouteArcCards"
   ```

2. Add three render blocks inside the `AISlot` section, alongside existing blocks:
   ```tsx
   {message.action === "show_area_cards" && message.payload?.areas && (
     <AreaCardGrid areas={message.payload.areas} onConfirm={(ids) => cardAction("areas_selected", { area_ids: ids })} />
   )}
   {message.action === "show_activity_options" && message.payload?.activities && (
     <ActivityOptions
       activities={message.payload.activities}
       placeId={message.payload.place_id}
       placeName={message.payload.place_name}
       onAdd={(placeId, activities) => cardAction("activities_for_place", { place_id: placeId, activities })}
       onDone={() => cardAction("activities_confirmed", {})}
     />
   )}
   {message.action === "show_route_arcs" && message.payload?.arcs && (
     <RouteArcCards arcs={message.payload.arcs} onSelect={(arc) => cardAction("route_arc_selected", { arc })} />
   )}
   ```

3. Add `onDayPlanReady?: (plan: DayPlanDay[], brief: DestinationBrief) => void` to `MessageBubbleProps`.

4. In the message rendering loop, when `message.action === "open_day_planner"`, call `onDayPlanReady?.(message.payload.plan, message.payload.brief)` — no in-chat card rendered.

5. **PlaceCardGrid update** (inline component, stays in `MessageBubble.tsx`):
   - Accept optional `pendingActivities?: Record<string, string[]>` prop from `message.payload.pending_activities`
   - For each place card, if `pendingActivities[place.id]` exists, show a small green badge (`#03C03C`, 9px, "N acts") top-left
   - Add "Done — finalise plan" ghost button below the grid when `pendingActivities` is non-empty
   - Ghost button fires `cardAction("activities_confirmed", {})`

---

### Modified File 5: `app/page.tsx`

**Changes only:**

1. Add state:
   ```ts
   const [dayPlan, setDayPlan] = useState<DayPlanDay[] | null>(null)
   const [dayBrief, setDayBrief] = useState<DestinationBrief | null>(null)
   ```

2. Add `handleDayPlanReady` callback:
   ```ts
   const handleDayPlanReady = useCallback((plan: DayPlanDay[], brief: DestinationBrief) => {
     setDayPlan(plan)
     setDayBrief(brief)
     setDaySidebarOpen(true)
   }, [])
   ```

3. Pass to `MessageBubble`: `onDayPlanReady={handleDayPlanReady}`

4. Pass `plan` and `brief` to `DaySidebar`: `<DaySidebar plan={dayPlan} brief={dayBrief} isOpen={daySidebarOpen} onClose={() => setDaySidebarOpen(false)} />`

---

### Modified File 6: `Sidebar.tsx`

**Changes only — replaces hardcoded placeholder data with real props:**

**New props:**
```ts
interface SidebarProps {
  isOpen: boolean
  onClose: () => void
  plan: DayPlanDay[] | null
  brief: DestinationBrief | null
}
```

**DayPlanDay shape:**
```ts
interface DayPlanDay {
  day: number
  title: string
  activities: Array<{ time: string; activity: string; place: string; duration: string }>
  note: string
}
```

**DestinationBrief shape:**
```ts
interface DestinationBrief {
  weather: string
  language_tip: string
  lingo: string[]          // array of "phrase — meaning" strings
  transport: string
  local_events: string
  permits: string
  safety: string
  currency: string
}
```

**Sidebar sections when `plan` and `brief` are non-null:**

1. **Destination intel** (top, collapsible):
   - `weather`, `transport`, `currency`, `safety` as icon+text rows
   - Icons from existing `Icon.tsx` system; fallback to emoji if icon not available
   - `language_tip` as a single-line note
   - `local_events` and `permits` only shown if not "None"

2. **Local lingo** (below intel):
   - Each string in `brief.lingo` rendered as a small chip
   - Phrase portion (before " — ") in `#03C03C` 600 weight
   - Meaning portion (after " — ") in muted 10px

3. **Day cards** (main section):
   - One card per day in `plan`
   - Day number eyebrow (`#03C03C`, uppercase), day title (Neuton 13px 700)
   - Activity list: time (9.5px muted, fixed 44px width) + activity name + place name (muted below)
   - Day note as 9.5px italic muted text at bottom of card

**Empty state** (when `plan` is null):
- "Your day plan will appear here once you complete the trip setup." — centred, muted, 11px

---

## TypeScript Interfaces

Add to `frontend/lib/types.ts`:
```ts
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

---

## Card Action Contract Summary

| User action | card_action sent | card_data |
|---|---|---|
| Confirm area selection | `areas_selected` | `{ area_ids: string[] }` |
| Add activities for place | `activities_for_place` | `{ place_id: string, activities: string[] }` |
| Finalise all activities (from activity card) | `activities_confirmed` | `{}` |
| Finalise all activities (from place card) | `activities_confirmed` | `{}` |
| Select route arc | `route_arc_selected` | `{ arc: { id, label, place_order } }` |

---

## What Is NOT in Scope

- Photo support for area/place cards (`photo_url` field reserved but not rendered)
- PlacePanel / AreaPanel full-screen detail overlays
- Offline or error states beyond what the existing app handles
- Any changes to Phase0 wizard or existing vibe/route card components
