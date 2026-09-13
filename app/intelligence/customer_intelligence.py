"""
Customer Health & Churn Retention Engine — Mega Prompt 8.
Evaluates multi-signal customer health (HEALTHY, DEGRADED, AT_RISK, CRITICAL)
and predicts churn risk based on ticket volume, incident frequency, SLA compliance, and uptime.
Forbids autonomous contract cancellations, refunds, or downgrades.
"""
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.database.models import Customer, SupportTicket, CustomerIncident, CustomerHealthMetric
from app.intelligence.models import (
    IntelligenceSignal, SignalType, EpistemicStatus,
    ConfidenceBand
)
from app.intelligence.signals import signal_registry
from app.intelligence.features import feature_store

class CustomerIntelligenceEngine:
    """
    Evaluates customer health and forecasts churn risk with actionable retention recommendations.
    """

    @classmethod
    async def evaluate_customer_health(
        cls,
        session: AsyncSession,
        customer_id: int
    ) -> Dict[str, Any]:
        """
        Synthesizes support, telemetry, and SLA records into a calibrated health tier.
        """
        features = await feature_store.extract_customer_health_features(session, customer_id)

        open_tickets = features["open_tickets_count"]
        crit_incidents = features["critical_incidents_count"]
        sla_breaches = features["sla_breach_count"]
        uptime = features["uptime_pct"]

        # Health Scoring (0 - 100)
        health_score = 100.0
        health_score -= (crit_incidents * 35.0)
        health_score -= (sla_breaches * 20.0)
        health_score -= (open_tickets * 10.0)
        if uptime < 99.0:
            health_score -= 25.0

        health_score = round(max(0.0, min(100.0, health_score)), 1)

        # Health Classification
        if health_score >= 85.0:
            tier = "HEALTHY"
        elif health_score >= 65.0:
            tier = "DEGRADED"
        elif health_score >= 40.0:
            tier = "AT_RISK"
        else:
            tier = "CRITICAL"

        # Churn Risk Calculation (0.0 to 1.0)
        churn_risk = round(max(0.05, min(0.95, (100.0 - health_score) / 100.0)), 2)

        retention_actions: List[str] = []
        if crit_incidents > 0:
            retention_actions.append("Dispatch senior engineering lead to review and resolve open high-severity incidents.")
        if sla_breaches > 0:
            retention_actions.append("Issue proactive SLA compliance review and executive check-in.")
        if not retention_actions:
            retention_actions.append("Account is healthy; conduct scheduled monthly value report.")

        # Persist health signal
        signal = signal_registry.create_signal(
            entity_type="customer",
            entity_id=customer_id,
            signal_type=SignalType.CUSTOMER_HEALTH,
            epistemic_status=EpistemicStatus.PREDICTION,
            signal_value=health_score,
            confidence=0.88,
            source="customer_intelligence_engine",
            evidence=[{"tier": tier, "churn_risk": churn_risk, "actions": retention_actions}]
        )
        await signal_registry.persist_signal(session, signal)

        return {
            "customer_id": customer_id,
            "health_score": health_score,
            "health_tier": tier,
            "churn_risk_score": churn_risk,
            "open_tickets": open_tickets,
            "critical_incidents": crit_incidents,
            "sla_breaches": sla_breaches,
            "uptime_pct": uptime,
            "recommended_retention_actions": retention_actions,
            "confidence": 0.88,
            "confidence_band": "HIGH"
        }


customer_intelligence_engine = CustomerIntelligenceEngine()
