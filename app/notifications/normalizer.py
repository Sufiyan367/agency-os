import re
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.event_bus import AgencyEvent
from app.notifications.models import (
    NotificationEventPayload,
    NotificationPriority,
    NotificationCategory,
)

SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[a-z0-9_\-\.]{15,}"),
    re.compile(r"sk_(?:live|test)_[a-zA-Z0-9]{10,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{10,}"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*['\"]?)[a-z0-9_\-]{10,}['\"]?"),
    re.compile(r"(?i)(password\s*[:=]\s*['\"]?)[^\s'\"]+['\"]?"),
    re.compile(r"(?i)(secret\s*[:=]\s*['\"]?)[a-z0-9_\-]{10,}['\"]?"),
    re.compile(r"(?i)(token\s*[:=]\s*['\"]?)[a-z0-9_\-]{10,}['\"]?"),
    re.compile(r"re_[a-zA-Z0-9]{20,}"),  # Resend API key
    re.compile(r"SG\.[a-zA-Z0-9_\-\.]{20,}"),  # SendGrid API key
    re.compile(r"rzp_(live|test)_[a-zA-Z0-9]{10,}"),  # Razorpay key
]

STACK_TRACE_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\):[\s\S]*"),
    re.compile(r'File ".*?", line \d+, in .*'),
]


def sanitize_text(text: Optional[str]) -> str:
    """Removes API keys, passwords, tokens, stack traces, and sensitive internal paths."""
    if not text:
        return ""
    clean = str(text)
    # Strip stack traces
    for st in STACK_TRACE_PATTERNS:
        clean = st.sub("[STACK TRACE REMOVED]", clean)
    # Strip secrets
    for pat in SECRET_PATTERNS:
        clean = pat.sub("[REDACTED]", clean)
    # Strip sensitive absolute paths
    clean = re.sub(r"[A-Za-z]:\\[\w\s\\.-]+", "[FILE_PATH]", clean)
    clean = re.sub(r"/(?:opt|etc|home|root|var)/[\w/.-]+", "[FILE_PATH]", clean)
    return clean.strip()


