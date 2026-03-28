"""
app/services/scorer.py — Social scoring layer.
Combines Reddit and blog signals into a unified (combined_score, confidence) per place.
Used by planning.py and in_destination.py before calling Ranker.

Signal flow per spec:
  reddit_signals.place_signals[name].sentiment_score   (0-1)
  blog_signals.sources[].final_score weighted by snippet mention
  → combined_score = 0.6 * reddit_score + 0.4 * blog_score
  → confidence from mention_count
  → reddit_crowd forwarded to ScoringEngine
"""
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import get_logger

logger = get_logger(__name__)


def _social_score(
    place_name: str,
    reddit_signals: Dict[str, Any],
    blog_signals: Dict[str, Any],
) -> Tuple[float, float, Optional[str]]:
    """
    Compute combined social score for a place.

    Returns:
        (combined_score, confidence, reddit_crowd)
        reddit_crowd: 'low' | 'medium' | 'high' | None
    """
    place_signals = reddit_signals.get("place_signals", {})

    # Try exact match, then partial match
    signal = place_signals.get(place_name)
    if not signal:
        for key in place_signals:
            if key.lower() in place_name.lower() or place_name.lower() in key.lower():
                signal = place_signals[key]
                break

    reddit_score = 0.5
    confidence = 0.3
    reddit_crowd = None
    mention_count = 0

    if signal:
        reddit_score = float(signal.get("sentiment_score", 0.5))
        reddit_crowd = signal.get("crowd_signal")
        mention_count = int(signal.get("mention_count", 1))
        confidence = min(mention_count / 5, 1.0)

    # Blog score: weighted by final_score for sources mentioning the place
    blog_score = 0.3  # fallback
    blog_hits = []
    for source in blog_signals.get("sources", []):
        snippet = source.get("snippet", "").lower()
        if place_name.lower() in snippet:
            blog_hits.append(source.get("final_score", 0.5))

    if blog_hits:
        blog_score = sum(blog_hits) / len(blog_hits)

    combined_score = round(0.6 * reddit_score + 0.4 * blog_score, 3)
    return combined_score, confidence, reddit_crowd


def score_all_places(
    places: List[Dict[str, Any]],
    reddit_signals: Dict[str, Any],
    blog_signals: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Attach social scores to each place dict.
    Returns the same list with added 'social_score', 'social_confidence', 'reddit_crowd' fields.
    """
    for place in places:
        name = place.get("name", "")
        score, conf, crowd = _social_score(name, reddit_signals, blog_signals)
        place["social_score"] = score
        place["social_confidence"] = conf
        place["reddit_crowd"] = crowd
    return places
