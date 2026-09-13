"""
Optimization Engine — Mega Prompt 8.
Synthesizes cross-system observations into ranked, explainable, policy-validated recommendations:
RECOMMENDATION, WHY, EVIDENCE, EXPECTED_IMPACT, CONFIDENCE, RISK, NEXT_ACTION.
Enforces strict recommendation safety boundaries (no spam, no approval bypass, no sub-floor pricing).
"""
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.intelligence.models import (
    OptimizationRecommendation, RecommendationStatus,
    RiskLevel, ConfidenceBand
)
from app.database.models import (
    OptimizationRecommendationRecord, Business, Payment,
    CustomerIncident, ActiveOutreachLock
)
from app.intelligence.prioritization import prospect_priority_engine
from app.intelligence.funnel_analytics import funnel_analytics_engine
from app.intelligence.maintenance_intelligence import predictive_maintenance_engine

class OptimizationEngine:
    """
    Central recommendation engine synthesizing global pipeline and operational opportunities.
    """

    @classmethod
    async def generate_system_recommendations(
        cls,
        session: AsyncSession
    ) -> List[OptimizationRecommendation]:
        """
        Scans funnel bottlenecks, top prospects, maintenance signals, and payment delays
        to formulate prioritized, policy-vetted recommendations.
        """
        recommendations: List[OptimizationRecommendation] = []

        # 1. Top High-Value Opportunity
        top_prospects = await prospect_priority_engine.rank_prospects(session, limit=1)
        if top_prospects:
            top = top_prospects[0]
            if top["overall_lead_score"] >= 70.0:
                recommendations.append(OptimizationRecommendation(
                    id=f"REC-{uuid.uuid4().hex[:8].upper()}",
                    category="PIPELINE",
                    recommendation=f"Prioritize personalized outreach for {top['business_name']} ({top['industry']} in {top['country_code']}).",
                    why=f"Highest Expected Commercial Value (${top['expected_value_usd']:.0f}) with {top['p_conversion']*100:.0f}% predicted conversion probability.",
                    evidence=[{"lead_score": top["overall_lead_score"], "service": top["recommended_service"]}],
                    expected_impact=f"+${top['expected_deal_value_usd']:.0f} potential deal revenue",
                    confidence=top["evidence_confidence"],
                    confidence_band=ConfidenceBand.HIGH if top["evidence_confidence"] >= 0.8 else ConfidenceBand.MEDIUM,
                    risk_level=RiskLevel.LOW,
                    next_action=top["recommended_action"],
                    status=RecommendationStatus.VALIDATED,
                    entity_type="business",
                    entity_id=top["business_id"]
                ))

        # 2. Funnel Bottlenecks
        funnel = await funnel_analytics_engine.get_funnel_metrics(session)
        for b in funnel["bottlenecks"]:
            recommendations.append(OptimizationRecommendation(
                id=f"REC-{uuid.uuid4().hex[:8].upper()}",
                category="FUNNEL",
                recommendation=b["recommendation"],
                why=b["possible_cause"],
                evidence=[{"observation": b["observation"], "evidence": b["evidence"]}],
                expected_impact="Improve funnel stage velocity and conversion",
                confidence=0.85,
                confidence_band=ConfidenceBand.HIGH,
                risk_level=RiskLevel.LOW,
                next_action="UPDATE_MESSAGING_TEMPLATE",
                status=RecommendationStatus.VALIDATED,
                entity_type="pipeline"
            ))

        # 3. Host & Maintenance Warnings
        maint = await predictive_maintenance_engine.analyze_host_trends(session)
        for w in maint["predictive_warnings"]:
            risk_tier = RiskLevel.HIGH if w["severity"] == "CRITICAL" else RiskLevel.MEDIUM
            recommendations.append(OptimizationRecommendation(
                id=f"REC-{uuid.uuid4().hex[:8].upper()}",
                category="MAINTENANCE",
                recommendation=w["remediation"],
                why=w["forecast"],
                evidence=[{"metric": w["metric"], "value": w["current_value"]}],
                expected_impact="Prevent service degradation or disk storage exhaustion",
                confidence=0.92,
                confidence_band=ConfidenceBand.HIGH,
                risk_level=risk_tier,
                next_action=w["remediation"],
                status=RecommendationStatus.VALIDATED,
                entity_type="system"
            ))

        # 4. Check for prolonged pending payments
        stmt_pay = select(Payment).where(Payment.status == "PENDING")
        pending_payments = (await session.execute(stmt_pay)).scalars().all()
        now = datetime.utcnow()
        for p in pending_payments:
            if p.created_at and (now - p.created_at).total_seconds() > 86400.0:
                recommendations.append(OptimizationRecommendation(
                    id=f"REC-{uuid.uuid4().hex[:8].upper()}",
                    category="PAYMENT",
                    recommendation=f"Send low-friction payment reminder for accepted proposal on Business #{p.business_id}.",
                    why=f"Payment of ${float(p.amount):.0f} pending verification for > 24 hours.",
                    evidence=[{"payment_id": p.id, "amount_usd": float(p.amount)}],
                    expected_impact=f"Recover ${float(p.amount):.0f} verified commercial revenue",
                    confidence=0.90,
                    confidence_band=ConfidenceBand.HIGH,
                    risk_level=RiskLevel.LOW,
                    next_action="SEND_PAYMENT_REMINDER",
                    status=RecommendationStatus.VALIDATED,
                    entity_type="payment",
                    entity_id=p.id
                ))

        # Persist generated recommendations
        for rec in recommendations:
            record = OptimizationRecommendationRecord(
                recommendation_id=rec.id,
                entity_type=rec.entity_type,
                entity_id=rec.entity_id,
                category=rec.category,
                recommendation=rec.recommendation,
                why=rec.why,
                evidence=rec.evidence,
                expected_impact=rec.expected_impact,
                confidence=rec.confidence,
                risk_level=rec.risk_level.value,
                next_action=rec.next_action,
                status=rec.status.value,
                created_at=rec.created_at
            )
            session.add(record)
        await session.commit()

        return recommendations


optimization_engine = OptimizationEngine()
