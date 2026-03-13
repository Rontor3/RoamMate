"""
Intent Extractor - Extracts structured travel intent from user text using LLM.
"""
import json
import logging
import os
import aiohttp
from typing import Optional

from app.models import (
    TravelIntent, Destination, IntentConfidence,
    Vibe, CrowdPreference, Duration, Budget
)

logger = logging.getLogger(__name__)

# LLM Configuration
GROQ_API_KEY = os.getenv("GROQ_API")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = """You are a travel intent extractor. Extract structured travel preferences from user text.
Return ONLY valid JSON matching the schema. Do not add commentary.

RULES:
- If a field is not mentioned or unclear, use null
- Infer implicit signals (e.g., "rooftop bars" → nightlife interest, night time)
- needs_flight: true if destination requires air travel (international or distant)
- needs_hotel: true if duration > 1 day
- Set confidence.overall based on how much is explicitly stated vs inferred (0.0-1.0)

OUTPUT SCHEMA:
{
  "destination": {"city": string|null, "country": string|null, "area": string|null},
  "vibe": ["chill"|"party"|"adventure"|"cultural"|"romantic"|"family"],
  "crowd_preference": "low"|"medium"|"high"|null,
  "duration": "day"|"weekend"|"week"|"extended"|null,
  "needs_flight": boolean|null,
  "needs_hotel": boolean|null,
  "interests": ["cafes"|"nature"|"beach"|"nightlife"|"food"|"shopping"|"museums"|"hiking"],
  "budget": "budget"|"mid"|"luxury"|null,
  "confidence": {"overall": 0.0-1.0, "ambiguous_fields": ["field_name"]}
}"""


class IntentExtractor:
    """Extracts travel intent from user text using LLM."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GROQ_API_KEY
        if not self.api_key:
            logger.warning("GROQ_API key not set")
    
    async def extract(self, raw_text: str) -> TravelIntent:
        """Extract intent from raw user text using LLM."""
        if not raw_text or not raw_text.strip():
            return self._empty_intent("Empty input")
        
        try:
            response = await self._call_llm(raw_text)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"Intent extraction failed: {e}")
            return self._empty_intent(str(e))
    
    async def _call_llm(self, user_text: str) -> dict:
        """Call LLM API for intent extraction."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            "max_tokens": 500,
            "temperature": 0.1  # Low temp for consistent extraction
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                content = result["choices"][0]["message"]["content"]
                # Extract JSON from response
                return self._extract_json(content)
    
    def _extract_json(self, content: str) -> dict:
        """Extract JSON from LLM response."""
        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # Try to find JSON in response
        import re
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        raise ValueError(f"Could not parse JSON from response: {content[:200]}")
    
    def _parse_response(self, data: dict) -> TravelIntent:
        """Parse LLM response into TravelIntent model."""
        # Parse destination
        dest_data = data.get("destination", {}) or {}
        destination = Destination(
            city=dest_data.get("city"),
            country=dest_data.get("country"),
            area=dest_data.get("area")
        )
        
        # Parse vibes
        vibes = []
        for v in data.get("vibe", []) or []:
            try:
                vibes.append(Vibe(v.lower()))
            except ValueError:
                pass
        
        # Parse crowd preference
        crowd_pref = None
        if cp := data.get("crowd_preference"):
            try:
                crowd_pref = CrowdPreference(cp.lower())
            except ValueError:
                pass
        
        # Parse duration
        duration = None
        if d := data.get("duration"):
            try:
                duration = Duration(d.lower())
            except ValueError:
                pass
        
        # Parse budget
        budget = None
        if b := data.get("budget"):
            try:
                budget = Budget(b.lower())
            except ValueError:
                pass
        
        # Parse confidence
        conf_data = data.get("confidence", {}) or {}
        confidence = IntentConfidence(
            overall=float(conf_data.get("overall", 0.5)),
            ambiguous_fields=conf_data.get("ambiguous_fields", [])
        )
        
        return TravelIntent(
            destination=destination,
            vibe=vibes,
            crowd_preference=crowd_pref,
            duration=duration,
            needs_flight=data.get("needs_flight"),
            needs_hotel=data.get("needs_hotel"),
            interests=data.get("interests", []) or [],
            budget=budget,
            confidence=confidence
        )
    
    def _empty_intent(self, error: str) -> TravelIntent:
        """Return empty intent with error flag."""
        return TravelIntent(
            confidence=IntentConfidence(
                overall=0.0,
                ambiguous_fields=["all"]
            )
        )
    
    def validate(self, intent: TravelIntent) -> dict:
        """Check for missing required fields and ambiguity."""
        issues = []
        
        if not intent.destination.city and not intent.destination.country:
            issues.append("destination")
        
        if intent.confidence.overall < 0.5:
            issues.append("low_confidence")
        
        return {
            "valid": len(issues) == 0 and intent.destination.city is not None,
            "issues": issues,
            "needs_clarification": intent.confidence.ambiguous_fields
        }
    
    def get_clarification_prompts(self, intent: TravelIntent) -> list[str]:
        """Generate follow-up questions for ambiguous fields."""
        prompts = []
        
        if not intent.destination.city and not intent.destination.country:
            prompts.append("Where would you like to go?")
        
        if "duration" in intent.confidence.ambiguous_fields:
            prompts.append("How long is your trip?")
        
        if "interests" in intent.confidence.ambiguous_fields:
            prompts.append("What activities are you interested in?")
        
        return prompts