def sanitize_metadata(meta: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively redacts sensitive keys from metadata dictionary."""
    if not meta or not isinstance(meta, dict):
        return {}
    safe = {}
    sensitive_keys = {"password", "secret", "token", "api_key", "client_secret", "refresh_token", "hash", "p256dh", "auth"}
    for k, v in meta.items():
        if any(s in k.lower() for s in sensitive_keys):
            safe[k] = "[REDACTED]"
        elif isinstance(v, dict):
            safe[k] = sanitize_metadata(v)
        elif isinstance(v, str):
            safe[k] = sanitize_text(v)
        elif isinstance(v, (int, float, bool)) or v is None:
            safe[k] = v
        else:
            safe[k] = str(v)
    return safe


class NotificationNormalizer:
    """
    Translates raw AgencyEvents into standardized, sanitized,
    CEO-safe NotificationEventPayload objects.
    """

    @classmethod
    def normalize_event(cls, event: AgencyEvent) -> Optional[NotificationEventPayload]:
        evt_type = (event.event_type or "").upper().strip()
        payload = event.payload or {}
        meta = payload.get("metadata", {}) or {}

        # 1. Financial / Payment Verification
        if evt_type in ("PAYMENT_VERIFIED", "DELIVERY_UNLOCKED") or (evt_type == "LIFECYCLE_TRANSITION" and payload.get("to_stage") in ("PAYMENT_VERIFIED", "DELIVERY_UNLOCKED")):
            client_name = payload.get("client_name") or payload.get("customer_name") or meta.get("customer_name") or f"Client #{event.entity_id}"
            amount = payload.get("amount_usd") or meta.get("amount_usd") or meta.get("deal_value") or 0.0
            ref = payload.get("payment_reference") or meta.get("payment_reference") or "VERIFIED_TRANSFER"
            safe_ref = sanitize_text(str(ref))[:30]

            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="PAYMENT_VERIFIED",
                category=NotificationCategory.FINANCIAL,
                priority=NotificationPriority.HIGH,
                title="💰 Payment Verified",
                body=f"Client: {sanitize_text(client_name)}\nAmount: ${amount:,.2f} USD\nReference: {safe_ref}\nStatus: DELIVERY UNLOCKED",
                deep_link=f"/dashboard#pipeline?client={event.entity_id}",
                action_required=False,
                business_id=event.entity_id if event.entity_type == "business" else None,
                payment_id=payload.get("payment_id"),
                deduplication_key=f"pay_verified_{event.entity_id}_{safe_ref}",
                metadata_safe=sanitize_metadata({"amount_usd": amount, "reference": safe_ref, "client_name": client_name}),
                created_at=event.timestamp
            )

        if evt_type in ("PAYMENT_ANOMALY", "PAYMENT_MISMATCH", "PAYMENT_UNDERPAYMENT", "PAYMENT_VERIFICATION_REQUIRED", "PAYMENT_REJECTED", "PAYMENT_FAILED"):
            client_name = payload.get("client_name") or f"Account #{event.entity_id}"
            reason = payload.get("reason") or "Verification criteria not satisfied."
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="PAYMENT_ANOMALY",
                category=NotificationCategory.FINANCIAL,
                priority=NotificationPriority.CRITICAL,
                title="⚠️ Payment Verification Anomaly",
                body=f"Client: {sanitize_text(client_name)}\nIssue: {sanitize_text(reason)}\nAction: Immediate CEO Review Required.",
                deep_link=f"/dashboard#pipeline?anomaly={event.entity_id}",
                action_required=True,
                action_url=f"/dashboard#pipeline?anomaly={event.entity_id}",
                business_id=event.entity_id if event.entity_type == "business" else None,
                deduplication_key=f"pay_anomaly_{event.entity_id}_{evt_type}",
                metadata_safe=sanitize_metadata({"reason": reason, "event_type": evt_type}),
                created_at=event.timestamp
            )

        # 2. Security Incidents
        if evt_type in ("SECURITY_INCIDENT", "SUSPECTED_BREACH", "UNAUTHORIZED_ACCESS", "DANGEROUS_CONFIG_CHANGE"):
            title = payload.get("title") or "Security Incident Detected"
            detail = payload.get("detail") or "Suspicious activity detected in operations core."
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="SECURITY_INCIDENT",
                category=NotificationCategory.SECURITY,
                priority=NotificationPriority.CRITICAL,
                title=f"🚨 {sanitize_text(title)}",
                body=f"Alert: {sanitize_text(detail)}\nPolicy: High-impact security gate triggered.",
                deep_link="/dashboard#security",
                action_required=True,
                action_url="/dashboard#security",
                deduplication_key=f"sec_incident_{event.event_id}",
                metadata_safe=sanitize_metadata(payload),
                created_at=event.timestamp
            )

        # 3. Production Outage / SEV-1 Incidents
        if evt_type in ("SEV1_INCIDENT", "PRODUCTION_OUTAGE", "CUSTOMER_FACING_FAILURE") or (evt_type == "INCIDENT_CREATED" and str(payload.get("severity", "")).upper() == "SEV-1"):
            cust = payload.get("customer_name") or f"Customer #{event.entity_id}"
            issue = payload.get("issue") or payload.get("title") or "Critical production service interruption."
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="SEV1_INCIDENT",
                category=NotificationCategory.PRODUCTION,
                priority=NotificationPriority.CRITICAL,
                severity="SEV-1",
                title="💥 Production Incident (SEV-1)",
                body=f"Customer: {sanitize_text(cust)}\nIssue: {sanitize_text(issue)}\nAction: CEO review required.",
                deep_link=f"/dashboard#support?incident={event.entity_id}",
                action_required=True,
                action_url=f"/dashboard#support?incident={event.entity_id}",
                customer_id=payload.get("customer_id"),
                incident_id=event.entity_id,
                deduplication_key=f"sev1_incident_{event.entity_id}",
                metadata_safe=sanitize_metadata({"customer": cust, "issue": issue}),
                created_at=event.timestamp
            )

        # 4. Delivery & Deployments
        if evt_type in ("DEPLOYMENT_COMPLETED", "PRODUCTION_VERIFIED") or (evt_type == "LIFECYCLE_TRANSITION" and payload.get("to_stage") == "LIVE"):
            client_name = payload.get("client_name") or f"Client #{event.entity_id}"
            build_v = payload.get("build_version") or "v1.0"
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="DEPLOYMENT_COMPLETED",
                category=NotificationCategory.DELIVERY,
                priority=NotificationPriority.HIGH,
                title="🚀 Production Deployment Completed",
                body=f"Client: {sanitize_text(client_name)}\nBuild: {build_v}\nQA: Passed\nProduction: Healthy",
                deep_link=f"/dashboard#delivery?project={event.entity_id}",
                action_required=False,
                project_id=event.entity_id,
                deduplication_key=f"delivery_live_{event.entity_id}_{build_v}",
                metadata_safe=sanitize_metadata({"client": client_name, "build": build_v}),
                created_at=event.timestamp
            )

        if evt_type in ("DEPLOYMENT_FAILED", "ROLLBACK_STARTED", "ROLLBACK_FAILED", "QA_FAILED"):
            client_name = payload.get("client_name") or f"Client #{event.entity_id}"
            issue = payload.get("error") or payload.get("reason") or "Deployment verification check failed."
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="DEPLOYMENT_FAILED",
                category=NotificationCategory.DELIVERY,
                priority=NotificationPriority.CRITICAL,
                title="⚠️ Deployment Failure / Rollback",
                body=f"Client: {sanitize_text(client_name)}\nIssue: {sanitize_text(issue)}\nAction: Inspection required.",
                deep_link=f"/dashboard#delivery?project={event.entity_id}",
                action_required=True,
                action_url=f"/dashboard#delivery?project={event.entity_id}",
                project_id=event.entity_id,
                deduplication_key=f"delivery_fail_{event.entity_id}_{evt_type}",
                metadata_safe=sanitize_metadata({"client": client_name, "error": issue}),
                created_at=event.timestamp
            )

        # 5. Sales & Customer Engagement
        if evt_type in ("POSITIVE_REPLY", "INBOUND_POSITIVE") or (evt_type == "LIFECYCLE_TRANSITION" and payload.get("to_stage") == "POSITIVE"):
            prospect_name = payload.get("prospect_name") or payload.get("business_name") or f"Prospect #{event.entity_id}"
            next_action = payload.get("next_action") or "Demo eligible"
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="POSITIVE_REPLY",
                category=NotificationCategory.SALES,
                priority=NotificationPriority.HIGH,
                title="💬 Positive Sales Reply",
                body=f"Prospect: {sanitize_text(prospect_name)}\nIntent: POSITIVE\nNext Action: {sanitize_text(next_action)}",
                deep_link=f"/dashboard#conversations?lead={event.entity_id}",
                action_required=True,
                action_url=f"/dashboard#conversations?lead={event.entity_id}",
                business_id=event.entity_id,
                deduplication_key=f"sales_pos_reply_{event.entity_id}",
                metadata_safe=sanitize_metadata({"prospect": prospect_name, "next_action": next_action}),
                created_at=event.timestamp
            )

        if evt_type in ("PROPOSAL_ACCEPTED",) or (evt_type == "LIFECYCLE_TRANSITION" and payload.get("to_stage") == "PROPOSAL_ACCEPTED"):
            prospect_name = payload.get("prospect_name") or f"Prospect #{event.entity_id}"
            value = payload.get("deal_value") or meta.get("deal_value") or 0.0
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="PROPOSAL_ACCEPTED",
                category=NotificationCategory.SALES,
                priority=NotificationPriority.HIGH,
                title="📄 Proposal Accepted",
                body=f"Client: {sanitize_text(prospect_name)}\nValue: ${value:,.2f} USD\nNext: Payment Pending",
                deep_link=f"/dashboard#pipeline?lead={event.entity_id}",
                action_required=False,
                business_id=event.entity_id,
                deduplication_key=f"sales_prop_accepted_{event.entity_id}",
                metadata_safe=sanitize_metadata({"prospect": prospect_name, "deal_value": value}),
                created_at=event.timestamp
            )

        if evt_type in ("DEAL_WON", "WON"):
            prospect_name = payload.get("prospect_name") or f"Prospect #{event.entity_id}"
            value = payload.get("deal_value") or 0.0
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="DEAL_WON",
                category=NotificationCategory.SALES,
                priority=NotificationPriority.HIGH,
                title="🏆 Deal Won",
                body=f"Client: {sanitize_text(prospect_name)}\nDeal Value: ${value:,.2f} USD\nDelivery Unlocked.",
                deep_link=f"/dashboard#pipeline?lead={event.entity_id}",
                action_required=False,
                business_id=event.entity_id,
                deduplication_key=f"sales_deal_won_{event.entity_id}",
                metadata_safe=sanitize_metadata({"prospect": prospect_name, "deal_value": value}),
                created_at=event.timestamp
            )

        # 6. Approvals
        if evt_type in ("APPROVAL_REQUIRED", "HUMAN_TAKEOVER_REQUIRED", "NEEDS_HUMAN"):
            action = payload.get("action_name") or payload.get("title") or "High-Impact Action"
            target = payload.get("target_name") or f"Entity #{event.entity_id}"
            risk = payload.get("risk_level") or "High-impact"
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="APPROVAL_REQUIRED",
                category=NotificationCategory.SECURITY if "config" in str(action).lower() else NotificationCategory.SALES,
                priority=NotificationPriority.CRITICAL if "high" in str(risk).lower() else NotificationPriority.HIGH,
                title="🔐 CEO Approval Required",
                body=f"Action: {sanitize_text(action)}\nTarget: {sanitize_text(target)}\nRisk: {risk}\nReview requested.",
                deep_link=payload.get("approval_link") or "/dashboard#queue",
                action_required=True,
                action_url=payload.get("approval_link") or "/dashboard#queue",
                business_id=event.entity_id if event.entity_type == "business" else None,
                deduplication_key=f"approval_req_{event.entity_id}_{action}",
                metadata_safe=sanitize_metadata({"action": action, "target": target}),
                created_at=event.timestamp
            )

        # 7. Outreach Governance & Compliance
        if evt_type in ("OUTREACH_BLOCKED", "COMPLIANCE_BLOCK", "SUPPRESSION_FAILURE"):
            reason = payload.get("reason") or "Policy enforcement stop rule"
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="OUTREACH_BLOCKED",
                category=NotificationCategory.COMPLIANCE,
                priority=NotificationPriority.HIGH,
                title="⚠️ Outreach Blocked",
                body=f"Reason: {sanitize_text(reason)}\nLead ID: #{event.entity_id}",
                deep_link=f"/dashboard#queue?lead={event.entity_id}",
                action_required=False,
                business_id=event.entity_id if event.entity_type == "business" else None,
                deduplication_key=f"outreach_block_{event.entity_id}_{reason[:20]}",
                metadata_safe=sanitize_metadata({"reason": reason}),
                created_at=event.timestamp
            )

        # 8. Support / Customer Remediation
        if evt_type in ("INCIDENT_RESOLVED", "AUTOMATIC_REMEDIATION_SUCCESS"):
            client_name = payload.get("customer_name") or f"Customer #{event.entity_id}"
            issue = payload.get("issue") or "Service health recovered"
            resolution = payload.get("resolution") or "Automatic self-healing retry succeeded"
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type="INCIDENT_RESOLVED",
                category=NotificationCategory.SUPPORT,
                priority=NotificationPriority.NORMAL,
                title="🛠️ Customer Incident Resolved",
                body=f"Client: {sanitize_text(client_name)}\nIssue: {sanitize_text(issue)}\nResolution: {sanitize_text(resolution)}",
                deep_link=f"/dashboard#support?incident={event.entity_id}",
                action_required=False,
                incident_id=event.entity_id,
                deduplication_key=f"support_res_{event.entity_id}",
                metadata_safe=sanitize_metadata({"client": client_name, "resolution": resolution}),
                created_at=event.timestamp
            )

        # 9. Routine / Normal Lifecycle Milestones
        if evt_type in ("AUDIT_COMPLETED", "DEMO_GENERATED", "LEAD_DISCOVERY_MILESTONE", "MAINTENANCE_COMPLETED"):
            title = payload.get("title") or f"Milestone: {evt_type.replace('_', ' ').title()}"
            msg = payload.get("message") or f"Routine milestone completed for entity #{event.entity_id}"
            return NotificationEventPayload(
                event_id=event.event_id,
                event_type=evt_type,
                category=NotificationCategory.SYSTEM,
                priority=NotificationPriority.NORMAL,
                title=f"ℹ️ {sanitize_text(title)}",
                body=sanitize_text(msg),
                deep_link="/dashboard#overview",
                action_required=False,
                deduplication_key=f"routine_{event.entity_id}_{evt_type}",
                metadata_safe=sanitize_metadata(payload),
                created_at=event.timestamp
            )

        # Other events classified as LOW / Telemetry or skipped
        return None
