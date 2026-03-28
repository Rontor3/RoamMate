"""
reddit_signals.py — Direct asyncpraw Reddit access (no MCP hop).
Builds structured place signals: {place_name: {sentiment_score, crowd_signal, vibe_tags, mention_count, review_highlights}}
Groq extracts structured signals per place from raw Reddit posts.
"""
import asyncio
import json
import os
import aiohttp
import asyncpraw
from typing import Dict, Any, List, Optional

from app.utils.logger import get_logger
from app.models import TravelIntent

logger = get_logger(__name__)

CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
USER_AGENT = "platform:roam_mate:v2.0 (by u/Admirable-Star-1447)"
GROQ_API_KEY = os.getenv("GROQ_API", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


def build_reddit_queries(intent: TravelIntent) -> List[str]:
    """Generate up to 4 targeted Reddit search queries from a TravelIntent."""
    dest = intent.destination.city or intent.destination.region or intent.destination.area or ""
    queries = []

    if dest:
        # Use broader, more natural Reddit search phrasing
        queries.append(f"{dest} itinerary")
        queries.append(f"{dest} travel")
        
        if intent.interests:
            queries.append(f"{dest} {intent.interests[0]}")
        if intent.vibe:
            queries.append(f"{dest} {intent.vibe[0].value}")
            
        # Fallback to just the destination name if we need more queries
        if len(queries) < 4:
            queries.append(dest)

    # Clean up and ensure uniqueness
    unique_queries = []
    for q in queries:
        clean_q = q.strip()
        if clean_q and clean_q not in unique_queries:
            unique_queries.append(clean_q)

    return unique_queries[:4]


async def _search_reddit(reddit, query: str, limit: int = 12) -> List[str]:
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
                        c.body[:200] for c in submission.comments.list()[:4]
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


async def _extract_place_signals(raw_posts: str, destination: str) -> Dict[str, Any]:
    """Use Groq to extract structured place signals from raw Reddit text."""
    system = (
        "You are a travel data extractor. Given Reddit posts, extract place signals.\n"
        "Return ONLY valid JSON like:\n"
        '{"place_signals": {"Place Name": {"sentiment_score": 0.8, "crowd_signal": "low", '
        '"vibe_tags": ["chill", "local"], "mention_count": 3, "review_highlights": ["great coffee"]}}}'
    )
    user_msg = f"Destination: {destination}\n\nReddit posts:\n{raw_posts[:4000]}"

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 1000,
        "temperature": 0.1,
    }

    logger.info(f"[Groq/reddit-extract] → extracting place signals for '{destination}'")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                content = result["choices"][0]["message"]["content"]
                import re
                match = re.search(r"\{[\s\S]*\}", content)
                if match:
                    parsed = json.loads(match.group())
                    n = len(parsed.get("place_signals", {}))
                    logger.info(f"[Groq/reddit-extract] ✓ extracted signals for {n} places")
                    return parsed
    except Exception as e:
        logger.error(f"[Groq/reddit-extract] ✗ {e}")

    return {"place_signals": {}}


async def get_reddit_place_signals(
    intent: TravelIntent,
    post_limit: int = 12,
) -> Dict[str, Any]:
    """
    Main entry point. Returns:
    {
      "place_signals": { "Place Name": { sentiment_score, crowd_signal, vibe_tags, mention_count, review_highlights } },
      "raw_posts_text": str  # for ScoringEngine crowd/auth analysis
    }
    """
    destination = intent.destination.city or intent.destination.region or intent.destination.area or "Unknown"
    queries = build_reddit_queries(intent)

    if not CLIENT_SECRET:
        logger.warning("[Reddit] ✗ REDDIT_CLIENT_SECRET not set — skipping")
        return {"place_signals": {}, "raw_posts_text": ""}

    logger.info(f"[Reddit] → searching {len(queries)} queries for '{destination}'")
    reddit = asyncpraw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT,
    )
    reddit.read_only = True

    try:
        tasks = [_search_reddit(reddit, q, post_limit) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        await reddit.close()

    all_posts: List[str] = []
    for r in results:
        if isinstance(r, list):
            all_posts.extend(r)

    raw_text = "\n\n---\n\n".join(all_posts)

    if not all_posts:
        logger.warning("No Reddit posts retrieved")
        return {"place_signals": {}, "raw_posts_text": ""}

    signals = await _extract_place_signals(raw_text, destination)
    signals["raw_posts_text"] = raw_text
    return signals
