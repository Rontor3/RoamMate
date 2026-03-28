"""Unit tests for Ranker with INTENT_WEIGHTS per Vibe."""
import pytest
from app.services.ranker import Ranker
from app.models import Place, PlaceAreaMapping, TravelIntent, Vibe


def _make_mapping(name: str, rating: float, tags: list = None) -> PlaceAreaMapping:
    return PlaceAreaMapping(
        place=Place(
            place_id=name,
            name=name,
            place_type="attraction",
            lat=0.0,
            lon=0.0,
            rating=rating,
            review_count=50,
            tags=tags or [],
        )
    )


def test_rank_places_sorts_descending():
    ranker = Ranker()
    mappings = [_make_mapping("Low", 3.5), _make_mapping("High", 4.8)]
    intent = TravelIntent()
    ranked = ranker.rank_places(mappings, intent)
    assert ranked[0].rank_score >= ranked[1].rank_score


def test_rank_explanation_has_top_factor():
    ranker = Ranker()
    mappings = [_make_mapping("Cafe", 4.6, tags=["coffee", "chill"])]
    intent = TravelIntent(vibe=[Vibe.CHILL])
    ranked = ranker.rank_places(mappings, intent)
    assert ranked[0].explanation.top_factor is not None


def test_rank_position_assigned():
    ranker = Ranker()
    mappings = [_make_mapping("A", 4.9), _make_mapping("B", 4.2), _make_mapping("C", 3.8)]
    ranked = ranker.rank_places(mappings, TravelIntent())
    positions = [r.rank_position for r in ranked]
    assert positions == [1, 2, 3]
