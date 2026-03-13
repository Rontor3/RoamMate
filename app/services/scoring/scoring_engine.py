"""
Scoring Engine - Deterministic scoring for crowd and authenticity.
"""
import logging
from typing import Optional

from app.models import ScoreResult, AreaScores

logger = logging.getLogger(__name__)


class CrowdScorer:
    """Computes crowd score from Reddit and Google signals."""
    
    # Signal weights
    WEIGHTS = {
        'crowd_mentions': 0.4,
        'popularity_score': 0.3,
        'time_popularity': 0.2,
        'review_count_ratio': 0.1
    }
    
    # Keyword mappings
    HIGH_CROWD_KEYWORDS = ['crowded', 'packed', 'busy', 'tourist trap', 'wait in line', 'queue', 'mobbed']
    MEDIUM_CROWD_KEYWORDS = ['popular', 'lively', 'bustling', 'vibrant']
    LOW_CROWD_KEYWORDS = ['quiet', 'empty', 'hidden gem', 'off the beaten path', 'peaceful', 'serene']
    
    def compute(
        self,
        reddit_text: Optional[str] = None,
        google_rating_count: Optional[int] = None,
        city_max_ratings: int = 10000,
        popular_times_peak: Optional[int] = None,  # 0-100
        category_avg_reviews: int = 100
    ) -> ScoreResult:
        """Compute crowd score from available signals."""
        signals_used = []
        weighted_sum = 0.0
        weight_sum = 0.0
        
        # 1. Reddit crowd mentions
        if reddit_text:
            crowd_signal, conf = self._analyze_reddit_crowd(reddit_text)
            weighted_sum += crowd_signal * self.WEIGHTS['crowd_mentions'] * conf
            weight_sum += self.WEIGHTS['crowd_mentions'] * conf
            signals_used.append('crowd_mentions')
        
        # 2. Google popularity score
        if google_rating_count is not None:
            popularity = min(google_rating_count / city_max_ratings, 1.0)
            weighted_sum += popularity * self.WEIGHTS['popularity_score']
            weight_sum += self.WEIGHTS['popularity_score']
            signals_used.append('popularity_score')
        
        # 3. Popular times
        if popular_times_peak is not None:
            time_pop = popular_times_peak / 100.0
            weighted_sum += time_pop * self.WEIGHTS['time_popularity']
            weight_sum += self.WEIGHTS['time_popularity']
            signals_used.append('time_popularity')
        
        # 4. Review count ratio
        if google_rating_count is not None:
            ratio = min(google_rating_count / category_avg_reviews, 1.0)
            weighted_sum += ratio * self.WEIGHTS['review_count_ratio']
            weight_sum += self.WEIGHTS['review_count_ratio']
            signals_used.append('review_count_ratio')
        
        # Calculate final score
        if weight_sum > 0:
            value = weighted_sum / weight_sum
            confidence = len(signals_used) / len(self.WEIGHTS)
        else:
            value = 0.5  # Neutral default
            confidence = 0.0
        
        # Apply fallback penalty if no Reddit data
        fallback_used = reddit_text is None
        if fallback_used:
            confidence *= 0.7
        
        return ScoreResult(
            value=round(value, 3),
            confidence=round(confidence, 3),
            signals_used=signals_used,
            fallback_used=fallback_used
        )
    
    def _analyze_reddit_crowd(self, text: str) -> tuple[float, float]:
        """Analyze Reddit text for crowd signals. Returns (score, confidence)."""
        text_lower = text.lower()
        
        high_count = sum(1 for kw in self.HIGH_CROWD_KEYWORDS if kw in text_lower)
        medium_count = sum(1 for kw in self.MEDIUM_CROWD_KEYWORDS if kw in text_lower)
        low_count = sum(1 for kw in self.LOW_CROWD_KEYWORDS if kw in text_lower)
        
        total = high_count + medium_count + low_count
        if total == 0:
            return 0.5, 0.3  # Neutral with low confidence
        
        # Weighted average
        score = (high_count * 0.8 + medium_count * 0.5 + low_count * 0.2) / total
        confidence = min(total / 5, 1.0)  # More mentions = higher confidence
        
        return score, confidence


