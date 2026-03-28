"""Unit tests for scorer.py — social score combining Reddit + blog."""
import pytest
from app.services.scorer import _social_score, score_all_places


def test_social_score_with_no_signals():
    score, conf, crowd = _social_score("Unknown Place", {}, {})
    assert 0.0 <= score <= 1.0
    assert crowd is None


def test_social_score_with_reddit_match():
    reddit = {"place_signals": {"Cafe Sunrise": {"sentiment_score": 0.9, "crowd_signal": "low", "mention_count": 4}}}
    score, conf, crowd = _social_score("Cafe Sunrise", reddit, {})
    assert score > 0.5
    assert crowd == "low"


def test_score_all_places_attaches_fields():
    places = [{"name": "Taj Mahal"}]
    result = score_all_places(places, {}, {})
    assert "social_score" in result[0]
    assert "reddit_crowd" in result[0]
