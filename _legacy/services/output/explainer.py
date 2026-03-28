"""
Explainer - Generates natural language explanations for recommendations using LLM.
"""
import logging
import os
import aiohttp
from typing import Optional

from app.models import RankedPlace, TravelIntent, AreaScores

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SYSTEM_PROMPT = """You are a travel recommendation explainer. Generate a brief, natural explanation for why 
a cafe/place was recommended. Use ONLY the provided signals - do not invent facts.

RULES:
1. State the main reason(s) the place ranks well
2. Mention area characteristics if relevant (crowd, authenticity)
3. If confidence < 0.6, use hedging language ("likely", "appears to be", "based on limited data")
4. If confidence < 0.4, explicitly state uncertainty
5. Never mention numerical scores to the user
6. Keep response to 2-3 sentences max
7. Do NOT invent details about the place (menu items, decor, etc.)

CONFIDENCE LANGUAGE GUIDE:
- confidence >= 0.8: "This is", "You'll find", "Known for"
- confidence 0.6-0.8: "This seems to be", "Appears to offer"
- confidence 0.4-0.6: "Based on reviews", "Likely"
- confidence < 0.4: "We have limited data, but", "This might be"
"""


class Explainer:
    """Generates natural language explanations for recommendations."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GROQ_API_KEY
    
    async def explain(
        self,
        ranked_place: RankedPlace,
        intent: TravelIntent,
        area_scores: Optional[AreaScores] = None
    ) -> str:
        """Generate natural language explanation for a recommendation."""
        # Build context for LLM
        context = self._build_context(ranked_place, intent, area_scores)
        
        try:
            return await self._call_llm(context)
        except Exception as e:
            logger.error(f"Explanation generation failed: {e}")
            return self._fallback_explanation(ranked_place, intent)
    
    async def explain_batch(
        self,
        ranked_places: list[RankedPlace],
        intent: TravelIntent,
        area_scores: Optional[AreaScores] = None
    ) -> list[str]:
        """Generate explanations for multiple recommendations."""
        explanations = []
        for rp in ranked_places:
            explanation = await self.explain(rp, intent, area_scores)
            explanations.append(explanation)
        return explanations
    
    def _build_context(
        self,
        ranked_place: RankedPlace,
        intent: TravelIntent,
        area_scores: Optional[AreaScores]
    ) -> str:
        """Build context string for LLM."""
        place = ranked_place.place
        exp = ranked_place.explanation
        
        context_parts = [
            f"PLACE: {place.name}",
            f"TYPE: {place.place_type}",
            f"RATING: {place.rating}/5 ({place.review_count} reviews)" if place.rating else "RATING: Unknown",
            f"TAGS: {', '.join(place.tags)}" if place.tags else "TAGS: None",
            f"CONFIDENCE: {ranked_place.confidence}",
            f"TOP_FACTOR: {exp.top_factor}" if exp else "",
        ]
        
        # Add area info
        if ranked_place.area:
            context_parts.append(f"AREA: {ranked_place.area.canonical_name}")
        
        # Add area scores
        if area_scores:
            if area_scores.crowd_score:
                crowd_level = "quiet" if area_scores.crowd_score.value < 0.4 else "busy" if area_scores.crowd_score.value > 0.6 else "moderate"
                context_parts.append(f"AREA_CROWD: {crowd_level}")
            if area_scores.authenticity_score:
                auth_level = "authentic local spot" if area_scores.authenticity_score.value > 0.6 else "touristy" if area_scores.authenticity_score.value < 0.4 else "mixed"
                context_parts.append(f"AREA_VIBE: {auth_level}")
        
        # Add user intent
        intent_parts = []
        if intent.vibe:
            intent_parts.append(f"vibe: {[v.value for v in intent.vibe]}")
        if intent.crowd_preference:
            intent_parts.append(f"crowd: {intent.crowd_preference.value}")
        if intent.interests:
            intent_parts.append(f"interests: {intent.interests}")
        
        context_parts.append(f"USER_WANTS: {', '.join(intent_parts)}")
        
        return "\n".join(context_parts)
    
    async def _call_llm(self, context: str) -> str:
        """Call LLM to generate explanation."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Generate a 2-3 sentence explanation for this recommendation:\n\n{context}"}
            ],
            "max_tokens": 150,
            "temperature": 0.7
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GROQ_URL, headers=headers, json=body) as r:
                result = await r.json()
                return result["choices"][0]["message"]["content"].strip()
    
    def _fallback_explanation(
        self,
        ranked_place: RankedPlace,
        intent: TravelIntent
    ) -> str:
        """Generate simple fallback explanation without LLM."""
        place = ranked_place.place
        exp = ranked_place.explanation
        
        # Confidence-based prefix
        if ranked_place.confidence >= 0.8:
            prefix = f"{place.name} is"
        elif ranked_place.confidence >= 0.6:
            prefix = f"{place.name} appears to be"
        else:
            prefix = f"Based on limited data, {place.name} might be"
        
        # Build description based on top factor
        if exp and exp.top_factor == 'quality':
            desc = f"well-rated with {place.review_count} reviews"
        elif exp and exp.top_factor == 'crowd_fit':
            desc = "a good match for your crowd preference"
        elif exp and exp.top_factor == 'authenticity':
            desc = "known for its authentic local feel"
        elif exp and exp.top_factor == 'intent_match':
            desc = "a good match for your interests"
        else:
            desc = "worth checking out"
        
        # Add area context if available
        area_text = ""
        if ranked_place.area:
            area_text = f" in {ranked_place.area.canonical_name}"
        
        return f"{prefix} {desc}{area_text}."
