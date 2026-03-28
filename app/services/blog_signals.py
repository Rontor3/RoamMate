"""
blog_signals.py — Tavily blog scoring service.
Scores editorial content by: domain_authority * freshness * tavily_score.
Cross-query boost for places mentioned across multiple sources.
"""
import asyncio
import aiohttp
import os
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"

# Domain authority scores (0-1) for known travel publishers
DOMAIN_AUTHORITY = {
    "lonelyplanet.com": 0.95,
    "tripadvisor.com": 0.90,
    "timeout.com": 0.88,
    "cntraveler.com": 0.87,
    "travelandleisure.com": 0.85,
    "fodors.com": 0.82,
    "nomadicmatt.com": 0.75,
    "theguardian.com": 0.80,
    "nytimes.com": 0.85,
}


def _score_domain(url: str) -> float:
    """Return domain authority score for a URL."""
    for domain, score in DOMAIN_AUTHORITY.items():
        if domain in url:
            return score
    return 0.5  # Unknown domain neutral score


def _estimate_freshness(published_date: Optional[str]) -> float:
    """Return a freshness score 0–1; recent = higher."""
    if not published_date:
        return 0.5
    try:
        pub = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_old = (now - pub).days
        if days_old <= 90:
            return 1.0
        elif days_old <= 365:
            return 0.8
        elif days_old <= 730:
            return 0.6
        return 0.4
    except Exception:
        return 0.5


async def _tavily_search(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Call Tavily search API and return raw results."""
    if not TAVILY_API_KEY:
        logger.warning("[Tavily] ✗ TAVILY_API_KEY not set — skipping")
        return []
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": False,
    }
    logger.info(f"[Tavily] → searching: '{query}'")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(TAVILY_URL, json=payload) as r:
                data = await r.json()
                results = data.get("results", [])
                logger.info(f"[Tavily] ✓ '{query}' → {len(results)} results")
                return results
    except Exception as e:
        logger.error(f"[Tavily] ✗ '{query}': {e}")
        return []


def _score_result(result: Dict[str, Any]) -> float:
    """Compute final score for a single Tavily result."""
    tavily_score = result.get("score", 0.5)
    domain_score = _score_domain(result.get("url", ""))
    freshness = _estimate_freshness(result.get("published_date"))
    return round(tavily_score * 0.5 + domain_score * 0.3 + freshness * 0.2, 3)


def cross_query_boost(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Boost final_score for domains mentioned in multiple query results."""
    domain_counts: Dict[str, int] = {}
    for s in sources:
        url = s.get("url", "")
        for domain in DOMAIN_AUTHORITY:
            if domain in url:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

    boosted = []
    for s in sources:
        url = s.get("url", "")
        for domain, count in domain_counts.items():
            if domain in url and count > 1:
                s["final_score"] = min(s.get("final_score", 0) + 0.05 * (count - 1), 1.0)
        boosted.append(s)
    return boosted


async def get_blog_signals(destination: str, vibe: Optional[str] = None) -> Dict[str, Any]:
    """
    Main entry point. Returns:
    {
      "sources": [{"url", "domain", "snippet", "final_score"}],
      "top_answer": str   # combined top snippets for responder
    }
    """
    queries = [
        f"best things to do in {destination} travel guide",
        f"{destination} hidden gems local tips {vibe or ''}".strip(),
    ]

    tasks = [_tavily_search(q) for q in queries]
    results_per_query = await asyncio.gather(*tasks, return_exceptions=True)

    all_sources = []
    for results in results_per_query:
        if isinstance(results, list):
            for r in results:
                scored = {
                    "url": r.get("url", ""),
                    "domain": re.sub(r"https?://(www\.)?", "", r.get("url", "")).split("/")[0],
                    "snippet": r.get("content", "")[:400],
                    "final_score": _score_result(r),
                }
                all_sources.append(scored)

    all_sources = cross_query_boost(all_sources)
    all_sources.sort(key=lambda x: x.get("final_score", 0), reverse=True)

    top_snippets = " ".join(s["snippet"] for s in all_sources[:3])

    return {"sources": all_sources[:8], "top_answer": top_snippets}


async def get_tavily_events(destination: str) -> List[Dict[str, Any]]:
    """Search for current events at the destination."""
    results = await _tavily_search(f"events happening in {destination} this month", max_results=4)
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")[:300]}
        for r in results
    ]
