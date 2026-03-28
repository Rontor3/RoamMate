"""Unit tests for blog_signals module."""
import pytest


@pytest.mark.asyncio
async def test_score_domain_known():
    from app.services.blog_signals import _score_domain
    assert _score_domain("https://lonelyplanet.com/goa") == 0.95


def test_cross_query_boost_increases_score():
    from app.services.blog_signals import cross_query_boost
    sources = [
        {"url": "https://lonelyplanet.com/a", "final_score": 0.7},
        {"url": "https://lonelyplanet.com/b", "final_score": 0.7},
    ]
    boosted = cross_query_boost(sources)
    assert boosted[0]["final_score"] >= 0.7
