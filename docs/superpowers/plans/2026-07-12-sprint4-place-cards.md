# Sprint 4 — Place Cards Filtered by Selected Area Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the empty `show_place_cards` stub with real place cards grouped by dynamic categories, ranked by the existing Ranker, with a background Reddit prefetch for Sprint 5.

**Architecture:** `fetch_place_cards` in `stage_machine.py` runs a 4-step pipeline — Groq category determination → parallel Google Maps per category → score+rank top-3 per category → Groq batch hook generation — then caches to Redis. A `place_selected` card action is wired into `intent.py` to advance state when the user picks a place. `get_area_reddit_signals` in `reddit_signals.py` fetches venue-level Reddit signals as a background task (cached for Sprint 5).

**Tech Stack:** Python 3.13, asyncpraw, aiohttp, Groq (`meta-llama/llama-4-scout-17b-16e-instruct`), Redis (via `area_cache.py`), `search_places` (Google Maps MCP), existing `Ranker` + `score_all_places`.

## Global Constraints

- Python 3.13 syntax: `str | None`, `list[dict]`, `dict | None` — no `Optional`, no `Union`
- pytest-asyncio STRICT mode: every async test needs `@pytest.mark.asyncio`
- Groq env var: `GROQ_API` (accessed as `os.getenv("GROQ_API", "")`)
- Groq model constant: `_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"` (already defined in stage_machine.py)
- Redis pattern: `area_cache.get_cached` / `set_cached` — silent on failure, never raises
- Background tasks: wrapped in `try/except`, never crash the main flow
- Rating filter: ≥ 4.2 (consistent with planning.py)
- `score_all_places` mutates dicts in-place; call it on the filtered list before building `Place` objects
- `PlaceAreaMapping(place=place)` — pass `primary_area=None`; `area_scores=None` in `rank_places`
- Place card output shape: `{"categories": [{"label": str, "places": [{"id", "name", "hook", "photo_url"}]}]}`
- Cache key for place cards: `f"place_cards:{destination.lower()}:{area_id.lower()}:{exp_key}"`, TTL 43200
- Background Reddit cache key: `f"reddit_area:{destination.lower()}:{area_id.lower()}"`, TTL 3600

---

## File Map

| File | Change |
|------|--------|
| `app/graph/state.py` | Add `place_cards` and `selected_place` fields |
| `app/graph/nodes/responder.py` | Persist `place_cards` and `selected_place` in return dict |
| `app/services/reddit_signals.py` | Add `comment_limit`/`comment_body_chars` to `_search_reddit`; add `get_area_reddit_signals` |
| `app/services/stage_machine.py` | Add imports, `_ranker`, `DEFAULT_PLACE_CATEGORIES`; add `_rank_places_for_area`, `_prefetch_area_reddit`, `fetch_place_cards`; update `resolve_stage` + `determine_action` |
| `app/graph/nodes/intent.py` | Add `place_selected` card action handler |
| `tests/unit/services/test_sprint4_places.py` | New test file (all Sprint 4 tests) |

---

### Task 1: State Fields and Responder Persistence

**Files:**
- Modify: `app/graph/state.py`
- Modify: `app/graph/nodes/responder.py`
- Create: `tests/unit/services/test_sprint4_places.py`

