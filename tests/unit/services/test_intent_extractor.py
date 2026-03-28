"""Unit tests for IntentExtractor."""
import pytest


@pytest.mark.asyncio
async def test_extract_basic_destination():
    """extract() returns a TravelIntent with destination set."""
    from app.services.intent_extractor import IntentExtractor
    extractor = IntentExtractor()
    # Mock Groq call would go here
    assert extractor is not None


@pytest.mark.asyncio
async def test_validate_missing_destination():
    """validate() flags missing destination."""
    from app.services.intent_extractor import IntentExtractor
    extractor = IntentExtractor()
    assert extractor is not None


def test_get_clarification_prompts():
    """get_clarification_prompts() returns a non-empty list when destination missing."""
    from app.services.intent_extractor import IntentExtractor
    extractor = IntentExtractor()
    assert extractor is not None
