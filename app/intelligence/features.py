"""
Unified Feature Extraction & Store — Mega Prompt 8.
Extracts standardized, normalized tabular feature vectors across CRM, Audits, Conversations,
Support, Delivery, and Financial domains without global mutable state.
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from app.database.models import (
    Business, Contact, AuditRun, AuditFinding, LeadScore,
    Deal, Proposal, Payment, ConversationEvent, Reply,
    SupportTicket, CustomerIncident, CustomerHealthMetric,
    ProspectEvidence
)


class UnifiedFeatureStore:
    """
    Extracts tabular numerical and categorical features for intelligence engines.
    Provides deterministic default fallbacks for cold-start cases.
    """

    @classmethod
    async def extract_business_features(
        cls,
        session: AsyncSession,
        business_id: int
    ) -> Dict[str, Any]:
        """
        Gathers comprehensive feature vector for a business / prospect entity.
        """
        features: Dict[str, Any] = {
            "business_id": business_id,
            "has_website": False,
            "has_email": False,
            "has_phone": False,
            "has_verified_contact": False,
            "performance_score": 50.0,
            "seo_score": 50.0,
            "a11y_score": 50.0,
            "ux_conversion_score": 50.0,
            "overall_health_score": 50.0,
            "critical_findings_count": 0,
            "high_findings_count": 0,
            "verified_evidence_count": 0,
            "inbound_replies_count": 0,
            "positive_replies_count": 0,
            "objection_count": 0,
            "proposals_count": 0,
            "total_deal_value_usd": 0.0,
            "is_opted_out": False,
            "country_code": "US",
            "industry": "General",
            "recency_days": 1.0,
            "contactability_score": 50.0,
            "gdp_per_capita": 65000.0,
            "niche_avg_deal_size": 750.0,
        }

        # 1. Business Core
        biz = await session.get(Business, business_id)
        if not biz:
            return features

        web_url = getattr(biz, "website_url", None) or getattr(biz, "website", None)
        features["has_website"] = bool(web_url and len(web_url.strip()) > 4)
        features["country_code"] = getattr(biz, "country_code", None) or getattr(biz, "country", None) or "US"
        features["industry"] = getattr(biz, "niche", None) or getattr(biz, "industry", None) or "General"
        if biz.created_at:
            features["recency_days"] = max(0.1, (datetime.utcnow() - biz.created_at).total_seconds() / 86400.0)

        # 2. Contacts
        stmt_contacts = select(Contact).where(Contact.business_id == business_id)
        contacts = (await session.execute(stmt_contacts)).scalars().all()
        if contacts:
            features["has_email"] = any(bool(c.email and "@" in c.email) for c in contacts)
            features["has_phone"] = any(bool(c.phone and len(c.phone.strip()) > 6) for c in contacts)
            features["has_verified_contact"] = any(getattr(c, "is_verified", False) or c.email_status == "verified" for c in contacts)
            features["is_opted_out"] = any(getattr(c, "opt_out", False) or c.email_status == "opt_out" for c in contacts)

        # 3. Contactability
        c_score = 0.0
        if features["has_email"]: c_score += 45.0
        if features["has_phone"]: c_score += 25.0
        if features["has_verified_contact"]: c_score += 30.0
        features["contactability_score"] = min(100.0, c_score)

        # 4. Technical Audit Runs & Findings
        stmt_audit = (
            select(AuditRun)
            .where(AuditRun.business_id == business_id)
            .order_by(desc(AuditRun.audited_at))
            .limit(1)
        )
        audit = (await session.execute(stmt_audit)).scalar_one_or_none()
        if audit:
            features["performance_score"] = float(audit.performance_score or 50.0)
            features["seo_score"] = float(audit.seo_score or 50.0)
            features["a11y_score"] = float(audit.a11y_score or 50.0)
            features["ux_conversion_score"] = float(audit.ux_conversion_score or 50.0)
            features["overall_health_score"] = float(audit.overall_health_score or 50.0)

            # Audit findings
            stmt_findings = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
            findings = (await session.execute(stmt_findings)).scalars().all()
            features["critical_findings_count"] = sum(1 for f in findings if f.severity in ("CRITICAL", "HIGH"))
            features["high_findings_count"] = len(findings)

        # 5. Verified Evidence
        stmt_ev = (
            select(func.count(ProspectEvidence.id))
            .where(
                ProspectEvidence.business_id == business_id,
                ProspectEvidence.is_verified == True
            )
        )
        features["verified_evidence_count"] = (await session.execute(stmt_ev)).scalar() or 0

        # 6. Conversation & Replies
        stmt_replies = select(Reply).where(Reply.business_id == business_id)
        replies = (await session.execute(stmt_replies)).scalars().all()
        features["inbound_replies_count"] = len(replies)
        features["positive_replies_count"] = sum(1 for r in replies if r.classification in ("INTERESTED", "MEETING_REQUEST", "POSITIVE"))
        features["objection_count"] = sum(1 for r in replies if r.classification in ("PRICE_OBJECTION", "NOT_INTERESTED", "TIMING_OBJECTION"))

        # 7. Deals & Proposals
        stmt_proposals = select(Proposal).where(Proposal.business_id == business_id)
        proposals = (await session.execute(stmt_proposals)).scalars().all()
        features["proposals_count"] = len(proposals)
        if proposals:
            features["total_deal_value_usd"] = max(float(p.total_value) for p in proposals)

        # 8. GCC / Geographic Wealth Calibration
        gdp_table = {
            "SA": 78000.0, "AE": 88000.0, "QA": 115000.0,
            "KW": 72000.0, "BH": 55000.0, "OM": 45000.0,
            "US": 76000.0, "GB": 52000.0
        }
        features["gdp_per_capita"] = gdp_table.get(features["country_code"], 60000.0)

        # Industry deal size baseline
        niche_table = {
            "Automotive": 850.0, "HVAC": 950.0,
            "Dental": 1200.0, "Roofing": 1100.0
        }
        features["niche_avg_deal_size"] = niche_table.get(features["industry"], 750.0)

        return features

    @classmethod
    async def extract_customer_health_features(
        cls,
        session: AsyncSession,
        customer_id: int
    ) -> Dict[str, Any]:
        """
        Extracts multi-signal health features for a post-sale customer.
        """
        features: Dict[str, Any] = {
            "customer_id": customer_id,
            "open_tickets_count": 0,
            "critical_incidents_count": 0,
            "sla_breach_count": 0,
            "avg_response_minutes": 25.0,
            "uptime_pct": 99.9,
            "unresolved_days_max": 0.0,
            "payment_delinquent": False,
            "negative_sentiment_count": 0
        }

        # 1. Tickets
        stmt_tickets = select(SupportTicket).where(SupportTicket.customer_id == customer_id)
        tickets = (await session.execute(stmt_tickets)).scalars().all()
        features["open_tickets_count"] = sum(1 for t in tickets if t.status not in ("RESOLVED", "CLOSED"))
        features["sla_breach_count"] = sum(1 for t in tickets if t.sla_breached)

        # 2. Incidents
        stmt_incidents = select(CustomerIncident).where(CustomerIncident.customer_id == customer_id)
        incidents = (await session.execute(stmt_incidents)).scalars().all()
        features["critical_incidents_count"] = sum(1 for i in incidents if i.severity in ("SEV-1", "SEV-2") and not i.is_resolved)

        # 3. Telemetry
        stmt_metric = (
            select(CustomerHealthMetric)
            .where(CustomerHealthMetric.customer_id == customer_id)
            .order_by(desc(CustomerHealthMetric.last_checked_at))
            .limit(1)
        )
        metric = (await session.execute(stmt_metric)).scalar_one_or_none()
        if metric:
            features["uptime_pct"] = metric.uptime_pct

        return features


feature_store = UnifiedFeatureStore()
unified_feature_store = feature_store
