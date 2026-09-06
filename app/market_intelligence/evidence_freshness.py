from datetime import datetime, timedelta
from typing import Tuple, Optional
from app.market_intelligence.models import FreshnessCategory
from app.market_intelligence.config import FRESHNESS_THRESHOLDS_DAYS

class EvidenceFreshnessCalculator:
    """Evaluates age and freshness score of market evidence."""

    def calculate(
        self,
        signal_type: str,
        publication_date: Optional[datetime],
        retrieved_at: Optional[datetime] = None
    ) -> Tuple[int, float, str]:
        now = datetime.utcnow()
        ref_date = publication_date or retrieved_at or now

        # Prevent future dates from skewing freshness
        if ref_date > now:
            ref_date = now

        age_days = max(0, (now - ref_date).days)
        max_days = FRESHNESS_THRESHOLDS_DAYS.get(signal_type, 180)

        # Freshness score scales gracefully from 1.0 down to 0.2
        if age_days <= 30:
            category = FreshnessCategory.VERY_RECENT.value
            score = 1.0
        elif age_days <= 90:
            category = FreshnessCategory.RECENT.value
            score = 0.85
        elif age_days <= max_days:
            category = FreshnessCategory.AGING.value
            score = 0.60
        else:
            category = FreshnessCategory.STALE.value
            score = max(0.20, 1.0 - (age_days / (max_days * 2)))

        return age_days, round(score, 3), category

    def calculate_freshness(self, publication_date: Optional[datetime], signal_type: str = "SERVICE_DEMAND"):
        age_days, score, category = self.calculate(signal_type, publication_date)
        return score, category

evidence_freshness_calculator = EvidenceFreshnessCalculator()
freshness_calculator = evidence_freshness_calculator