class AuthenticityScorer:
    """Computes local authenticity score from Reddit and Google signals."""
    
    WEIGHTS = {
        'local_mentions': 0.35,
        'tourist_trap_flags': 0.25,
        'review_language_diversity': 0.20,
        'price_authenticity': 0.10,
        'chain_ratio': 0.10
    }
    
    # Keyword mappings
    HIGH_AUTH_KEYWORDS = ['locals love', 'authentic', 'real deal', 'hidden gem', 'off tourist path', 'genuine', 'traditional']
    LOW_AUTH_KEYWORDS = ['tourist trap', 'overpriced', 'avoid', 'not worth', 'scam', 'rip off', 'touristy']
    
    def compute(
        self,
        reddit_text: Optional[str] = None,
        local_language_review_pct: Optional[float] = None,  # 0-1
        price_level: Optional[int] = None,  # 1-4
        category_avg_price: int = 2,
        is_chain: bool = False
    ) -> ScoreResult:
        """Compute authenticity score from available signals."""
        signals_used = []
        weighted_sum = 0.0
        weight_sum = 0.0
        
        # 1 & 2. Reddit local/tourist mentions
        if reddit_text:
            auth_signal, conf = self._analyze_reddit_authenticity(reddit_text)
            # Split between local_mentions and tourist_trap_flags
            weighted_sum += auth_signal * (self.WEIGHTS['local_mentions'] + self.WEIGHTS['tourist_trap_flags']) * conf
            weight_sum += (self.WEIGHTS['local_mentions'] + self.WEIGHTS['tourist_trap_flags']) * conf
            signals_used.extend(['local_mentions', 'tourist_trap_flags'])
        
        # 3. Review language diversity
        if local_language_review_pct is not None:
            weighted_sum += local_language_review_pct * self.WEIGHTS['review_language_diversity']
            weight_sum += self.WEIGHTS['review_language_diversity']
            signals_used.append('review_language_diversity')
        
        # 4. Price authenticity (not overpriced)
        if price_level is not None:
            # Lower price relative to category = more authentic
            price_auth = max(0, 1 - abs(price_level - category_avg_price) * 0.25)
            weighted_sum += price_auth * self.WEIGHTS['price_authenticity']
            weight_sum += self.WEIGHTS['price_authenticity']
            signals_used.append('price_authenticity')
        
        # 5. Chain vs independent
        chain_signal = 0.0 if is_chain else 1.0
        weighted_sum += chain_signal * self.WEIGHTS['chain_ratio']
        weight_sum += self.WEIGHTS['chain_ratio']
        signals_used.append('chain_ratio')
        
        # Calculate final score
        if weight_sum > 0:
            value = weighted_sum / weight_sum
            confidence = len(signals_used) / len(self.WEIGHTS)
        else:
            value = 0.5
            confidence = 0.0
        
        fallback_used = reddit_text is None
        if fallback_used:
            confidence *= 0.7
        
        return ScoreResult(
            value=round(value, 3),
            confidence=round(confidence, 3),
            signals_used=signals_used,
            fallback_used=fallback_used
        )
    
    def _analyze_reddit_authenticity(self, text: str) -> tuple[float, float]:
        """Analyze Reddit text for authenticity signals."""
        text_lower = text.lower()
        
        high_count = sum(1 for kw in self.HIGH_AUTH_KEYWORDS if kw in text_lower)
        low_count = sum(1 for kw in self.LOW_AUTH_KEYWORDS if kw in text_lower)
        
        total = high_count + low_count
        if total == 0:
            return 0.5, 0.3
        
        score = high_count / total  # Proportion of positive signals
        confidence = min(total / 5, 1.0)
        
        return score, confidence


class ScoringEngine:
    """Combined scoring engine for areas."""
    
    def __init__(self):
        self.crowd_scorer = CrowdScorer()
        self.authenticity_scorer = AuthenticityScorer()
    
    def score_area(
        self,
        reddit_text: Optional[str] = None,
        google_rating_count: Optional[int] = None,
        city_max_ratings: int = 10000,
        popular_times_peak: Optional[int] = None,
        local_language_pct: Optional[float] = None,
        price_level: Optional[int] = None,
        is_chain: bool = False
    ) -> AreaScores:
        """Compute all area scores."""
        crowd = self.crowd_scorer.compute(
            reddit_text=reddit_text,
            google_rating_count=google_rating_count,
            city_max_ratings=city_max_ratings,
            popular_times_peak=popular_times_peak
        )
        
        authenticity = self.authenticity_scorer.compute(
            reddit_text=reddit_text,
            local_language_review_pct=local_language_pct,
            price_level=price_level,
            is_chain=is_chain
        )
        
        return AreaScores(
            crowd_score=crowd,
            authenticity_score=authenticity
        )
