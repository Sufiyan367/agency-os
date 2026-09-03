"""
Real Outreach Delivery Engine Demo Lifecycle Script
Demonstrates:
1. Create real-style qualified prospect
2. Verify contactability (zero email guessing/fabrication)
3. Generate evidence-grounded outreach using observed diagnostic metrics
4. Put message into PENDING_APPROVAL
5. Attempt automatic send -> MUST FAIL (Human Approval Gate enforced)
6. Human approval sign-off
7. Mock provider dispatch (DRY_RUN / MockEmailProvider)
8. Record successful send event with provider tracking
9. Attempt duplicate send -> MUST BE BLOCKED (Idempotency check)
10. Simulate prospect reply
11. Put reply into HUMAN REVIEW (REPLY_PENDING_HUMAN_REVIEW)
12. Activate human takeover
13. Verify subsequent automated responses are blocked

Usage:
    python scripts/demo_real_outreach.py
"""

import sys
import os
import uuid
import asyncio
from datetime import datetime

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database.connection import get_db, init_db
from app.models.entities import (
    LocalBusiness, LocalLead, LocalAudit, LocalOutreachMessage,
    LocalFollowup, LocalLeadEvent, LeadStatus, MessageStatus,
    FollowupStatus, EventType
)
from app.outreach.delivery_service import outreach_delivery_service
from app.outreach.providers.factory import get_email_provider
from app.outreach.contact_verifier import contactability_verifier
from app.core.config import settings

def print_step(step_num: int, title: str):
    print("\n" + "=" * 80)
    print(f" STEP {step_num:02d}: {title.upper()}")
    print("=" * 80)

