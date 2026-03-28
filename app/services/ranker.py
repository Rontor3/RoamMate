"""
Ranker - Deterministic ranking algorithm for places based on scores and user intent.
"""
import logging
from typing import Optional

from app.models import (
    Place, PlaceAreaMapping, TravelIntent, RankedPlace, RankExplanation,
    ScoreResult, AreaScores, Vibe, CrowdPreference
)

logger = logging.getLogger(__name__)


# Default weights
DEFAULT_WEIGHTS = {
    'quality': 0.35,
    'crowd_fit': 0.20,
    'authenticity': 0.20,
    'intent_match': 0.25
}

# Intent-adjusted weights
INTENT_WEIGHTS = {
    Vibe.CHILL: {'quality': 0.30, 'crowd_fit': 0.30, 'authenticity': 0.20, 'intent_match': 0.20},
    Vibe.ADVENTURE: {'quality': 0.25, 'crowd_fit': 0.15, 'authenticity': 0.25, 'intent_match': 0.35},
    Vibe.CULTURAL: {'quality': 0.25, 'crowd_fit': 0.15, 'authenticity': 0.35, 'intent_match': 0.25},
    Vibe.PARTY: {'quality': 0.30, 'crowd_fit': 0.10, 'authenticity': 0.20, 'intent_match': 0.40},
}

# Crowd preference mappings
CROWD_PREF_VALUES = {
    CrowdPreference.LOW: 0.2,
    CrowdPreference.MEDIUM: 0.5,
    CrowdPreference.HIGH: 0.8,
    None: 0.5
}


class Ranker:
    """Ranks places using deterministic weighted formula."""
    
    def rank_places(
        self,
        places: list[PlaceAreaMapping],
        intent: TravelIntent,
        area_scores: Optional[AreaScores] = None
    ) -> list[RankedPlace]:
        """Rank all places and return sorted list."""
        weights = self._get_weights(intent)
        ranked = []
        
        for mapping in places:
            place = mapping.place
            
            # Calculate component scores
            quality = self._compute_quality(place)
            crowd_fit = self._compute_crowd_fit(
                area_scores.crowd_score if area_scores else None,
                intent
            )
            authenticity = self._compute_authenticity_fit(
                area_scores.authenticity_score if area_scores else None,
                intent
            )
            intent_match = self._compute_intent_match(place, intent)
            
            # Calculate contributions
            quality_contrib = quality * weights['quality']
            crowd_contrib = crowd_fit * weights['crowd_fit']
            auth_contrib = authenticity * weights['authenticity']
            intent_contrib = intent_match * weights['intent_match']
            
            # Final rank score
            rank_score = quality_contrib + crowd_contrib + auth_contrib + intent_contrib
            
            # Determine top and weakest factors
            contributions = {
                'quality': quality_contrib,
                'crowd_fit': crowd_contrib,
                'authenticity': auth_contrib,
                'intent_match': intent_contrib
            }
            top_factor = max(contributions, key=contributions.get)
            weakest_factor = min(contributions, key=contributions.get)
            
            # Build explanation
            explanation = RankExplanation(
                quality={'value': round(quality, 3), 'weight': weights['quality'], 'contribution': round(quality_contrib, 3)},
                crowd_fit={'value': round(crowd_fit, 3), 'weight': weights['crowd_fit'], 'contribution': round(crowd_contrib, 3)},
                authenticity={'value': round(authenticity, 3), 'weight': weights['authenticity'], 'contribution': round(auth_contrib, 3)},
                intent_match={'value': round(intent_match, 3), 'weight': weights['intent_match'], 'contribution': round(intent_contrib, 3)},
                top_factor=top_factor,
                weakest_factor=weakest_factor
            )
            
            # Calculate confidence
            confidence = self._compute_confidence(
                place, area_scores, intent_match
            )
            
            ranked.append(RankedPlace(
                place=place,
                rank_score=round(rank_score, 3),
                rank_position=0,  # Will be set after sorting
                area=mapping.primary_area,
                explanation=explanation,
                confidence=round(confidence, 3)
            ))
        
        # Sort by rank score descending
        ranked.sort(key=lambda x: x.rank_score, reverse=True)
        
        # Assign positions
        for i, rp in enumerate(ranked):
            rp.rank_position = i + 1
        
        return ranked
    
    def _get_weights(self, intent: TravelIntent) -> dict[str, float]:
        """Get weights adjusted by user intent."""
        if intent.vibe:
            primary_vibe = intent.vibe[0]
            if primary_vibe in INTENT_WEIGHTS:
                return INTENT_WEIGHTS[primary_vibe]
        return DEFAULT_WEIGHTS
    
    def _compute_quality(self, place: Place) -> float:
        """Compute quality score from rating and review count."""
        if place.rating is None:
            return 0.5  # Neutral
        
        # Normalize rating (1-5 → 0-1)
        normalized_rating = (place.rating - 1) / 4
        
        # Review confidence (caps at 100 reviews)
        review_confidence = min(place.review_count / 100, 1.0)
        
        # Weighted combination
        return normalized_rating * 0.6 + review_confidence * 0.4
    
    def _compute_crowd_fit(
        self,
        crowd_score: Optional[ScoreResult],
        intent: TravelIntent
    ) -> float:
        """Compute how well crowd level matches user preference."""
        user_pref = CROWD_PREF_VALUES.get(intent.crowd_preference, 0.5)
        
        if crowd_score is None:
            return 0.5  # Neutral if no data
        
        # 1 - absolute difference (closer = better fit)
        return 1.0 - abs(crowd_score.value - user_pref)
    
    def _compute_authenticity_fit(
        self,
        auth_score: Optional[ScoreResult],
        intent: TravelIntent
    ) -> float:
        """Compute authenticity fit based on intent."""
        if auth_score is None:
            return 0.5
        
        # Cultural vibe boosts authenticity importance
        weight = 1.0
        if Vibe.CULTURAL in intent.vibe:
            weight = 1.2
        elif Vibe.PARTY in intent.vibe:
            weight = 0.8
        
        return min(auth_score.value * weight, 1.0)
    
    def _compute_intent_match(
        self,
        place: Place,
        intent: TravelIntent
    ) -> float:
        """Compute match between place tags and user interests."""
        if not intent.interests:
            return 0.5  # Neutral if no interests specified
        
        if not place.tags:
            return 0.3  # Low match if place has no tags
        
        # Count matching interests
        place_tags_lower = [t.lower() for t in place.tags]
        matched = sum(1 for interest in intent.interests 
                     if any(interest.lower() in tag for tag in place_tags_lower))
        
        return matched / len(intent.interests)
    
    def _compute_confidence(
        self,
        place: Place,
        area_scores: Optional[AreaScores],
        intent_match: float
    ) -> float:
        """Compute overall confidence in the ranking."""
        factors = []
        
        # Place data quality
        if place.rating:
            factors.append(min(place.review_count / 100, 1.0))
        else:
            factors.append(0.3)
        
        # Area score confidence
        if area_scores:
            if area_scores.crowd_score:
                factors.append(area_scores.crowd_score.confidence)
            if area_scores.authenticity_score:
                factors.append(area_scores.authenticity_score.confidence)
        
        # Intent match clarity
        factors.append(0.5 if intent_match == 0.5 else 0.8)
        
        return sum(factors) / len(factors) if factors else 0.5
