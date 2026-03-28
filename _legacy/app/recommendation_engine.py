"""
Recommendation Orchestrator - Integrates all components for end-to-end recommendations.
"""
import logging
from typing import Optional
from dataclasses import dataclass

from .models import (
    TravelIntent, Place, RankedPlace, ResolvedArea,
    PlaceAreaMapping, AreaScores, AirportResult
)
from .services.input import IntentExtractor
from .services.extraction import GeoResolver
from .services.scoring import ScoringEngine, Ranker
from .services.mapping.airport_mapper import AirportMapper
from .services.mapping.area_mapper import AreaMapper
from .services.output import Explainer

logger = logging.getLogger(__name__)


@dataclass
class RecommendationResult:
    """Complete recommendation result."""
    intent: TravelIntent
    destination: Optional[ResolvedArea] = None
    airports: Optional[AirportResult] = None
    ranked_places: list[RankedPlace] = None
    explanations: list[str] = None
    area_scores: Optional[AreaScores] = None
    
    def __post_init__(self):
        if self.ranked_places is None:
            self.ranked_places = []
        if self.explanations is None:
            self.explanations = []


class RecommendationOrchestrator:
    """Orchestrates the full recommendation pipeline."""
    
    def __init__(self, airport_csv_path: str = "world-airports.csv"):
        self.intent_extractor = IntentExtractor()
        self.geo_resolver = GeoResolver()
        self.scoring_engine = ScoringEngine()
        self.ranker = Ranker()
        self.area_mapper = AreaMapper()
        self.explainer = Explainer()
        
        # Load airport data
        try:
            self.airport_mapper = AirportMapper(airport_csv_path)
        except Exception as e:
            logger.warning(f"Could not load airport data: {e}")
            self.airport_mapper = None
    
    async def recommend(
        self,
        user_text: str,
        places: Optional[list[Place]] = None,
        reddit_text: Optional[str] = None,
        max_results: int = 5
    ) -> RecommendationResult:
        """
        Generate recommendations from user text.
        
        Args:
            user_text: Raw user query (e.g., "chill cafes in Tokyo")
            places: Optional list of pre-fetched places
            reddit_text: Optional Reddit signals for scoring
            max_results: Maximum recommendations to return
            
        Returns:
            RecommendationResult with ranked places and explanations
        """
        # Step 1: Extract intent
        logger.info("Extracting intent...")
        intent = await self.intent_extractor.extract(user_text)
        
        result = RecommendationResult(intent=intent)
        
        # Step 2: Resolve destination
        if intent.destination.city or intent.destination.area:
            logger.info("Resolving destination...")
            destination = await self.geo_resolver.resolve(
                intent.destination.city or intent.destination.area,
                context_country=intent.destination.country
            )
            result.destination = destination
            
            # Step 3: Find airports if needed
            if destination and destination.geo and intent.needs_flight:
                if self.airport_mapper:
                    logger.info("Finding airports...")
                    result.airports = self.airport_mapper.find_for_destination(
                        destination.geo.lat,
                        destination.geo.lon
                    )
        
        # Step 4: Score area (if Reddit data available)
        if reddit_text:
            logger.info("Computing area scores...")
            result.area_scores = self.scoring_engine.score_area(
                reddit_text=reddit_text
            )
        
        # Step 5: Rank places
        if places:
            logger.info("Ranking places...")
            
            # Map places to areas
            if result.destination:
                self.area_mapper.set_areas([result.destination])
            mappings = self.area_mapper.map_batch(places)
            
            # Rank
            ranked = self.ranker.rank_places(
                mappings,
                intent,
                result.area_scores
            )
            result.ranked_places = ranked[:max_results]
            
            # Step 6: Generate explanations
            logger.info("Generating explanations...")
            result.explanations = await self.explainer.explain_batch(
                result.ranked_places,
                intent,
                result.area_scores
            )
        
        return result
    
    async def quick_recommend(
        self,
        user_text: str,
        places: list[Place]
    ) -> list[dict]:
        """
        Quick recommendation without Reddit signals.
        Returns simplified output.
        """
        result = await self.recommend(user_text, places)
        
        output = []
        for i, rp in enumerate(result.ranked_places):
            explanation = result.explanations[i] if i < len(result.explanations) else ""
            output.append({
                "name": rp.place.name,
                "rank": rp.rank_position,
                "score": rp.rank_score,
                "rating": rp.place.rating,
                "explanation": explanation,
                "confidence": rp.confidence
            })
        
        return output