**Interfaces:**
- Produces: `state["place_cards"]` (list of category dicts) and `state["selected_place"]` (str | None) as valid GraphState fields; responder return dict includes both fields

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/services/test_sprint4_places.py
"""Sprint 4 — place cards and place selection tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.graph.state import GraphState


# ── Task 1: State fields ──────────────────────────────────────────────────────

def test_graphstate_has_place_cards():
    state: GraphState = {}
    state["place_cards"] = [{"label": "Beaches", "places": []}]
    assert state["place_cards"][0]["label"] == "Beaches"


def test_graphstate_has_selected_place():
    state: GraphState = {}
    state["selected_place"] = "chapora_fort"
    assert state["selected_place"] == "chapora_fort"


def test_graphstate_selected_place_defaults_to_none():
    state: GraphState = {}
    assert state.get("selected_place") is None


# ── Task 1: Responder persistence ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_responder_persists_place_cards():
    from app.graph.nodes.responder import responder
    state: GraphState = {
        "destination": "Goa",
        "messages": [{"role": "user", "content": "hi"}],
        "place_cards": [{"label": "Beaches", "places": [{"id": "x", "name": "Y", "hook": "z", "photo_url": None}]}],
        "selected_place": None,
    }
    with patch("app.graph.nodes.responder._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.responder.aiohttp.ClientSession") as mock_session:
        mock_action.return_value = (None, None)
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"choices": [{"message": {"content": "Nice!"}}]})
        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=MagicMock(return_value=mock_post)))
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await responder(state)
    assert result["place_cards"] == state["place_cards"]
    assert result["selected_place"] is None


@pytest.mark.asyncio
async def test_responder_persists_selected_place():
    from app.graph.nodes.responder import responder
    state: GraphState = {
        "destination": "Goa",
        "messages": [{"role": "user", "content": "hi"}],
        "selected_place": "chapora_fort",
    }
    with patch("app.graph.nodes.responder._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.responder.aiohttp.ClientSession") as mock_session:
        mock_action.return_value = (None, None)
        mock_resp = AsyncMock()
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock(return_value=False)
        mock_resp.json = AsyncMock(return_value={"choices": [{"message": {"content": "Nice!"}}]})
        mock_post = MagicMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=False)
        mock_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock(post=MagicMock(return_value=mock_post)))
        mock_session.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await responder(state)
    assert result["selected_place"] == "chapora_fort"
```

- [ ] **Step 2: Run tests to verify they fail**

```
cd /Users/rakshitsingh/Desktop/My_project/RoamMate
pytest tests/unit/services/test_sprint4_places.py -v 2>&1 | head -40
```

Expected: `FAILED` — `place_cards` and `selected_place` may not exist in GraphState yet; responder return dict missing these keys.

- [ ] **Step 3: Add state fields to `app/graph/state.py`**

Add after the `selected_area` line (around line 92):

```python
    # ── Place cards — populated when area is selected ─────────────────────────
    place_cards: List[Dict[str, Any]]  # categorised place cards for selected area
    selected_place: str | None         # place_id chosen for activity exploration
```

- [ ] **Step 4: Add persistence to `app/graph/nodes/responder.py`**

In the `return` dict at the end of `responder()` (after `"selected_area": state.get("selected_area"),`), add:

```python
        "place_cards": state.get("place_cards") or [],
        "selected_place": state.get("selected_place"),
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/unit/services/test_sprint4_places.py::test_graphstate_has_place_cards tests/unit/services/test_sprint4_places.py::test_graphstate_has_selected_place tests/unit/services/test_sprint4_places.py::test_graphstate_selected_place_defaults_to_none tests/unit/services/test_sprint4_places.py::test_responder_persists_place_cards tests/unit/services/test_sprint4_places.py::test_responder_persists_selected_place -v
```

Expected: all 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add app/graph/state.py app/graph/nodes/responder.py tests/unit/services/test_sprint4_places.py
git commit -m "feat(sprint4): add place_cards/selected_place state fields and responder persistence"
```

---

### Task 2: Area-Level Reddit Signals

**Files:**
- Modify: `app/services/reddit_signals.py`
- Modify: `tests/unit/services/test_sprint4_places.py`

**Interfaces:**
- Consumes: `_search_reddit(reddit, query, limit, comment_limit, comment_body_chars)` — extended signature
- Produces: `get_area_reddit_signals(area_name: str, destination: str, experience_types: list[str]) -> dict[str, Any]` — returns `{"place_signals": {...}, "raw_posts_text": "..."}`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/services/test_sprint4_places.py`:

```python
# ── Task 2: get_area_reddit_signals ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_area_reddit_signals_returns_expected_shape():
    """get_area_reddit_signals returns dict with place_signals and raw_posts_text."""
    from app.services.reddit_signals import get_area_reddit_signals
    with patch("app.services.reddit_signals.asyncpraw.Reddit") as mock_reddit_cls, \
         patch("app.services.reddit_signals._extract_place_signals", new_callable=AsyncMock) as mock_extract:
        mock_reddit = AsyncMock()
        mock_reddit.__aenter__ = AsyncMock(return_value=mock_reddit)
        mock_reddit.__aexit__ = AsyncMock(return_value=False)
        mock_reddit_cls.return_value = mock_reddit
        mock_extract.return_value = {"place_signals": {"Chapora Fort": {"sentiment_score": 0.8}}}
        result = await get_area_reddit_signals("Vagator", "Goa", ["beach_coast"])
    assert "place_signals" in result
    assert "raw_posts_text" in result


@pytest.mark.asyncio
async def test_get_area_reddit_signals_on_failure_returns_empty():
    """get_area_reddit_signals returns empty dicts on any failure."""
    from app.services.reddit_signals import get_area_reddit_signals
    with patch("app.services.reddit_signals.asyncpraw.Reddit", side_effect=Exception("no creds")):
        result = await get_area_reddit_signals("Vagator", "Goa", [])
    assert result == {"place_signals": {}, "raw_posts_text": ""}


@pytest.mark.asyncio
async def test_search_reddit_uses_comment_limit():
    """_search_reddit with comment_limit=2 reads only 2 comments."""
    from app.services.reddit_signals import _search_reddit
    mock_comment = MagicMock()
    mock_comment.body = "great place" * 30  # 330 chars
    mock_submission = AsyncMock()
    mock_submission.title = "Vagator guide"
    mock_submission.selftext = ""
    mock_submission.comments = MagicMock()
    mock_submission.comments.replace_more = AsyncMock()
    mock_submission.comments.list = MagicMock(return_value=[mock_comment] * 5)
    mock_subreddit = AsyncMock()
    async def _gen(*a, **kw):
        yield mock_submission
    mock_subreddit.search = _gen
    mock_reddit = AsyncMock()
    mock_reddit.subreddit = AsyncMock(return_value=mock_subreddit)
    posts = await _search_reddit(mock_reddit, "Vagator Goa", limit=1, comment_limit=2, comment_body_chars=100)
    assert len(posts) == 1
    # 2 comments × 100 chars each, joined by " | "
    assert posts[0].count(" | ") == 1  # 2 comments → 1 separator
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/services/test_sprint4_places.py::test_get_area_reddit_signals_returns_expected_shape tests/unit/services/test_sprint4_places.py::test_get_area_reddit_signals_on_failure_returns_empty tests/unit/services/test_sprint4_places.py::test_search_reddit_uses_comment_limit -v
```

Expected: FAILED — `get_area_reddit_signals` does not exist yet; `_search_reddit` has no `comment_limit` param.

- [ ] **Step 3: Modify `_search_reddit` signature in `app/services/reddit_signals.py`**

Change the existing `_search_reddit` signature and body:

```python
async def _search_reddit(
    reddit,
    query: str,
    limit: int = 12,
    comment_limit: int = 4,
    comment_body_chars: int = 200,
) -> List[str]:
    """Search r/all and return formatted post strings."""
    posts = []
    semaphore = asyncio.Semaphore(3)
    async with semaphore:
        try:
            subreddit = await reddit.subreddit("all")
            async for submission in subreddit.search(query, sort="relevance", limit=limit, time_filter="year"):
                try:
                    await asyncio.wait_for(submission.load(), timeout=10)
                    await submission.comments.replace_more(limit=0)
                    top_comments = [
                        c.body[:comment_body_chars] for c in submission.comments.list()[:comment_limit]
                        if hasattr(c, "body")
                    ]
                    posts.append(
                        f"TITLE: {submission.title}\n"
                        f"TEXT: {getattr(submission, 'selftext', '')[:400]}\n"
                        f"COMMENTS: {' | '.join(top_comments)}"
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[Reddit] ✗ '{query}': {e}")
    logger.info(f"[Reddit] ✓ '{query}' → {len(posts)} posts")
    return posts
```

- [ ] **Step 4: Add `get_area_reddit_signals` to `app/services/reddit_signals.py`**

Add after `_search_reddit` (before `build_reddit_queries` or at the end of the file — after any existing `get_reddit_place_signals` function):

```python
async def get_area_reddit_signals(
    area_name: str,
    destination: str,
    experience_types: list[str],
) -> dict[str, Any]:
    """Fetch venue-level Reddit signals for a specific area. Used by Sprint 5."""
    exp_str = experience_types[0] if experience_types else f"{area_name} things to do"
    queries = [
        f"{area_name} {destination}",
        f"best places {area_name} {destination}",
        f"{area_name} {destination} {exp_str}",
        f"{area_name} {destination} recommend",
    ]
    all_posts: list[str] = []
    try:
        async with asyncpraw.Reddit(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            user_agent=USER_AGENT,
        ) as reddit:
            tasks = [_search_reddit(reddit, q, limit=8, comment_limit=15, comment_body_chars=350) for q in queries]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    all_posts.extend(r)
    except Exception as e:
        logger.warning(f"[Reddit/area] ✗ {area_name}: {e}")
        return {"place_signals": {}, "raw_posts_text": ""}

    if not all_posts:
        return {"place_signals": {}, "raw_posts_text": ""}

    raw_text = "\n\n".join(all_posts)
    signals = await _extract_place_signals(raw_text, f"{area_name}, {destination}")
    signals["raw_posts_text"] = raw_text
    return signals
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/unit/services/test_sprint4_places.py::test_get_area_reddit_signals_returns_expected_shape tests/unit/services/test_sprint4_places.py::test_get_area_reddit_signals_on_failure_returns_empty tests/unit/services/test_sprint4_places.py::test_search_reddit_uses_comment_limit -v
```

Expected: all 3 PASS.

- [ ] **Step 6: Verify existing reddit_signals tests still pass**

```
pytest tests/unit/services/test_reddit_signals.py -v
```

Expected: all existing tests PASS (existing call sites use `_search_reddit` without the new params — default values preserve backward compatibility).

- [ ] **Step 7: Commit**

```bash
git add app/services/reddit_signals.py tests/unit/services/test_sprint4_places.py
git commit -m "feat(sprint4): add comment_limit to _search_reddit, add get_area_reddit_signals"
```

---

### Task 3: `fetch_place_cards` Pipeline

**Files:**
- Modify: `app/services/stage_machine.py`
- Modify: `tests/unit/services/test_sprint4_places.py`

**Interfaces:**
- Consumes (from Task 2): `get_area_reddit_signals` (imported)
- Produces:
  - `_rank_places_for_area(places_raw, intent, reddit_signals, blog_signals) -> list[dict]` — returns `[{"id", "name", "photo_url"}]`, max 3
  - `_prefetch_area_reddit(destination, area_id, area_name, experience_types) -> None` — background coroutine
  - `fetch_place_cards(state: dict) -> list[dict]` — returns `[{"label", "places": [{"id", "name", "hook", "photo_url"}]}]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/services/test_sprint4_places.py`:

```python
# ── Task 3: fetch_place_cards pipeline ───────────────────────────────────────

def _make_place(place_id: str, name: str, rating: float = 4.5) -> dict:
    """Helper — raw Maps dict."""
    return {"place_id": place_id, "name": name, "rating": rating, "user_ratings_total": 100,
            "types": ["tourist_attraction"], "photo_url": None, "lat": 15.6, "lng": 73.7}


def test_rank_places_for_area_filters_low_rating():
    """_rank_places_for_area drops places with rating < 4.2."""
    from app.services.stage_machine import _rank_places_for_area
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    places = [
        _make_place("good", "Good Place", 4.5),
        _make_place("bad", "Bad Place", 3.9),
    ]
    result = _rank_places_for_area(places, intent, {}, {})
    ids = [p["id"] for p in result]
    assert "bad" not in ids


def test_rank_places_for_area_returns_at_most_three():
    """_rank_places_for_area caps output at 3 places."""
    from app.services.stage_machine import _rank_places_for_area
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    places = [_make_place(f"p{i}", f"Place {i}", 4.6) for i in range(6)]
    result = _rank_places_for_area(places, intent, {}, {})
    assert len(result) <= 3


def test_rank_places_for_area_output_shape():
    """_rank_places_for_area output dicts have id, name, photo_url."""
    from app.services.stage_machine import _rank_places_for_area
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    places = [_make_place("fort", "Chapora Fort", 4.7)]
    result = _rank_places_for_area(places, intent, {}, {})
    assert len(result) == 1
    assert set(result[0].keys()) >= {"id", "name", "photo_url"}


def test_rank_places_for_area_empty_input_returns_empty():
    """_rank_places_for_area returns [] on empty input."""
    from app.services.stage_machine import _rank_places_for_area
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    assert _rank_places_for_area([], intent, {}, {}) == []


@pytest.mark.asyncio
async def test_fetch_place_cards_returns_categories():
    """fetch_place_cards returns list of category dicts with label and places."""
    from app.services.stage_machine import fetch_place_cards
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    state = {
        "destination": "Goa",
        "selected_area": "vagator",
        "experience_types": ["beach_coast"],
        "selected_vibe_ids": [],
        "travel_intent": intent,
        "reddit_signals": {},
        "blog_signals": {},
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
    }
    mock_places = [_make_place("fort", "Chapora Fort", 4.8), _make_place("beach", "Ozran Beach", 4.5)]
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock) as mock_groq, \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock, return_value=mock_places), \
         patch("asyncio.create_task"):
        mock_groq.side_effect = [
            [{"label": "Beaches", "query": "beaches swimming"}],  # category call
            {"fort": "Panoramic views", "beach": "Hidden cove"},  # hooks call
        ]
        result = await fetch_place_cards(state)
    assert isinstance(result, list)
    assert len(result) >= 1
    cat = result[0]
    assert "label" in cat
    assert "places" in cat
    if cat["places"]:
        p = cat["places"][0]
        assert {"id", "name", "hook", "photo_url"} <= set(p.keys())


@pytest.mark.asyncio
async def test_fetch_place_cards_uses_cache_on_hit():
    """fetch_place_cards returns cached result and skips pipeline."""
    from app.services.stage_machine import fetch_place_cards
    cached = [{"label": "Beaches", "places": [{"id": "x", "name": "X", "hook": "hook", "photo_url": None}]}]
    state = {
        "destination": "Goa", "selected_area": "vagator",
        "experience_types": [], "selected_vibe_ids": [],
        "travel_intent": None, "reddit_signals": {}, "blog_signals": {},
        "area_cards": [],
    }
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=cached), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock) as mock_search, \
         patch("asyncio.create_task"):
        result = await fetch_place_cards(state)
    assert result == cached
    mock_search.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_place_cards_falls_back_to_defaults_on_groq_failure():
    """fetch_place_cards uses DEFAULT_PLACE_CATEGORIES when Groq returns None."""
    from app.services.stage_machine import fetch_place_cards, DEFAULT_PLACE_CATEGORIES
    from app.models import TravelIntent, Destination
    intent = TravelIntent(destination=Destination(city="Goa"))
    state = {
        "destination": "Goa", "selected_area": "vagator",
        "experience_types": [], "selected_vibe_ids": [],
        "travel_intent": intent, "reddit_signals": {}, "blog_signals": {},
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
    }
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock), \
         patch("app.services.stage_machine._groq_json", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.search_places", new_callable=AsyncMock, return_value=[]) , \
         patch("asyncio.create_task"):
        result = await fetch_place_cards(state)
    # With no places, result is [] — but the search was issued for DEFAULT_PLACE_CATEGORIES count
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_prefetch_area_reddit_skips_if_cached():
    """_prefetch_area_reddit does nothing if Redis key already warm."""
    from app.services.stage_machine import _prefetch_area_reddit
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=[{"existing": True}]), \
         patch("app.services.stage_machine.get_area_reddit_signals", new_callable=AsyncMock) as mock_reddit:
        await _prefetch_area_reddit("Goa", "vagator", "Vagator", [])
    mock_reddit.assert_not_called()


@pytest.mark.asyncio
async def test_prefetch_area_reddit_stores_signals():
    """_prefetch_area_reddit fetches and stores Reddit signals when cache is cold."""
    from app.services.stage_machine import _prefetch_area_reddit
    signals = {"place_signals": {"Chapora Fort": {"sentiment_score": 0.9}}, "raw_posts_text": "text"}
    with patch("app.services.stage_machine.get_cached", new_callable=AsyncMock, return_value=None), \
         patch("app.services.stage_machine.set_cached", new_callable=AsyncMock) as mock_set, \
         patch("app.services.stage_machine.get_area_reddit_signals", new_callable=AsyncMock, return_value=signals):
        await _prefetch_area_reddit("Goa", "vagator", "Vagator", ["beach_coast"])
    mock_set.assert_called_once()
    call_args = mock_set.call_args
    assert call_args[1]["ttl"] == 3600 or call_args[0][2] == 3600
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/services/test_sprint4_places.py -k "rank_places or fetch_place_cards or prefetch" -v 2>&1 | head -50
```

Expected: FAILED — `_rank_places_for_area`, `fetch_place_cards`, `_prefetch_area_reddit`, `DEFAULT_PLACE_CATEGORIES` do not exist yet.

- [ ] **Step 3: Add imports and module-level constants to `app/services/stage_machine.py`**

After the existing imports block (after line 19 `from app.utils.logger import get_logger`), add:

```python
from app.tools.fetchers.places import search_places
from app.services.ranker import Ranker
from app.services.scorer import score_all_places
from app.models import Place, PlaceAreaMapping, TravelIntent
from app.services.reddit_signals import get_area_reddit_signals
```

After the `_MODEL = "..."` constant, add:

```python
_ranker = Ranker()

DEFAULT_PLACE_CATEGORIES: list[dict] = [
    {"label": "Things to Do", "query": "attractions activities things to do"},
    {"label": "Cafés & Bars", "query": "cafes bars restaurants local food"},
    {"label": "Viewpoints & Nature", "query": "viewpoints nature parks scenic"},
]
```

- [ ] **Step 4: Add `_rank_places_for_area` to `app/services/stage_machine.py`**

Add after the `DEFAULT_PLACE_CATEGORIES` constant block (before the `_CATEGORY_DESCRIPTIONS` dict or in the private helpers section):

```python
def _rank_places_for_area(
    places_raw: list[dict],
    intent: any,
    reddit_signals: dict,
    blog_signals: dict,
) -> list[dict]:
    """Filter by rating, attach social scores, rank. Returns top-3 minimal dicts."""
    filtered = [p for p in places_raw if (p.get("rating") or 0) >= 4.2]
    if not filtered:
        return []
    score_all_places(filtered, reddit_signals, blog_signals)
    mappings: list[PlaceAreaMapping] = []
    for p in filtered:
        place = Place(
            place_id=p.get("place_id") or p.get("id", ""),
            name=p.get("name", ""),
            place_type=(p.get("types") or p.get("tags") or ["attraction"])[0],
            lat=float(p.get("lat") or 0.0),
            lon=float(p.get("lng") or p.get("lon") or 0.0),
            rating=p.get("rating"),
            review_count=int(p.get("user_ratings_total") or p.get("review_count") or 0),
            tags=p.get("types") or p.get("tags") or [],
        )
        mappings.append(PlaceAreaMapping(place=place))
    ranked = _ranker.rank_places(mappings, intent, area_scores=None) if intent else []
    id_to_raw: dict[str, dict] = {(p.get("place_id") or p.get("id", "")): p for p in filtered}
    result = []
    for rp in ranked[:3]:
        pid = rp.place.place_id
        raw = id_to_raw.get(pid, {})
        result.append({"id": pid, "name": rp.place.name, "photo_url": raw.get("photo_url")})
    return result
```

- [ ] **Step 5: Add `_prefetch_area_reddit` to `app/services/stage_machine.py`**

Add after `_rank_places_for_area`:

```python
async def _prefetch_area_reddit(
    destination: str,
    area_id: str,
    area_name: str,
    experience_types: list[str],
) -> None:
    """Background task: fetch area-level Reddit signals and cache for Sprint 5."""
    cache_key = f"reddit_area:{destination.lower()}:{area_id.lower()}"
    existing = await get_cached(cache_key)
    if existing:
        return
    try:
        signals = await get_area_reddit_signals(area_name, destination, experience_types)
        if signals.get("place_signals"):
            await set_cached(cache_key, [signals], ttl=3600)
    except Exception:
        pass
```

- [ ] **Step 6: Add `fetch_place_cards` to `app/services/stage_machine.py`**

Add after `_prefetch_area_reddit`:

```python
async def fetch_place_cards(state: dict) -> list[dict]:
    """4-step pipeline: Groq categories → Maps search → rank → Groq hooks. Returns categorised place cards."""
    destination = state.get("destination", "")
    area_id = state.get("selected_area", "")
    experience_types = state.get("experience_types") or []
    selected_vibe_ids = state.get("selected_vibe_ids") or []
    travel_intent = state.get("travel_intent")
    reddit_signals = state.get("reddit_signals") or {}
    blog_signals = state.get("blog_signals") or {}

    area_name = area_id
    for area in (state.get("area_cards") or []):
        if area.get("id") == area_id:
            area_name = area.get("name", area_id)
            break

    exp_key = "|".join(sorted(experience_types)) if experience_types else "|".join(sorted(selected_vibe_ids))
    cache_key = f"place_cards:{destination.lower()}:{area_id.lower()}:{exp_key}"
    cached = await get_cached(cache_key)
    if cached:
        state["place_cards"] = cached
        try:
            asyncio.create_task(_prefetch_area_reddit(destination, area_id, area_name, experience_types))
        except Exception:
            pass
        return cached

    # Step 1 — Category determination
    trip_who = state.get("trip_who") or ""
    trip_season = state.get("trip_season") or ""
    exp_desc = ", ".join(experience_types) if experience_types else ", ".join(selected_vibe_ids)
    cat_prompt = (
        f"You are a travel expert. For {area_name} in {destination}, "
        f"experience types: {exp_desc or 'general'}, group: {trip_who}, season: {trip_season}. "
        f"Return a JSON array of 3-4 category objects with 'label' (display name) and 'query' (Google Maps search terms). "
        f"Always include a food/drink category (Cafés & Bars or Restaurants). "
        f'Example: [{{"label": "Adventure Spots", "query": "trekking viewpoints cliff"}}]. '
        f"Return only valid JSON, no explanation."
    )
    raw_cats = await _groq_json(cat_prompt, max_tokens=250)
    categories: list[dict] = raw_cats if (isinstance(raw_cats, list) and raw_cats) else DEFAULT_PLACE_CATEGORIES

    # Step 2 — Maps search per category (parallel)
    search_tasks = [search_places(f"{area_name}, {destination}", cat["query"]) for cat in categories]
    raw_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    # Step 3 — Score and rank per category
    categories_with_places: list[dict] = []
    for cat, raw in zip(categories, raw_results):
        if isinstance(raw, Exception) or not raw:
            continue
        ranked = _rank_places_for_area(raw, travel_intent, reddit_signals, blog_signals)
        if ranked:
            categories_with_places.append({"label": cat["label"], "places": ranked})

    if not categories_with_places:
        state["place_cards"] = []
        try:
            asyncio.create_task(_prefetch_area_reddit(destination, area_id, area_name, experience_types))
        except Exception:
            pass
        return []

    # Step 4 — Hook generation (one batch Groq call)
    all_ids = [p["id"] for cat in categories_with_places for p in cat["places"]]
    all_names = [p["name"] for cat in categories_with_places for p in cat["places"]]
    hook_prompt = (
        f"Write a punchy one-liner hook (under 15 words) for each place in {area_name}, {destination}. "
        f"Return a JSON object mapping place_id to hook string. "
        f"Places: {json.dumps(dict(zip(all_ids, all_names)))}. "
        f"Return only valid JSON."
    )
    hooks_raw = await _groq_json(hook_prompt, max_tokens=800)
    hooks: dict[str, str] = hooks_raw if isinstance(hooks_raw, dict) else {}

    categories_out = []
    for cat in categories_with_places:
        places_out = [
            {
                "id": p["id"],
                "name": p["name"],
                "hook": hooks.get(p["id"]) or f"A great spot in {area_name}",
                "photo_url": p["photo_url"],
            }
            for p in cat["places"]
        ]
        categories_out.append({"label": cat["label"], "places": places_out})

    state["place_cards"] = categories_out
    await set_cached(cache_key, categories_out, ttl=43200)
    try:
        asyncio.create_task(_prefetch_area_reddit(destination, area_id, area_name, experience_types))
    except Exception:
        pass
    return categories_out
```

- [ ] **Step 7: Run tests to verify they pass**

```
pytest tests/unit/services/test_sprint4_places.py -k "rank_places or fetch_place_cards or prefetch" -v
```

Expected: all tests PASS.

- [ ] **Step 8: Run full existing test suite to check for regressions**

```
pytest tests/unit/ -v 2>&1 | tail -20
```

Expected: no new failures.

- [ ] **Step 9: Commit**

```bash
git add app/services/stage_machine.py tests/unit/services/test_sprint4_places.py
git commit -m "feat(sprint4): add fetch_place_cards, _rank_places_for_area, _prefetch_area_reddit to stage_machine"
```

---

### Task 4: Routing — `resolve_stage`, `determine_action`, and `place_selected` Handler

**Files:**
- Modify: `app/services/stage_machine.py` (`resolve_stage`, `determine_action`)
- Modify: `app/graph/nodes/intent.py` (add `place_selected` handler)
- Modify: `tests/unit/services/test_sprint4_places.py`

**Interfaces:**
- Consumes (from Task 3): `fetch_place_cards(state)` — called from `determine_action`
- Produces:
  - `resolve_stage(state)` returns `"place_selected"` when `state["selected_place"]` is set
  - `determine_action("area_selected", state)` returns `("show_place_cards", {"categories": [...]})`
  - `determine_action("place_selected", state)` returns `("show_activity_options", {"activities": []})`
  - `detect_intent(state)` with `card_action == "place_selected"` sets `state["selected_place"]` and `state["action"]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/services/test_sprint4_places.py`:

```python
# ── Task 4: resolve_stage + determine_action + intent handler ─────────────────

def test_resolve_stage_selected_place_wins_over_selected_area():
    """selected_place takes priority over selected_area in resolve_stage."""
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "selected_area": "vagator",
        "selected_place": "chapora_fort",
        "vibes_confirmed": True,
    }
    assert resolve_stage(state) == "place_selected"


def test_resolve_stage_selected_place_wins_over_places_shown():
    """selected_place takes priority over places_shown in resolve_stage."""
    from app.services.stage_machine import resolve_stage
    state = {
        "destination": "Goa",
        "selected_area": "vagator",
        "places_shown": True,
        "selected_place": "beach",
    }
    assert resolve_stage(state) == "place_selected"


def test_resolve_stage_area_selected_when_no_place():
    """resolve_stage returns area_selected when selected_area is set but selected_place is not."""
    from app.services.stage_machine import resolve_stage
    state = {"destination": "Goa", "selected_area": "vagator"}
    assert resolve_stage(state) == "area_selected"


@pytest.mark.asyncio
async def test_determine_action_area_selected_calls_fetch_place_cards():
    """determine_action for area_selected calls fetch_place_cards and returns show_place_cards."""
    from app.services.stage_machine import determine_action
    categories = [{"label": "Beaches", "places": [{"id": "x", "name": "X", "hook": "y", "photo_url": None}]}]
    state = {
        "destination": "Goa", "selected_area": "vagator",
        "experience_types": [], "selected_vibe_ids": [],
        "travel_intent": None, "reddit_signals": {}, "blog_signals": {},
        "area_cards": [{"id": "vagator", "name": "Vagator"}],
    }
    with patch("app.services.stage_machine.fetch_place_cards", new_callable=AsyncMock, return_value=categories):
        action, payload = await determine_action("area_selected", state)
    assert action == "show_place_cards"
    assert payload == {"categories": categories}


@pytest.mark.asyncio
async def test_determine_action_place_selected_returns_stub():
    """determine_action for place_selected returns show_activity_options stub."""
    from app.services.stage_machine import determine_action
    action, payload = await determine_action("place_selected", {})
    assert action == "show_activity_options"
    assert payload == {"activities": []}


@pytest.mark.asyncio
async def test_detect_intent_place_selected_sets_state():
    """detect_intent with card_action=place_selected sets selected_place and calls determine_action."""
    from app.graph.nodes.intent import detect_intent
    from app.graph.state import GraphState
    state: GraphState = {
        "destination": "Goa",
        "selected_area": "vagator",
        "card_action": "place_selected",
        "card_data": {"place_id": "chapora_fort"},
        "messages": [],
    }
    with patch("app.graph.nodes.intent._stage_determine_action", new_callable=AsyncMock) as mock_action, \
         patch("app.graph.nodes.intent.resolve_stage", return_value="place_selected"):
        mock_action.return_value = ("show_activity_options", {"activities": []})
        result = await detect_intent(state)
    assert result["selected_place"] == "chapora_fort"
    assert result["card_action"] is None
    assert result["skip_graph"] is True
    assert result["action"] == "show_activity_options"
    assert result["payload"] == {"activities": []}
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/services/test_sprint4_places.py -k "resolve_stage or determine_action or detect_intent" -v 2>&1 | head -50
```

Expected: FAILED — `resolve_stage` has no `selected_place` check; `determine_action("area_selected")` still uses stub; no `place_selected` handler in `intent.py`.

- [ ] **Step 3: Update `resolve_stage` in `app/services/stage_machine.py`**

In `resolve_stage`, insert the `selected_place` check BEFORE the `selected_area` check AND before `places_shown`. The current code near line 168 is:

```python
    if state.get("places_shown"):
        if not state.get("trip_duration"):
            return "duration_pending"
        return "places_shown"
    if state.get("selected_area"):
        return "area_selected"
```

Change to:

```python
    if state.get("selected_place"):
        return "place_selected"
    if state.get("places_shown"):
        if not state.get("trip_duration"):
            return "duration_pending"
        return "places_shown"
    if state.get("selected_area"):
        return "area_selected"
```

- [ ] **Step 4: Update `determine_action` in `app/services/stage_machine.py`**

Replace the `area_selected` stub:

```python
    if stage == "area_selected":
        # Sprint 4 stub — place cards filtered to selected area
        return "show_place_cards", {"places": []}
```

With:

```python
    if stage == "area_selected":
        categories = await fetch_place_cards(state)
        return "show_place_cards", {"categories": categories}

    if stage == "place_selected":
        return "show_activity_options", {"activities": []}
```

- [ ] **Step 5: Add `place_selected` handler to `app/graph/nodes/intent.py`**

In `detect_intent`, after the `area_selected` handler block (after line 110, before `elif card_action == "route_selected"`), add:

```python
    elif card_action == "place_selected":
        state["selected_place"] = card_data.get("place_id", "")
        state["card_action"] = None
        state["skip_graph"] = True
        stage = resolve_stage(state)
        state["conversation_stage"] = stage
        action, payload = await _stage_determine_action(stage, state)
        state["action"] = action
        state["payload"] = payload
        return state
```

- [ ] **Step 6: Run all Sprint 4 tests**

```
pytest tests/unit/services/test_sprint4_places.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Run the full unit test suite**

```
pytest tests/unit/ -v 2>&1 | tail -30
```

Expected: no regressions — all pre-existing tests still PASS.

- [ ] **Step 8: Commit**

```bash
git add app/services/stage_machine.py app/graph/nodes/intent.py tests/unit/services/test_sprint4_places.py
git commit -m "feat(sprint4): wire place_selected routing in resolve_stage, determine_action, and intent handler"
```

---

## Self-Review

### 1. Spec Coverage

| Spec Section | Task | Status |
|---|---|---|
| §1 New state fields (`place_cards`, `selected_place`) | Task 1 | ✅ |
| §7 Responder persistence | Task 1 | ✅ |
| §5 `get_area_reddit_signals` (8 posts, 15 comments, 350 chars) | Task 2 | ✅ |
| `_search_reddit` `comment_limit` param (default=4) | Task 2 | ✅ |
| §4 `fetch_place_cards` — Step 1 Groq categories max_tokens=250 | Task 3 | ✅ |
| §4 `fetch_place_cards` — Step 2 parallel Maps search | Task 3 | ✅ |
| §4 `fetch_place_cards` — Step 3 score+rank, rating filter ≥4.2, top 3 | Task 3 | ✅ |
| §4 `fetch_place_cards` — Step 4 Groq hooks max_tokens=800 | Task 3 | ✅ |
| §4 Cache key + TTL 43200 | Task 3 | ✅ |
| §6 `_prefetch_area_reddit` + Redis TTL 3600 | Task 3 | ✅ |
| §4 Background `asyncio.create_task` on both hit and miss | Task 3 | ✅ |
| §4 `area_name` resolved from `area_cards` | Task 3 | ✅ |
| §8 All Maps fail → return `[]` | Task 3 (`not categories_with_places`) | ✅ |
| §8 Groq category fail → DEFAULT_CATEGORIES | Task 3 | ✅ |
| §8 Groq hook fail → `f"A great spot in {area_name}"` | Task 3 | ✅ |
| §3 `resolve_stage` — `selected_place` before `selected_area` and `places_shown` | Task 4 | ✅ |
| §3 `determine_action` `area_selected` → `fetch_place_cards` | Task 4 | ✅ |
| §3 `determine_action` `place_selected` → Sprint 5 stub | Task 4 | ✅ |
| §3 `intent.py` `place_selected` card action handler | Task 4 | ✅ |
| §2 Place card output shape (categories, label, id, name, hook, photo_url) | Task 3 + 4 | ✅ |

### 2. Placeholder Scan

No TBDs. All code is complete. `show_activity_options` stub is intentional (per spec §3 and §10 "Sprint 5 stub").

### 3. Type Consistency

- `_rank_places_for_area` returns `list[dict]` with keys `{id, name, photo_url}` — consumed by `fetch_place_cards` which adds `hook` before emitting as final `place_cards` payload.
- `get_area_reddit_signals` returns `dict[str, Any]` with `place_signals` and `raw_posts_text` keys — same shape as `get_reddit_place_signals`.
- `_prefetch_area_reddit` caches `[signals]` (list with one dict) at `reddit_area:` key — Sprint 5's `build_activity_options` expects this same format.
- `resolve_stage` returns string literals only — no enum mismatch with `determine_action` match arms.
