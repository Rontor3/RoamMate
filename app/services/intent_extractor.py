"""
Intent Extractor - Extracts structured travel intent from user text using LLM.
"""
import json
import logging
import os
import aiohttp
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # Ensure .env is loaded before reading env vars at module level

from app.models import (
    TravelIntent, Destination, IntentConfidence,
    Vibe, CrowdPreference, Duration, Budget
)

logger = logging.getLogger(__name__)

# LLM Configuration — read after load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = """You are a travel intent extractor. Always respond with ONLY valid JSON, no other text.
Extract structured travel preferences from the user's messages in the conversation.

RULES:
- If a field is not mentioned or unclear, use null
- Infer implicit signals (e.g., "rooftop bars" → nightlife interest)
- "feel like going to X" or "want to go to X" → destination city is X
- needs_flight: true if destination requires air travel (international or distant)
- needs_hotel: true if duration > 1 day
- If no travel intent detected (e.g. just "hi"), return the schema with all nulls and confidence 0.0
- ALWAYS return valid JSON. Never explain. Never refuse.
- region: use for broad geographic zones spanning multiple cities/states (e.g. "North East India", "Scottish Highlands", "Patagonia"). When region is set, city should be null.

OUTPUT SCHEMA:
{
  "destination": {"city": string|null, "country": string|null, "area": string|null, "region": string|null},
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
        # Re-read at init time in case load_dotenv() was called after module load
        self.api_key = api_key or os.getenv("GROQ_API") or GROQ_API_KEY
        if not self.api_key:
            logger.warning("GROQ_API key not set")
    
    async def extract(self, messages: list) -> TravelIntent:
        """
        Extract intent from a list of message dicts: [{"role": ..., "content": ...}].
        Falls back gracefully to empty intent if the LLM fails or refuses.
        """
        if not messages:
            return self._empty_intent("Empty input")
        
        logger.info(f"[Groq/intent] → extracting intent from {len(messages)} messages")
        try:
            response = await self._call_llm(messages)
            intent = self._parse_response(response)
            dest = intent.destination.city or intent.destination.region or intent.destination.country or "unknown"
            vibe = [v.value for v in intent.vibe] if intent.vibe else []
            logger.info(f"[Groq/intent] ✓ dest={dest} vibe={vibe} confidence={intent.confidence.overall}")
            return intent
        except Exception as e:
            logger.error(f"[Groq/intent] ✗ {e}")
            return self._empty_intent(str(e))
    
    async def _call_llm(self, messages: list) -> dict:
        """Call LLM API for intent extraction, passing the full conversation as structured messages."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # Map our internal roles to LLM API roles
        def _to_api_role(role: str) -> str:
            if role in ("human", "user"):
                return "user"
            if role in ("ai", "assistant"):
                return "assistant"
            return "user"

        api_messages = [
            {"role": _to_api_role(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in messages if m.get("content")
        ]

        body = {
            "model": MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + api_messages,
            "max_tokens": 500,
            "temperature": 0.1
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                content = result["choices"][0]["message"]["content"]
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
            area=dest_data.get("area"),
            region=dest_data.get("region"),
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
        
        if not intent.destination.city and not intent.destination.country and not intent.destination.region:
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
            prompts.append("Sounds exciting! Where are you thinking of heading?")
        
        if "duration" in intent.confidence.ambiguous_fields:
            prompts.append("Nice! How long are you thinking of staying?")
        
        if "interests" in intent.confidence.ambiguous_fields:
            prompts.append("What kind of things do you enjoy — beaches, food, nightlife, culture?")
        
        return prompts

    async def ask_conversationally(self, messages: list) -> str:
        """
        Generate a warm, natural clarifying question based on the conversation so far.
        Used instead of hardcoded fallbacks so the bot feels human.
        """
        if not self.api_key:
            return "Sounds exciting! Where are you thinking of heading?"

        system = (
            "You are RoamMate, a friendly and enthusiastic travel companion. "
            "The user wants to travel but hasn't specified a destination yet. "
            "Based on the conversation so far, ask ONE short, warm, conversational question to find out where they want to go. "
            "Do NOT use bullet points or lists. Keep it to 1-2 sentences max. "
            "Sound like an excited friend, not a form."
        )
        api_messages = [
            {"role": m.get("role", "user") if isinstance(m, dict) else getattr(m, "type", "user"),
             "content": str(m.get("content", "") if isinstance(m, dict) else getattr(m, "content", ""))}
            for m in messages if (m.get("content") if isinstance(m, dict) else getattr(m, "content", ""))
        ]
        logger.info("[Groq/clarify] → generating conversational question")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": MODEL,
            "messages": [{"role": "system", "content": system}] + api_messages,
            "max_tokens": 80,
            "temperature": 0.8,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(GROQ_URL, headers=headers, json=body) as r:
                    result = await r.json()
                    question = result["choices"][0]["message"]["content"].strip()
                    logger.info(f"[Groq/clarify] ✓ question generated")
                    return question
        except Exception as e:
            logger.error(f"[Groq/clarify] ✗ {e}")
            return "Sounds like a fun trip! Where are you thinking of going?"
