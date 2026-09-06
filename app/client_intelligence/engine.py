"""Unified Client Intelligence Engine.

Coordinates business profiling, size estimation, pain point diagnosis,
operational waste evaluation, service matching, ROI estimation, commercial pricing,
offer composition, prospect ranking, and decision traceability.
Supports both synchronous sessions and asynchronous SQLAlchemy sessions.
"""
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.client_intelligence.models import (
    BusinessProfile,
    BusinessSizeEstimate,
    ClientOffer,
    DecisionTrace,
    DetectedPainPoint,
    OperationalWasteEstimate,
    PricingRecommendation,
    ROIEstimate,
    ServiceMatch,
)
from app.client_intelligence.catalog import service_catalog, SERVICE_CATALOG
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


class ClientIntelligenceEngine:
    """End-to-end engine for evidence-grounded client profiling and service matching."""

    def __init__(self):
        self.profiler = BusinessProfiler()
        self.size_estimator = BusinessSizeEstimator()
        self.pain_detector = PainPointDetector()
        self.waste_detector = OperationalWasteDetector()
        self.matcher = ServiceMatcher()
        self.roi_estimator = ROIEstimator()
        self.pricing_engine = PricingEngine()
        self.composer = OfferComposer()
        self.selector = ProspectSelector()
        self.trace_manager = DecisionTraceManager()

    def _compute_intelligence(
        self,
        business: Any,
        audit: Optional[Any] = None,
        raw_signals: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Any], DecisionTrace]:
        """Performs purely deterministic feature extraction, diagnosis, matching, and calculations."""
        biz_id = getattr(business, "id", 0)
        domain = getattr(business, "domain", "unknown-domain.com")

        # 1. Profile business
        profile = self.profiler.profile_business(business, audit=audit, raw_signals=raw_signals)

        # 2. Estimate business scale
        size_estimate = self.size_estimator.estimate_size(profile, business=business, raw_signals=raw_signals)

        # 3. Detect pain points
        pain_points = self.pain_detector.detect_pain_points(profile, size_estimate, audit=audit)

        # 4. Estimate operational waste
        waste_estimate = self.waste_detector.estimate_waste(profile, size_estimate, pain_points)

        # 5. Match against service catalog
        matches = self.matcher.match_services(profile, size_estimate, pain_points, waste_estimate)
        
        # Fallback to general lead qualification if no matches
        if not matches:
            top_service = SERVICE_CATALOG["SERVICE_001"]
            top_match = ServiceMatch(
                service_id="SERVICE_001",
                service_name=top_service.name,
                fit_score=0.5,
                reasons=["General inbound qualification baseline for verified web domain."],
                evidence=["Website verified in database."],
                implementation_complexity=top_service.implementation_complexity,
                estimated_effort_days=top_service.estimated_implementation_effort_days,
            )
            matches = [top_match]
        else:
            top_match = matches[0]

        # 6. Compute bounded ROI
        roi = self.roi_estimator.estimate_roi(profile, size_estimate, waste_estimate, top_match)

        # 7. Pricing Recommendation (Enforcing $500 floor, $1,000+ target)
        pricing = self.pricing_engine.recommend_pricing(profile, size_estimate, top_match, roi)

        # 8. Compose 8-part modular offer
        offer = self.composer.compose_offer(profile, size_estimate, top_match, pricing, pain_points, roi)

        # 9. Prospect prioritization & Win Probability
        selection_data = self.selector.evaluate_prospect(profile, size_estimate, top_match, pricing, pain_points, roi)

        # 10. Audit decision trace
        raw_inputs = {
            "business_id": biz_id,
            "name": getattr(business, "name", ""),
            "domain": domain,
            "niche": getattr(business, "niche", ""),
            "country": getattr(business, "country", ""),
            "city": getattr(business, "city", ""),
            "health_score": getattr(audit, "overall_health_score", 0.0) if audit else 0.0,
        }
        trace = self.trace_manager.build_trace(
            business_id=biz_id,
            domain=domain,
            profile=profile,
            size_estimate=size_estimate,
            pain_points=pain_points,
            waste_estimate=waste_estimate,
            service_matches=matches,
            roi_estimate=roi,
            pricing=pricing,
            offer=offer,
            selection_data=selection_data,
            raw_inputs=raw_inputs,
        )

        result_dict = {
            "business_id": biz_id,
            "domain": domain,
            "business_name": getattr(business, "name", domain),
            "profile": profile.model_dump(mode="json"),
            "size_estimate": size_estimate.model_dump(mode="json"),
            "pain_points": [p.model_dump(mode="json") for p in pain_points],
            "waste_estimate": waste_estimate.model_dump(mode="json"),
            "service_matches": [m.model_dump(mode="json") for m in matches],
            "top_match": top_match.model_dump(mode="json"),
            "roi_estimate": roi.model_dump(mode="json"),
            "pricing": pricing.model_dump(mode="json"),
            "offer": offer.model_dump(mode="json"),
            "p_win": selection_data["p_win"],
            "expected_value_usd": selection_data["expected_value_usd"],
            "selection_score": selection_data["selection_score"],
            "why_this_business": selection_data["why_this_business"],
            "trace_id": trace.trace_id,
            "decision_trace": trace.model_dump(mode="json"),
            "analyzed_at": datetime.utcnow().isoformat(),
        }

        return result_dict, trace

    def analyze_business(
        self,
        session: Optional[Session],
        business: Any,
        audit: Optional[Any] = None,
        raw_signals: Optional[Dict[str, Any]] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Synchronous analysis execution and persistence."""
        result_dict, trace = self._compute_intelligence(business, audit=audit, raw_signals=raw_signals)
        biz_id = getattr(business, "id", 0)

        if session and persist and biz_id > 0:
            self._persist_intelligence_sync(session, business, result_dict, trace)

        return result_dict

    async def analyze_business_async(
        self,
        session: Optional[AsyncSession],
        business: Any,
        audit: Optional[Any] = None,
        raw_signals: Optional[Dict[str, Any]] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """Asynchronous analysis execution and persistence."""
        result_dict, trace = self._compute_intelligence(business, audit=audit, raw_signals=raw_signals)
        biz_id = getattr(business, "id", 0)

        if session and persist and biz_id > 0:
            await self._persist_intelligence_async(session, business, result_dict, trace)

        return result_dict

    def _persist_intelligence_sync(self, session: Session, business: Any, data: Dict[str, Any], trace: DecisionTrace):
        from app.database.models import ClientIntelligenceRecord
        
        stmt = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == business.id)
        record = session.scalar(stmt)
        if not record:
            record = ClientIntelligenceRecord(business_id=business.id)
            session.add(record)

        self._populate_record(record, data, trace)

        # Update ProspectMemory if present
        if hasattr(business, "memory") and business.memory:
            memory = business.memory
            comm_ctx = memory.commercial_context or {}
            comm_ctx["client_intelligence"] = {
                "segment": record.segment,
                "top_service_name": record.top_service_name,
                "fit_score": record.fit_score,
                "recommended_price_usd": record.recommended_price_usd,
                "target_price_usd": record.target_price_usd,
                "why_this_business": record.why_this_business,
                "analyzed_at": datetime.utcnow().isoformat(),
            }
            memory.commercial_context = comm_ctx
            session.add(memory)

        session.commit()

    async def _persist_intelligence_async(self, session: AsyncSession, business: Any, data: Dict[str, Any], trace: DecisionTrace):
        from app.database.models import ClientIntelligenceRecord
        
        stmt = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == business.id)
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            record = ClientIntelligenceRecord(business_id=business.id)
            session.add(record)

        self._populate_record(record, data, trace)

        from app.database.models import ProspectMemory
        stmt_mem = select(ProspectMemory).where(ProspectMemory.business_id == business.id)
        res_mem = await session.execute(stmt_mem)
        memory = res_mem.scalar_one_or_none()
        if memory:
            comm_ctx = memory.commercial_context or {}
            comm_ctx["client_intelligence"] = {
                "segment": record.segment,
                "top_service_name": record.top_service_name,
                "fit_score": record.fit_score,
                "recommended_price_usd": record.recommended_price_usd,
                "target_price_usd": record.target_price_usd,
                "why_this_business": record.why_this_business,
                "analyzed_at": datetime.utcnow().isoformat(),
            }
            memory.commercial_context = comm_ctx
            session.add(memory)

        await session.commit()

    def _populate_record(self, record: Any, data: Dict[str, Any], trace: DecisionTrace):
        record.segment = str(data["size_estimate"]["segment"])
        record.top_service_id = data["top_match"]["service_id"]
        record.top_service_name = data["top_match"]["service_name"]
        record.fit_score = data["top_match"]["fit_score"]
        record.p_win = data["p_win"]
        record.selection_score = data["selection_score"]
        record.recommended_price_usd = data["pricing"]["recommended_price_usd"]
        record.target_price_usd = data["pricing"]["target_price_usd"]
        record.full_profile = data["profile"]
        record.pain_points = data["pain_points"]
        record.service_matches = data["service_matches"]
        record.roi_estimate = data["roi_estimate"]
        record.client_offer = data["offer"]
        record.why_this_business = data["why_this_business"]
        record.decision_trace = trace.model_dump(mode="json")
        record.trace_id = trace.trace_id
        record.updated_at = datetime.utcnow()

    def get_client_intelligence(self, session: Session, business_id: int) -> Optional[Dict[str, Any]]:
        """Synchronously retrieves persisted intelligence for a given business."""
        from app.database.models import ClientIntelligenceRecord
        stmt = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == business_id)
        record = session.scalar(stmt)
        if not record:
            return None
        return self._format_record(record)

    async def get_client_intelligence_async(self, session: AsyncSession, business_id: int) -> Optional[Dict[str, Any]]:
        """Asynchronously retrieves persisted intelligence for a given business."""
        from app.database.models import ClientIntelligenceRecord
        stmt = select(ClientIntelligenceRecord).where(ClientIntelligenceRecord.business_id == business_id)
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return self._format_record(record)

    def _format_record(self, record: Any) -> Dict[str, Any]:
        return {
            "business_id": record.business_id,
            "segment": record.segment,
            "top_service_id": record.top_service_id,
            "top_service_name": record.top_service_name,
            "fit_score": record.fit_score,
            "p_win": record.p_win,
            "selection_score": record.selection_score,
            "recommended_price_usd": record.recommended_price_usd,
            "target_price_usd": record.target_price_usd,
            "profile": record.full_profile,
            "pain_points": record.pain_points,
            "service_matches": record.service_matches,
            "roi_estimate": record.roi_estimate,
            "offer": record.client_offer,
            "why_this_business": record.why_this_business,
            "trace_id": record.trace_id,
            "decision_trace": record.decision_trace,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
        }

    def select_top_prospects(self, session: Session, limit: int = 10) -> List[Dict[str, Any]]:
        """Synchronously returns top ranked prospects ordered by selection_score."""
        from app.database.models import ClientIntelligenceRecord, Business
        stmt = (
            select(ClientIntelligenceRecord, Business)
            .join(Business, ClientIntelligenceRecord.business_id == Business.id)
            .order_by(desc(ClientIntelligenceRecord.selection_score))
            .limit(limit)
        )
        results = session.execute(stmt).all()
        return [self._format_top_prospect(rec, biz) for rec, biz in results]

    async def select_top_prospects_async(self, session: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
        """Asynchronously returns top ranked prospects ordered by selection_score."""
        from app.database.models import ClientIntelligenceRecord, Business
        stmt = (
            select(ClientIntelligenceRecord, Business)
            .join(Business, ClientIntelligenceRecord.business_id == Business.id)
            .order_by(desc(ClientIntelligenceRecord.selection_score))
            .limit(limit)
        )
        res = await session.execute(stmt)
        results = res.all()
        return [self._format_top_prospect(rec, biz) for rec, biz in results]

    def _format_top_prospect(self, rec: Any, biz: Any) -> Dict[str, Any]:
        return {
            "business_id": biz.id,
            "business_name": biz.name,
            "domain": biz.domain,
            "niche": biz.niche,
            "country": biz.country,
            "segment": rec.segment,
            "top_service_name": rec.top_service_name,
            "fit_score": rec.fit_score,
            "p_win": rec.p_win,
            "recommended_price_usd": rec.recommended_price_usd,
            "target_price_usd": rec.target_price_usd,
            "selection_score": rec.selection_score,
            "why_this_business": rec.why_this_business,
            "trace_id": rec.trace_id,
        }

    def list_services(self) -> List[Dict[str, Any]]:
        """Returns the full 10-service catalog with details."""
        items = service_catalog.list_services()
        res = []
        for item in items:
            res.append({
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "description": item.description,
                "suitable_business_sizes": [s.value for s in item.suitable_business_sizes],
                "implementation_complexity": item.implementation_complexity,
                "estimated_implementation_effort_days": item.estimated_implementation_effort_days,
                "pricing_min_usd": item.pricing_min_usd,
                "pricing_max_usd": item.pricing_max_usd,
                "recommended_target_price_usd": item.recommended_target_price_usd,
                "expected_business_outcomes": item.expected_business_outcomes,
                "contraindications": item.contraindications,
            })
        return res


client_intelligence_engine = ClientIntelligenceEngine()
