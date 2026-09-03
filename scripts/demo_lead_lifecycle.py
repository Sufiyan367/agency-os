"""
Standalone End-to-End Local Demo Script:
Demonstrates the complete 12-step AI Lead Recovery & Outreach Lifecycle.
Runs 100% locally with zero external API fees or real email sending.
"""

import sys
import os
import asyncio
from datetime import datetime, timedelta

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database.connection import AsyncSessionLocal, init_db
from app.models.entities import (
    Business, Lead, Audit, OutreachMessage, FollowupSchedule, LeadEvent,
    EventType, LeadStatus, FollowupStatus, MessageStatus
)
from app.services.qualification import QualificationService
from app.services.outreach import OutreachService
from app.services.followup_engine import FollowUpEngine
from app.services.notification import LocalNotificationService
from config.demo_business import get_demo_business

def print_step(step_num: int, title: str):
    print(f"\n{'='*75}")
    print(f"STEP {step_num}: {title.upper()}")
    print(f"{'='*75}")

async def run_lifecycle_demo():
    print("\n" + "#"*75)
    print("  LOCAL-FIRST AI LEAD RECOVERY & OUTREACH AUTOMATION DEMO")
    print("  Target: Small US Local Businesses • Zero External Cloud Costs")
    print("#"*75)

    # Initialize schema
    await init_db()

    async with AsyncSessionLocal() as db:
        demo_cfg = get_demo_business()

        # ----------------------------------------------------------------------
        # STEP 1: Create Demo Business
        # ----------------------------------------------------------------------
        print_step(1, "Create Demo Business")
        domain = "apexcomfortair.example.com"
        res = await db.execute(select(Business).where(Business.domain == domain))
        biz = res.scalar_one_or_none()
        if not biz:
            biz = Business(
                name=demo_cfg.name,
                domain=domain,
                website_url=demo_cfg.website,
                niche=demo_cfg.industry,
                city="Austin",
                state="TX",
                country="US",
                email=demo_cfg.email,
                phone=demo_cfg.phone
            )
            db.add(biz)
            await db.commit()
            await db.refresh(biz)
        print(f"✓ Business record active: ID {biz.id} | {biz.name} | {biz.city}, {biz.state}")

        # ----------------------------------------------------------------------
        # STEP 2: Create Inbound Lead
        # ----------------------------------------------------------------------
        print_step(2, "Create Inbound Lead")
        contact_email = f"marcus.vance@austinhomes.example.com"
        lead_res = await db.execute(select(Lead).where(Lead.contact_email == contact_email))
        lead = lead_res.scalar_one_or_none()
        if not lead:
            lead = Lead(
                business_id=biz.id,
                contact_name="Marcus Vance",
                contact_email=contact_email,
                contact_phone="+1 (512) 555-8821",
                status=LeadStatus.NEW.value,
                human_takeover=False,
                human_takeover_reason=None
            )
            db.add(lead)
            await db.commit()
            await db.refresh(lead)

            event = LeadEvent(
                lead_id=lead.id,
                event_type=EventType.LEAD_DISCOVERED.value,
                payload={"contact_name": lead.contact_name, "contact_email": lead.contact_email}
            )
            db.add(event)
            await db.commit()
        else:
            # Clean fixture reset for repeatable demo execution
            lead.human_takeover = False
            lead.human_takeover_reason = None
            lead.status = LeadStatus.NEW.value
            await db.commit()
            await db.refresh(lead)

        assert lead.human_takeover is False, "Safety Check: Human takeover must NOT be active before Step 6!"
        print(f"✓ Lead captured: ID {lead.id} | {lead.contact_name} <{lead.contact_email}> | Status: {lead.status}")
        print(f"✓ Human Takeover Guard Status: STANDBY (False) - Automated flow permitted")

        # ----------------------------------------------------------------------
        # STEP 3: Execute Technical Website Audit
        # ----------------------------------------------------------------------
        print_step(3, "Execute Technical Website Diagnostic Audit")
        audit_res = await db.execute(select(Audit).where(Audit.business_id == biz.id))
        audit = audit_res.scalar_one_or_none()
        if not audit:
            audit = Audit(
                business_id=biz.id,
                url_audited=biz.website_url,
                overall_health_score=38.0,
                performance_score=32.0,
                seo_score=42.0,
                accessibility_score=55.0,
                security_score=70.0,
                mobile_responsive=False,
                findings=[
                    {
                        "category": "PERFORMANCE",
                        "severity": "CRITICAL",
                        "finding": "Mobile Largest Contentful Paint exceeds 5.2 seconds on 4G cellular",
                        "evidence": "Hero compressor graphic uncompressed (3.4 MB)"
                    },
                    {
                        "category": "SEO",
                        "severity": "HIGH",
                        "finding": "Missing HVAC local business schema markup",
                        "evidence": "Google Rich Results validator returns zero structured entities"
                    },
                    {
                        "category": "MOBILE",
                        "severity": "HIGH",
                        "finding": "Tap targets overlap on mobile viewport",
                        "evidence": "Click-to-call button obscured by floating cookie banner"
                    }
                ],
                summary="Significant digital customer drop-off detected on mobile devices."
            )
            db.add(audit)
            await db.commit()
            await db.refresh(audit)
        print(f"✓ Diagnostic Audit complete: Health: {audit.overall_health_score}/100 | Speed: {audit.performance_score}/100")
        for f in audit.findings:
            print(f"  • [{f['category']}] {f['finding']}")

        # ----------------------------------------------------------------------
        # STEP 4: AI Qualification & Scoring
        # ----------------------------------------------------------------------
        print_step(4, "AI Qualification & Scoring")
        qual_svc = QualificationService()
        qual_res = await qual_svc.qualify_lead_record(db, lead.id)
        print(f"✓ Opportunity Score:    {qual_res.lead_score:.1f}/100")
        print(f"✓ Qualification Tier:   {qual_res.qualification} (Intent: {qual_res.intent_level})")
        print(f"✓ Recommended Service:  {qual_res.recommended_service}")
        print(f"✓ Analytical Rationale: {qual_res.reasoning}")

        # ----------------------------------------------------------------------
        # STEP 5: Generate Outreach Copy
        # ----------------------------------------------------------------------
        print_step(5, "Generate Evidence-Grounded Outreach Copy")
        outreach_svc = OutreachService()
        msg = await outreach_svc.draft_outreach_for_lead(db, lead.id)
        assert msg.status == MessageStatus.PENDING_APPROVAL.value
        assert lead.human_takeover is False, "Takeover must remain inactive while drafting."
        print(f"✓ Outreach Drafted (ID: {msg.id}):")
        print(f"  To:      {msg.recipient}")
        print(f"  Subject: {msg.subject}")
        print(f"  Status:  {msg.status} (Human Sign-Off Mandatory)")
        print(f"  Body Preview:\n{msg.body[:220]}...")

        # ----------------------------------------------------------------------
        # STEP 6: Human Approval
        # ----------------------------------------------------------------------
        print_step(6, "Human Approval Gate")
        assert lead.human_takeover is False, "Human takeover must NOT be active before Step 6!"
        print(f"✓ Operator reviews outreach draft for {lead.contact_name}.")
        print(f"✓ Explicit human approval granted for message ID {msg.id}.")

        # ----------------------------------------------------------------------
        # STEP 7: Successfully Send & Record Approved Outreach Event
        # ----------------------------------------------------------------------
        print_step(7, "Successfully Send & Record Approved Outreach Event")
        sent_msg = await outreach_svc.approve_and_send(db, msg.id)
        assert sent_msg.status in (MessageStatus.MOCKED_SENT.value, MessageStatus.SENT.value)
        assert lead.status == LeadStatus.CONTACTED.value
        print(f"✓ Outreach succeeded before takeover: Message ID {sent_msg.id} marked {sent_msg.status}.")
        print(f"✓ Lead status advanced to: {lead.status}")

        # ----------------------------------------------------------------------
        # STEP 8: Schedule Automated Follow-Up Sequence
        # ----------------------------------------------------------------------
        print_step(8, "Schedule Automated Follow-Up Cadence")
        engine = FollowUpEngine(time_compression_factor=86400.0) # 1 day = 1 second
        now = datetime.utcnow()
        await engine.cancel_followups_for_lead(db, lead.id, reason="Demo sequence reset")
        schedules = await engine.schedule_sequence_for_lead(db, lead.id, base_time=now)
        assert len(schedules) == 3
        print(f"✓ Scheduled {len(schedules)} follow-up touchpoints:")
        for s in schedules:
            print(f"  • Step {s.step_number}: '{s.subject}' scheduled for {s.scheduled_for.isoformat()}Z")

        # ----------------------------------------------------------------------
        # STEP 9: Process Compressed-Time Follow-Up
        # ----------------------------------------------------------------------
        print_step(9, "Process Compressed-Time Follow-Up Dispatch")
        simulated_future = now + timedelta(days=3)
        executed = await engine.process_due_followups(db, now=simulated_future)
        assert len(executed) > 0, "Expected follow-ups to execute prior to takeover!"
        print(f"✓ Time advanced 3 simulated days. Processed {len(executed)} due follow-up(s):")
        for ex in executed:
            print(f"  • Step {ex.step_number} sent to {lead.contact_email} (Status: {ex.status})")

        # ----------------------------------------------------------------------
        # STEP 10: Dispatch Local Owner Notification
        # ----------------------------------------------------------------------
        print_step(10, "Dispatch Local Owner Notification")
        notifier = LocalNotificationService()
        await notifier.notify_owner_new_qualified_lead(db, lead, audit=audit, outreach=sent_msg)
        print("✓ Local owner banner dispatched to console and logged in audit trail.")

        # ----------------------------------------------------------------------
        # STEP 11: Trigger Human Takeover
        # ----------------------------------------------------------------------
        print_step(11, "Trigger Human Takeover / Pause Automation Switch")
        lead.human_takeover = True
        lead.human_takeover_reason = "Customer requested live phone discussion regarding pricing."
        lead.status = LeadStatus.HUMAN_TAKEOVER.value
        cancelled_count = await engine.cancel_followups_for_lead(
            db, lead.id, reason=f"Takeover: {lead.human_takeover_reason}"
        )
        event = LeadEvent(
            lead_id=lead.id,
            event_type=EventType.HUMAN_TAKEOVER_ENABLED.value,
            payload={"reason": lead.human_takeover_reason, "cancelled_followups": cancelled_count}
        )
        db.add(event)
        await db.commit()
        await db.refresh(lead)

        assert lead.human_takeover is True, "Assertion Error: Takeover must be active at Step 11!"
        print(f"✓ Takeover became ACTIVE at the intended step for Lead {lead.id}.")
        print(f"✓ Automatically cancelled {cancelled_count} pending automated follow-ups.")

        # ----------------------------------------------------------------------
        # STEP 12: Verify Subsequent Automated Actions Are Blocked
        # ----------------------------------------------------------------------
        print_step(12, "Verify Subsequent Automated Actions Blocked Under Human Takeover")

        # 1. Verify follow-up automation respects human takeover
        future_day_10 = now + timedelta(days=10)
        due_after_takeover = await engine.process_due_followups(db, now=future_day_10)
        assert len(due_after_takeover) == 0, "Error: Follow-ups executed during active human takeover!"
        print(f"✓ Follow-up automation respects human takeover (Processed: {len(due_after_takeover)} due follow-ups).")

        # 2. Verify subsequent automated outreach is rejected by production guardrail
        new_msg = await outreach_svc.draft_outreach_for_lead(db, lead.id)
        outreach_blocked = False
        try:
            await outreach_svc.approve_and_send(db, new_msg.id)
        except RuntimeError as e:
            outreach_blocked = True
            assert "Human takeover is ACTIVE" in str(e)
            print(f"✓ Subsequent automated outreach rejected by guardrail: '{e}'")

        assert outreach_blocked, "Safety Failure: approve_and_send() did not block outreach during active takeover!"

        # 3. Print Final Lead Lifecycle Audit Trail
        events_res = await db.execute(
            select(LeadEvent).where(LeadEvent.lead_id == lead.id).order_by(LeadEvent.created_at.asc())
        )
        all_events = events_res.scalars().all()

        print(f"\nTIMELINE AUDIT TRAIL FOR LEAD #{lead.id} ({lead.contact_name}):")
        print("-" * 75)
        for e in all_events:
            print(f"[{e.created_at.strftime('%H:%M:%S')}] {e.event_type:<25} -> {e.payload}")
        print("-" * 75)
        print(f"Final Lead Status: {lead.status} | Human Takeover: {lead.human_takeover}")

    print("\n" + "#"*75)
    print("  ✓ ALL 12 LIFECYCLE STEPS COMPLETED & VERIFIED SUCCESSFULLY!")
    print("#"*75 + "\n")

if __name__ == "__main__":
    asyncio.run(run_lifecycle_demo())
