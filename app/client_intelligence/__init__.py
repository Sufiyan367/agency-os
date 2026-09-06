"""Client Intelligence & Service Matching Package.
"""
from app.client_intelligence.models import (
    BusinessSegment,
    PainCategory,
    InferredField,
    BusinessProfile,
    BusinessSizeEstimate,
    DetectedPainPoint,
    OperationalWasteEstimate,
    ServiceMatch,
    ROIEstimate,
    ClientOffer,
    PricingRecommendation,
    DecisionTrace,
)
from app.client_intelligence.catalog import (
    SERVICE_CATALOG,
    ServiceCatalogItem,
    ServiceCatalog,
    service_catalog,
)
from app.client_intelligence.profiler import BusinessProfiler
from app.client_intelligence.size_estimator import BusinessSizeEstimator
from app.client_intelligence.pain_detector import PainPointDetector
from app.client_intelligence.waste_detector import OperationalWasteDetector
from app.client_intelligence.matcher import ServiceMatcher
from app.client_intelligence.roi_estimator import ROIEstimator
from app.client_intelligence.pricing import PricingEngine
from app.client_intelligence.composer import OfferComposer
from app.client_intelligence.selector import ProspectSelector
from app.client_intelligence.traceability import DecisionTraceManager
from app.client_intelligence.engine import ClientIntelligenceEngine, client_intelligence_engine

__all__ = [
    "BusinessSegment",
    "PainCategory",
    "InferredField",
    "BusinessProfile",
    "BusinessSizeEstimate",
    "DetectedPainPoint",
    "OperationalWasteEstimate",
    "ServiceMatch",
    "ROIEstimate",
    "ClientOffer",
    "PricingRecommendation",
    "DecisionTrace",
    "SERVICE_CATALOG",
    "ServiceCatalogItem",
    "ServiceCatalog",
    "service_catalog",
    "BusinessProfiler",
    "BusinessSizeEstimator",
    "PainPointDetector",
    "OperationalWasteDetector",
    "ServiceMatcher",
    "ROIEstimator",
    "PricingEngine",
    "OfferComposer",
    "ProspectSelector",
    "DecisionTraceManager",
    "ClientIntelligenceEngine",
    "client_intelligence_engine",
]
