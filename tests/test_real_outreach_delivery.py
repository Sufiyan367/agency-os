import uuid
import pytest
from datetime import datetime
from sqlalchemy import select

from app.database.connection import get_db, init_db
from app.models.entities import (
    LocalBusiness, LocalLead, LocalAudit, LocalOutreachMessage,
    LocalFollowup, LocalLeadEvent, LeadStatus, MessageStatus,
    FollowupStatus, EventType
)
from app.outreach.contact_verifier import contactability_verifier, ContactabilityVerifier
from app.outreach.delivery_service import OutreachDeliveryService, outreach_delivery_service
from app.outreach.providers.base import BaseEmailProvider
from app.outreach.providers.dry_run import DryRunEmailProvider, MockEmailProvider
from app.outreach.providers.resend_provider import ResendEmailProvider
from app.outreach.providers.sendgrid_provider import SendGridEmailProvider
from app.outreach.providers.smtp_provider import SMTPEmailProvider
from app.core.config import settings

@pytest.fixture(autouse=True)
async def setup_database():
    await init_db()

@pytest.mark.asyncio
async def test_invalid_and_malformed_email():
    """Verifies that syntactically invalid or malformed emails are rejected."""
    biz_dom = "acme-plumbing.com"
    
    for bad_email in ["not-an-email", "missing@domain", "@nodomain.com", "spaces in@domain.com", "plainaddress"]:
        res = contactability_verifier.verify_contact_email(bad_email, biz_dom)
        assert res.is_valid is False
        assert res.status == "CONTACT_UNAVAILABLE"
        assert "Malformed email syntax" in res.reason or "Invalid email format" in res.reason

@pytest.mark.asyncio
async def test_fabricated_and_guessed_email_prevention():
    """Verifies that placeholder and fabricated domains/mailboxes are strictly rejected."""
    biz_dom = "austin-hvac.com"

    for placeholder in ["info@example.com", "test@test.org", "owner@yourcompany.com", "admin@domain.com", "null@austin-hvac.com"]:
        res = contactability_verifier.verify_contact_email(placeholder, biz_dom)
        assert res.is_valid is False
        assert res.status == "CONTACT_UNAVAILABLE"
        assert "is not a legitimate recipient" in res.reason or "rejected" in res.reason

@pytest.mark.asyncio
async def test_wrong_domain_and_freemail_rejection():
    """Verifies that consumer free-mail addresses are rejected for corporate outreach unless allow_free_mail is true."""
    biz_dom = "houston-industrial-roofing.com"
    
    # Consumer freemail should be rejected by default
    res_gmail = contactability_verifier.verify_contact_email("roofingboss@gmail.com", biz_dom, allow_free_mail=False)
    assert res_gmail.is_valid is False
    assert "Consumer free-mail provider" in res_gmail.reason

    # Legitimate corporate email matching business domain
    res_corp = contactability_verifier.verify_contact_email("contact@houston-industrial-roofing.com", biz_dom)
    assert res_corp.is_valid is True
    assert res_corp.domain_match is True

@pytest.mark.asyncio
async def test_missing_email_non_fabrication():
    """Verifies that missing email returns CONTACT_UNAVAILABLE without fabricating an address."""
    res_none = contactability_verifier.verify_contact_email(None, "dallascooling.com")
    assert res_none.is_valid is False
    assert res_none.email is None
    assert res_none.status == "CONTACT_UNAVAILABLE"
    assert "Fabrication is strictly prohibited" in res_none.reason

    res_empty = contactability_verifier.verify_contact_email("", "dallascooling.com")
    assert res_empty.is_valid is False
    assert res_empty.status == "CONTACT_UNAVAILABLE"

@pytest.mark.asyncio
async def test_human_approval_gate_blocks_direct_send():
    """Verifies that unapproved messages cannot be sent and raise a clear safety error."""
    uid = uuid.uuid4().hex[:6]
    dom = f"safety-gate-{uid}.com"

    async for db in get_db():
        biz = LocalBusiness(name="Gate Test LLC", domain=dom, niche="HVAC", email=f"team@{dom}")
        db.add(biz)
        await db.flush()

        lead = LocalLead(business_id=biz.id, contact_name="Gate Lead", contact_email=f"team@{dom}", status=LeadStatus.QUALIFIED.value)
        db.add(lead)
        await db.flush()

        audit = LocalAudit(business_id=biz.id, url_audited=f"https://{dom}", overall_health_score=55.0)
        db.add(audit)
        await db.commit()

        # Draft message
        msg = await outreach_delivery_service.draft_evidence_grounded_outreach(db, lead.id)
        assert msg.status == MessageStatus.PENDING_APPROVAL.value

        # Attempt sending without operator approval
        with pytest.raises(RuntimeError) as exc:
            await outreach_delivery_service.send_approved_message(db, msg.id, is_operator_approved=False)
        assert "Explicit operator approval is strictly required" in str(exc.value)

