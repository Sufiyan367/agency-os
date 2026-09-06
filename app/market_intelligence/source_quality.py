import re
from typing import Tuple
from app.market_intelligence.models import EvidenceTier

class SourceQualityClassifier:
    """Classifies public evidence sources into quality tiers and computes credibility scores."""

    TIER_1_DOMAINS = {
        "worldbank.org", "imf.org", "oecd.org", "un.org", "statista.com",
        "bls.gov", "census.gov", "gov.uk", "ons.gov.uk", "abs.gov.au",
        "statcan.gc.ca", "ec.europa.eu", "eurostat.ec.europa.eu",
        "stats.gov.sa", "fcsc.gov.ae", "singstat.gov.sg", "stat.go.jp",
        "destatis.de", "insee.fr", "cbs.nl", "kostat.go.kr", "mospi.gov.in"
    }

    TIER_2_DOMAINS = {
        "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "forbes.com",
        "mckinsey.com", "gartner.com", "bain.com", "deloitte.com", "pwc.com",
        "kpmg.com", "techcrunch.com", "venturebeat.com", "mit.edu", "hbr.org",
        "economist.com", "accenture.com", "idc.com", "forrester.com"
    }

    def classify(self, domain: str) -> Tuple[int, float]:
        d = domain.lower().strip()
        # Remove www.
        if d.startswith("www."):
            d = d[4:]

        # Tier 1 checks: government, international institutions, official statistical bureaus
        if d.endswith(".gov") or ".gov." in d or any(d == t1 or d.endswith("." + t1) for t1 in self.TIER_1_DOMAINS):
            return EvidenceTier.TIER_1_OFFICIAL.value, 0.95

        # Tier 2 checks: established research firms, major financial/business press
        if any(d == t2 or d.endswith("." + t2) for t2 in self.TIER_2_DOMAINS):
            return EvidenceTier.TIER_2_RESEARCH.value, 0.85

        # Tier 3: General directories, public corporate websites, trade portals, industry blogs
        return EvidenceTier.TIER_3_PUBLIC_WEB.value, 0.60

source_quality_classifier = SourceQualityClassifier()
