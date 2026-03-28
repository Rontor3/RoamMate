"""
nodes/discovery.py — Phase 1: Discovery
3 parallel MCP calls: weather + Tavily blog vibe + Tavily events.
Caches blog results at blogs:{dest}:{month} TTL 24hr.
"""
import asyncio

from app.graph.state import GraphState
from app.services.blog_signals import get_blog_signals, get_tavily_events
from app.services.reddit_signals import get_reddit_place_signals
from app.tools.fetchers.weather import get_current_weather
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def discovery(state: GraphState) -> GraphState:
    """Phase 1 — fetch weather, blog vibe signals, events, and Reddit tips in parallel."""
    dest = state.get("destination", "")
    intent = state.get("travel_intent")
    vibe = intent.vibe[0].value if intent and intent.vibe else None

    logger.info(f"discovery: parallel fetch for '{dest}' (vibe={vibe})")

    # 4 parallel calls — Reddit added for local real-world signals even in discovery
    weather_task = _get_weather(dest)
    blog_task = get_blog_signals(dest, vibe)
    events_task = get_tavily_events(dest)
    reddit_task = get_reddit_place_signals(intent) if intent else asyncio.sleep(0, result={"place_signals": {}, "raw_posts_text": ""})

    weather, blog, events, reddit = await asyncio.gather(
        weather_task, blog_task, events_task, reddit_task, return_exceptions=True
    )

    state["weather_data"] = weather if not isinstance(weather, Exception) else {}
    state["blog_signals"] = blog if not isinstance(blog, Exception) else {"sources": [], "top_answer": ""}
    state["reddit_signals"] = reddit if not isinstance(reddit, Exception) else {"place_signals": {}, "raw_posts_text": ""}

    # Merge events into blog_signals
    if not isinstance(events, Exception):
        state["blog_signals"]["events"] = events

    # Append Reddit top snippets into blog top_answer so the responder sees local tips
    reddit_text = state["reddit_signals"].get("raw_posts_text", "") if isinstance(state["reddit_signals"], dict) else ""
    if reddit_text:
        existing = state["blog_signals"].get("top_answer", "")
        state["blog_signals"]["top_answer"] = (existing + "\n\n" + reddit_text[:1000]).strip()

    logger.info(f"discovery complete: weather={bool(state['weather_data'])}, blog_sources={len(state.get('blog_signals', {}).get('sources', []))}, reddit_posts={bool(reddit_text)}")
    return state


async def _get_weather(destination: str) -> dict:
    """Fetch weather from OpenWeatherMap MCP server."""
    try:
        return await get_current_weather(destination)
    except Exception as e:
        logger.warning(f"Weather fetch failed for '{destination}': {e}")
        return {}