@pytest.mark.asyncio
async def test_human_takeover_blocks_automated_sending():
    """Verifies that active human takeover halts sending of approved messages."""
    uid = uuid.uuid4().hex[:6]
    dom = f"takeover-block-{uid}.com"

    async for db in get_db():
        biz = LocalBusiness(name="Takeover Test", domain=dom, niche="HVAC", email=f"ops@{dom}")
        db.add(biz)
        await db.flush()

        lead = LocalLead(
            business_id=biz.id,
            contact_name="Lead Takeover",
            contact_email=f"ops@{dom}",
            status=LeadStatus.HUMAN_TAKEOVER.value,
            human_takeover=True,
            human_takeover_reason="Client requested live phone call"
        )
        db.add(lead)
        await db.flush()

        msg = LocalOutreachMessage(
            lead_id=lead.id,
            channel="EMAIL",
            recipient=lead.contact_email,
            subject="Important Note",
            body="Followup body",
            status=MessageStatus.APPROVED.value,
            is_mocked=True
        )
        db.add(msg)
        await db.commit()

        with pytest.raises(RuntimeError) as exc:
            await outreach_delivery_service.send_approved_message(db, msg.id)
        assert "Human takeover is ACTIVE" in str(exc.value)

@pytest.mark.asyncio
async def test_dry_run_provider_isolation():
    """Verifies that DRY_RUN mode generates simulated deliveries without external network requests."""
    provider = MockEmailProvider()
    res = await provider.send_email(
        to_email="verified@acmeheating.com",
        subject="Heating Infrastructure Review",
        body="Audit findings for your HVAC systems.",
        from_email="outreach@agencygrowth.co",
        from_name="Elena Vance"
    )
    assert res["status"] == "SUCCESS"
    assert res["provider"] == "dry_run"
    assert res["details"]["dry_run"] is True
    assert res["message_id"].startswith("dry_run_")

@pytest.mark.asyncio
async def test_successful_provider_send_lifecycle():
    """Verifies the complete flow from approval to successful send recording."""
    uid = uuid.uuid4().hex[:6]
    dom = f"success-send-{uid}.com"

    async for db in get_db():
        biz = LocalBusiness(name="Success Corp", domain=dom, niche="HVAC", email=f"hello@{dom}")
        db.add(biz)
        await db.flush()

        lead = LocalLead(business_id=biz.id, contact_name="Owner", contact_email=f"hello@{dom}", status=LeadStatus.QUALIFIED.value)
        db.add(lead)
        await db.flush()

        audit = LocalAudit(business_id=biz.id, url_audited=f"https://{dom}", overall_health_score=45.0)
        db.add(audit)
        await db.commit()

        msg = await outreach_delivery_service.draft_evidence_grounded_outreach(db, lead.id)
        assert msg.status == MessageStatus.PENDING_APPROVAL.value

        approved = await outreach_delivery_service.approve_outreach_message(db, msg.id, operator="Elena Vance")
        assert approved.status == MessageStatus.APPROVED.value

        res = await outreach_delivery_service.send_approved_message(db, approved.id)
        assert res["status"] == "SUCCESS"
        assert res["delivery_status"] in (MessageStatus.SENT.value, MessageStatus.MOCKED_SENT.value)

        await db.refresh(msg)
        assert msg.sent_at is not None
        assert msg.provider is not None

@pytest.mark.asyncio
async def test_duplicate_send_prevention_idempotency():
    """Verifies that an outreach message cannot be sent twice."""
    uid = uuid.uuid4().hex[:6]
    dom = f"idempotent-{uid}.com"

    async for db in get_db():
        biz = LocalBusiness(name="Idempotent Test", domain=dom, niche="HVAC", email=f"contact@{dom}")
        db.add(biz)
        await db.flush()

        lead = LocalLead(business_id=biz.id, contact_name="Idem Lead", contact_email=f"contact@{dom}", status=LeadStatus.QUALIFIED.value)
        db.add(lead)
        await db.flush()

        audit = LocalAudit(business_id=biz.id, url_audited=f"https://{dom}", overall_health_score=60.0)
        db.add(audit)
        await db.commit()

        msg = await outreach_delivery_service.draft_evidence_grounded_outreach(db, lead.id)
        await outreach_delivery_service.approve_outreach_message(db, msg.id)
        
        # First send succeeds
        await outreach_delivery_service.send_approved_message(db, msg.id)

        # Second send must be blocked
        with pytest.raises(ValueError) as exc:
            await outreach_delivery_service.send_approved_message(db, msg.id)
        assert "Duplicate dispatch is blocked" in str(exc.value)

