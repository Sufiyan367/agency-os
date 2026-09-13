"""
Payment Intelligence Engine — Mega Prompt 8.
Monitors the payment verification funnel:
PROPOSAL_ACCEPTED -> PAYMENT_INSTRUCTIONS -> PAYMENT_PENDING -> VERIFIED_PAYMENT -> DELIVERY_UNLOCKED.
Detects friction, verification anomalies, and settlement delays without bypassing deterministic verification.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.models import Payment, PaymentWebhookEvent, Proposal

class PaymentIntelligenceEngine:
    """
    Analyzes payment turnaround times, webhook reliability, and settlement friction.
    Deterministic verification authority is strictly preserved.
    """

    @classmethod
    async def analyze_payment_funnel(
        cls,
        session: AsyncSession
    ) -> Dict[str, Any]:
        """
        Analyzes payments status distribution and identifies friction points.
        """
        stmt_all = select(Payment)
        payments = (await session.execute(stmt_all)).scalars().all()

        total = len(payments)
        confirmed = sum(1 for p in payments if p.status == "CONFIRMED")
        pending = sum(1 for p in payments if p.status == "PENDING")
        failed = sum(1 for p in payments if p.status in ("FAILED", "REJECTED"))

        # Webhook health
        stmt_wh = select(func.count(PaymentWebhookEvent.id))
        webhook_count = (await session.execute(stmt_wh)).scalar() or 0

        anomalies: List[Dict[str, Any]] = []

        now = datetime.utcnow()
        for p in payments:
            if p.status == "PENDING" and p.created_at:
                age_hours = (now - p.created_at).total_seconds() / 3600.0
                if age_hours > 48.0:
                    anomalies.append({
                        "payment_id": p.id,
                        "business_id": p.business_id,
                        "amount_usd": float(p.amount),
                        "age_hours": round(age_hours, 1),
                        "anomaly_type": "PROLONGED_PENDING_VERIFICATION",
                        "recommendation": "Operator should inspect gateway dashboard or issue automated reminder."
                    })

        settlement_rate = round((confirmed / total * 100.0), 1) if total > 0 else 100.0

        return {
            "total_payments_initiated": total,
            "confirmed_payments": confirmed,
            "pending_payments": pending,
            "failed_payments": failed,
            "settlement_rate_pct": settlement_rate,
            "webhooks_recorded": webhook_count,
            "anomalies_detected": anomalies,
            "verification_authority": "DETERMINISTIC_WEBHOOK_AND_SIGNATURE_AUTH",
            "auto_verify_permitted": False
        }


payment_intelligence_engine = PaymentIntelligenceEngine()