async def run_outreach_lifecycle_demo():
    print("\n" + "#" * 80)
    print(" JARVIS REVENUE OPERATIONS - REAL OUTREACH DELIVERY DEMO")
    print(f" Mode: {'DRY_RUN (SAFE SIMULATION)' if settings.EMAIL_DRY_RUN else 'LIVE PROVIDER'}")
    print(f" Active Provider: {get_email_provider().__class__.__name__}")
    print("#" * 80)

    await init_db()

    async for db in get_db():
        unique_suffix = uuid.uuid4().hex[:6]
        test_domain = f"austin-precision-hvac-{unique_suffix}.com"
        observed_email = f"contact@{test_domain}"

        # ----------------------------------------------------------------------
        # STEP 1: Create Real-Style Qualified Prospect
        # ----------------------------------------------------------------------
        print_step(1, "Create Real-Style Qualified Prospect")
        biz = LocalBusiness(
            name="Austin Precision HVAC Systems",
            domain=test_domain,
            website_url=f"https://{test_domain}",
            niche="Commercial & Residential HVAC",
            address="4200 Congress Ave, Austin, TX 78701",
            city="Austin",
            state="TX",
            country="US",
            email=observed_email,
            phone="+1-512-555-0198",
            rating=4.9,
            review_count=142,
            source="google_maps"
        )
        db.add(biz)
        await db.flush()

        lead = LocalLead(
            business_id=biz.id,
            contact_name="Marcus Vance (Operations Director)",
            contact_email=observed_email,
            contact_phone=biz.phone,
            status=LeadStatus.QUALIFIED.value,
            qualification="HIGH_VALUE",
            lead_score=88.5,
            intent_level="HIGH",
            confidence=0.92,
            pain_points=["Slow mobile landing page", "No online appointment booking"]
        )
        db.add(lead)
        await db.flush()

        # Add technical audit observations for evidence grounding
        audit = LocalAudit(
            business_id=biz.id,
            url_audited=f"https://{test_domain}",
            overall_health_score=42.0,
            performance_score=38.0,
            seo_score=55.0,
            accessibility_score=60.0,
            security_score=75.0,
            mobile_responsive=True,
            findings=[
                {"category": "PERFORMANCE", "issue": "LCP exceeds 4.8s due to unoptimized hero assets", "severity": "HIGH"},
                {"category": "CONVERSION", "issue": "Missing interactive scheduling widget above fold", "severity": "CRITICAL"}
            ],
            summary="High commercial capacity HVAC operator with severe mobile performance bottleneck."
        )
        db.add(audit)
        await db.commit()
        print(f"✓ Created Qualified Business: {biz.name} ({biz.domain})")
        print(f"✓ Created Lead #{lead.id} ({lead.contact_name}) - Score: {lead.lead_score}/100")
        print(f"✓ Recorded Technical Audit: Health Score {audit.overall_health_score}/100 | Findings: {len(audit.findings)}")

        # ----------------------------------------------------------------------
        # STEP 2: Verify Contactability (Zero Guessing / Fabrication)
        # ----------------------------------------------------------------------
        print_step(2, "Verify Contactability (Strict Non-Fabrication)")
        contact_res = await outreach_delivery_service.verify_and_qualify_contact(db, lead.id)
        assert contact_res.is_valid is True, "Contact should be verified valid."
        assert contact_res.domain_match is True, "Domain should match business domain."
        print(f"✓ Contact verified: {contact_res.email}")
        print(f"✓ Verification Reason: {contact_res.reason}")
        print(f"✓ Domain Match: {contact_res.domain_match}")
        print(f"✓ Lead Status transitioned to: {lead.status}")

        # Also demonstrate rejection of fabricated / placeholder emails
        bogus_res = contactability_verifier.verify_contact_email("info@example.com", test_domain)
        assert bogus_res.is_valid is False
        print(f"✓ Safety Verification: Placeholder '@example.com' strictly rejected: '{bogus_res.reason}'")

        missing_res = contactability_verifier.verify_contact_email(None, test_domain)
        assert missing_res.is_valid is False
        print(f"✓ Safety Verification: Missing email strictly rejected without guessing: '{missing_res.reason}'")

        # ----------------------------------------------------------------------
        # STEP 3: Generate Evidence-Grounded Outreach
        # ----------------------------------------------------------------------
        print_step(3, "Generate Evidence-Grounded Outreach")
        msg = await outreach_delivery_service.draft_evidence_grounded_outreach(db, lead.id)
        print(f"✓ Message #{msg.id} drafted for {msg.recipient}")
        print(f"✓ Subject: '{msg.subject}'")
        print(f"✓ Reply-To Address: {msg.reply_to}")
        print(f"✓ Evidence Grounded: Health Score {msg.evidence_used.get('overall_health_score')}/100")

        # ----------------------------------------------------------------------
        # STEP 4: Verify Message Enters PENDING_APPROVAL
        # ----------------------------------------------------------------------
        print_step(4, "Verify Message Enters PENDING_APPROVAL")
        assert msg.status == MessageStatus.PENDING_APPROVAL.value, f"Expected PENDING_APPROVAL, got {msg.status}"
        assert lead.status == LeadStatus.PENDING_APPROVAL.value, f"Expected lead in PENDING_APPROVAL, got {lead.status}"
        print(f"✓ Message Status: {msg.status}")
        print(f"✓ Lead Status: {lead.status}")

        # ----------------------------------------------------------------------
        # STEP 5: Attempt Automatic Send -> MUST FAIL
        # ----------------------------------------------------------------------
        print_step(5, "Attempt Automatic Send -> MUST FAIL (Safety Gate)")
        gate_blocked = False
        try:
            await outreach_delivery_service.send_approved_message(db, msg.id, is_operator_approved=False)
        except RuntimeError as e:
            gate_blocked = True
            print(f"✓ Safety Gate Triggered: Automated dispatch rejected: '{e}'")

        assert gate_blocked, "Safety Failure: Unapproved message was sent automatically!"
        assert msg.status == MessageStatus.PENDING_APPROVAL.value, "Message status must remain PENDING_APPROVAL"

        # ----------------------------------------------------------------------
        # STEP 6: Operator Human Approval Sign-Off
        # ----------------------------------------------------------------------
        print_step(6, "Operator Human Approval Sign-Off")
        approved_msg = await outreach_delivery_service.approve_outreach_message(db, msg.id, operator="Elena Vance")
        assert approved_msg.status == MessageStatus.APPROVED.value
        assert approved_msg.approved_at is not None
        print(f"✓ Message #{approved_msg.id} APPROVED by operator at {approved_msg.approved_at.isoformat()}")

        # ----------------------------------------------------------------------
        # STEP 7: Provider Dispatch (DRY_RUN / Mock Provider)
        # ----------------------------------------------------------------------
        print_step(7, "Email Provider Dispatch")
        send_result = await outreach_delivery_service.send_approved_message(db, approved_msg.id)
        print(f"✓ Provider Response: {send_result['status']}")
        print(f"✓ Provider Used: {send_result['provider']}")
        print(f"✓ Provider Message ID: {send_result['provider_message_id']}")

        # ----------------------------------------------------------------------
        # STEP 8: Record Successful Send Event
        # ----------------------------------------------------------------------
        print_step(8, "Record Successful Send Event & Update Status")
        await db.refresh(msg)
        await db.refresh(lead)
        assert msg.status in (MessageStatus.SENT.value, MessageStatus.MOCKED_SENT.value)
        assert msg.sent_at is not None
        assert lead.status == LeadStatus.SENT.value
        print(f"✓ Message #{msg.id} Status: {msg.status}")
        print(f"✓ Sent Timestamp: {msg.sent_at.isoformat()}")
        print(f"✓ Lead Status: {lead.status}")

        # ----------------------------------------------------------------------
        # STEP 9: Attempt Duplicate Send -> MUST BE BLOCKED
        # ----------------------------------------------------------------------
        print_step(9, "Attempt Duplicate Send -> MUST BE BLOCKED (Idempotency)")
        duplicate_blocked = False
        try:
            await outreach_delivery_service.send_approved_message(db, msg.id)
        except (ValueError, RuntimeError) as e:
            duplicate_blocked = True
            print(f"✓ Idempotency Guard Triggered: Duplicate send rejected: '{e}'")

        assert duplicate_blocked, "Safety Failure: Duplicate send was not blocked!"

        # ----------------------------------------------------------------------
        # STEP 10: Simulate Prospect Reply
        # ----------------------------------------------------------------------
        print_step(10, "Simulate Prospect Inbound Reply")
        reply_text = "Hi Elena, thanks for reaching out. We have been noticing high bounce rates on mobile. Can we review this on Thursday at 2pm?"
        reply_res = await outreach_delivery_service.handle_incoming_reply(
            session=db,
            lead_id=lead.id,
            reply_body=reply_text,
            sender_email=observed_email
        )
        print(f"✓ Inbound reply ingested: '{reply_text[:60]}...'")

        # ----------------------------------------------------------------------
        # STEP 11: Put Reply into HUMAN REVIEW (REPLY_PENDING_HUMAN_REVIEW)
        # ----------------------------------------------------------------------
        print_step(11, "Route Reply into HUMAN REVIEW (No Auto-Replies)")
        await db.refresh(lead)
        assert lead.status == LeadStatus.REPLY_PENDING_HUMAN_REVIEW.value
        print(f"✓ Lead Status: {lead.status}")
        print(f"✓ Human Review Required: {reply_res['requires_human_review']}")

        # ----------------------------------------------------------------------
        # STEP 12: Activate Human Takeover
        # ----------------------------------------------------------------------
        print_step(12, "Activate Human Takeover Lock")
        await outreach_delivery_service.activate_human_takeover(
            session=db,
            lead_id=lead.id,
            reason="High-value client requested live screenshare appointment."
        )
        await db.refresh(lead)
        assert lead.human_takeover is True
        print(f"✓ Takeover Active: {lead.human_takeover}")
        print(f"✓ Takeover Reason: '{lead.human_takeover_reason}'")
        print(f"✓ Lead Status: {lead.status}")

        # ----------------------------------------------------------------------
        # STEP 13: Verify Subsequent Automated Actions Are Blocked
        # ----------------------------------------------------------------------
        print_step(13, "Verify Automated Actions Blocked During Takeover")
        # Attempt to draft and send new automated message under active takeover
        new_msg = LocalOutreachMessage(
            lead_id=lead.id,
            channel="EMAIL",
            recipient=lead.contact_email,
            subject="Automated follow-up",
            body="Checking in...",
            status=MessageStatus.APPROVED.value,
            is_mocked=True
        )
        db.add(new_msg)
        await db.commit()
        await db.refresh(new_msg)

        takeover_blocked = False
        try:
            await outreach_delivery_service.send_approved_message(db, new_msg.id)
        except RuntimeError as e:
            takeover_blocked = True
            print(f"✓ Takeover Guard Triggered: Automated dispatch rejected: '{e}'")

        assert takeover_blocked, "Safety Failure: Automated outreach sent during active takeover!"

        # Print Complete Chronological Audit Trail
        print_step(14, "Print Lead Chronological Audit Trail")
        events_q = select(LocalLeadEvent).where(LocalLeadEvent.lead_id == lead.id).order_by(LocalLeadEvent.created_at.asc())
        events = (await db.execute(events_q)).scalars().all()
        for idx, ev in enumerate(events, 1):
            print(f"  [{idx:02d}] {ev.created_at.strftime('%H:%M:%S')} - {ev.event_type} | Payload: {ev.payload}")

        print("\n" + "=" * 80)
        print("✓ REAL OUTREACH DELIVERY DEMO LIFECYCLE COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        return True

if __name__ == "__main__":
    asyncio.run(run_outreach_lifecycle_demo())