@pytest.mark.asyncio
async def test_failed_provider_send_handling():
    """Verifies that a provider failure transitions message to SEND_FAILED and does NOT mark it SENT."""
    class FailingProvider(BaseEmailProvider):
        async def send_email(self, to_email, subject, body, html_body=None, from_email=None, from_name=None, reply_to=None):
            return {"status": "FAILED", "provider": "failing_mock", "details": {"error": "Simulated connection refused"}}

    failing_service = OutreachDeliveryService(email_provider=FailingProvider())
    uid = uuid.uuid4().hex[:6]
    dom = f"fail-prov-{uid}.com"

    async for db in get_db():
        biz = LocalBusiness(name="Fail Corp", domain=dom, niche="HVAC", email=f"admin@{dom}")
        db.add(biz)
        await db.flush()

        lead = LocalLead(business_id=biz.id, contact_name="Admin", contact_email=f"admin@{dom}", status=LeadStatus.QUALIFIED.value)
        db.add(lead)
        await db.flush()

        audit = LocalAudit(business_id=biz.id, url_audited=f"https://{dom}", overall_health_score=50.0)
        db.add(audit)
        await db.commit()

        msg = await failing_service.draft_evidence_grounded_outreach(db, lead.id)
        await failing_service.approve_outreach_message(db, msg.id)

        with pytest.raises(RuntimeError) as exc:
            await failing_service.send_approved_message(db, msg.id)
        assert "Email delivery unsuccessful" in str(exc.value)

        await db.refresh(msg)
        assert msg.status == MessageStatus.SEND_FAILED.value
        assert msg.sent_at is None

@pytest.mark.asyncio
async def test_provider_missing_credentials_fails_safely():
    """Verifies that providers fail safely when environment variables are missing."""
    # Resend without API key
    resend_no_key = ResendEmailProvider(api_key="")
    with pytest.raises(ValueError) as exc1:
        await resend_no_key.send_email(to_email="test@test.com", subject="Subj", body="Body")
    assert "RESEND_API_KEY is not configured" in str(exc1.value)

    # SendGrid without API key
    sendgrid_no_key = SendGridEmailProvider(api_key="")
    with pytest.raises(ValueError) as exc2:
        await sendgrid_no_key.send_email(to_email="test@test.com", subject="Subj", body="Body")
    assert "SENDGRID_API_KEY is not configured" in str(exc2.value)

    # SMTP without host
    smtp_no_host = SMTPEmailProvider(host="", port=587, user="")
    with pytest.raises(ValueError) as exc3:
        await smtp_no_host.send_email(to_email="test@test.com", subject="Subj", body="Body")
    assert "SMTP_HOST and SMTP_USER must be configured" in str(exc3.value)

@pytest.mark.asyncio
async def test_inbound_reply_routing_and_audit_trail():
    """Verifies that inbound replies enter REPLY_PENDING_HUMAN_REVIEW and produce an immutable audit trail."""
    uid = uuid.uuid4().hex[:6]
    dom = f"reply-audit-{uid}.com"

    async for db in get_db():
        biz = LocalBusiness(name="Reply Audit Co", domain=dom, niche="HVAC", email=f"owner@{dom}")
        db.add(biz)
        await db.flush()

        lead = LocalLead(business_id=biz.id, contact_name="Owner", contact_email=f"owner@{dom}", status=LeadStatus.QUALIFIED.value)
        db.add(lead)
        await db.commit()

        # Ingest incoming reply
        reply_res = await outreach_delivery_service.handle_incoming_reply(
            session=db,
            lead_id=lead.id,
            reply_body="Can we schedule a call next Tuesday at 10 AM?",
            sender_email=f"owner@{dom}"
        )
        assert reply_res["status"] == "REPLY_PENDING_HUMAN_REVIEW"
        assert reply_res["requires_human_review"] is True

        await db.refresh(lead)
        assert lead.status == LeadStatus.REPLY_PENDING_HUMAN_REVIEW.value

        # Verify audit trail event
        ev_q = select(LocalLeadEvent).where(
            LocalLeadEvent.lead_id == lead.id,
            LocalLeadEvent.event_type == EventType.CUSTOMER_REPLY.value
        )
        ev = (await db.execute(ev_q)).scalar_one_or_none()
        assert ev is not None
        assert ev.payload["requires_human_review"] is True
        assert "Tuesday at 10 AM" in ev.payload["reply_body"]
