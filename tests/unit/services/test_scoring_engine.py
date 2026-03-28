"""Unit tests for ScoringEngine and Ranker."""
import pytest
from app.services.scoring_engine import ScoringEngine, CrowdScorer, AuthenticityScorer
from app.services.ranker import Ranker


def test_crowd_scorer_high_crowd_keywords():
    scorer = CrowdScorer()
    result = scorer.compute(reddit_text="very crowded and packed with tourists")
    assert result.value > 0.5


def test_authenticity_scorer_local_keywords():
    scorer = AuthenticityScorer()
    result = scorer.compute(reddit_text="locals love this hidden gem, very authentic")
    assert result.value > 0.5


def test_scoring_engine_returns_area_scores():
    engine = ScoringEngine()
    result = engine.score_area(reddit_text="quiet and peaceful, locals only")
    assert result.crowd_score is not None
    assert result.authenticity_score is not None


def test_ranker_returns_sorted_results():
    from app.models import Place, PlaceAreaMapping, TravelIntent
    ranker = Ranker()
    places = [
        PlaceAreaMapping(place=Place(place_id="1", name="A", place_type="cafe", lat=0, lon=0, rating=4.5, review_count=80)),
        PlaceAreaMapping(place=Place(place_id="2", name="B", place_type="cafe", lat=0, lon=0, rating=3.8, review_count=20)),
    ]
    intent = TravelIntent()
    ranked = ranker.rank_places(places, intent)
    assert ranked[0].rank_score >= ranked[1].rank_score
