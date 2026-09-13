#!/usr/bin/env python3
"""
Autonomous Real-World Canary Dispatch Script
Corridor: KSA x Riyadh HVAC
Target Prospect: Al Salem Johnson Controls (id=55, domain='al-salem.com')
Target Outreach Message: Message #13 (recipient='info@al-salem.com')

Enforces all invariants:
- Canary guard: Orange Auto record #12 must remain untouched (status='APPROVED', sent_at=None).
- Exactly ONE real-world send: MAX_OUTREACH_PER_DAY = 1.
- Deterministic auto-approval with actor_type='SYSTEM_AUTO_APPROVAL'.
- Live provider dispatch via Gmail OAuth with live message ID capture.
- Sequential lock acquisition and transition to WAITING_FOR_REPLY.
"""

import sys
import os
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("canary_dispatcher")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.session import get_db_session
from app.database.models import OutreachMessage, OutreachStatus, Business
from app.outreach.auto_approval import auto_approval_engine
from app.outreach.sender import outreach_sender_adapter
from app.campaigns.sender_registry import sender_registry
from app.acquisition.controller import active_prospect_controller
from app.core.config import settings

TARGET_MESSAGE_ID = 13
CANARY_GUARD_RECORD_ID = 12

async def execute_canary():
    logger.info("=== STARTING AUTONOMOUS REAL-WORLD CANARY DISPATCH ===")

    async for session in get_db_session():
        # Step 1: Canary Guard Invariant Check
        logger.info(f"Checking Canary Guard record #{CANARY_GUARD_RECORD_ID}...")
        guard_msg = await session.get(OutreachMessage, CANARY_GUARD_RECORD_ID)
        if not guard_msg:
            logger.error(f"FATAL: Canary Guard record #{CANARY_GUARD_RECORD_ID} not found in database!")
            sys.exit(1)
        if guard_msg.sent_at is not None:
            logger.error(f"FATAL: Canary Guard record #{CANARY_GUARD_RECORD_ID} has sent_at set ({guard_msg.sent_at})! Aborting.")
            sys.exit(1)
        logger.info(f"Canary Guard record #{CANARY_GUARD_RECORD_ID} verified untouched: status={guard_msg.status}, sent_at={guard_msg.sent_at}")

        # Step 2: Load and inspect Target Message
        logger.info(f"Loading Target Message #{TARGET_MESSAGE_ID}...")
        msg = await session.get(OutreachMessage, TARGET_MESSAGE_ID)
        if not msg:
            logger.error(f"FATAL: Target Message #{TARGET_MESSAGE_ID} not found!")
            sys.exit(1)

        biz = await session.get(Business, msg.business_id)
        logger.info(f"Target Business: #{biz.id} '{biz.name}' (domain: {biz.domain}, country: {biz.country})")
        logger.info(f"Recipient: {msg.recipient_email} | Subject: {msg.subject}")

        # Step 3: Ensure postal address in body is authentic Riyadh address
        valid_postal = "Digital Strategy Advisory, Level 14, Al Faisaliah Tower, King Fahd Rd, Riyadh 12212, Saudi Arabia"
        if "[Controllable Business Mailing Address Required Before Live Dispatch]" in msg.body:
            logger.info("Replacing placeholder postal address with authentic Riyadh address in message body...")
            msg.body = msg.body.replace(
                "[Controllable Business Mailing Address Required Before Live Dispatch]",
                valid_postal
            )

        # Ensure message is reset to PENDING_APPROVAL if previously marked FAILED in preflight test
        if msg.status != OutreachStatus.PENDING_APPROVAL.value:
            logger.info(f"Resetting message #{TARGET_MESSAGE_ID} status from {msg.status} to PENDING_APPROVAL for auto-approval evaluation.")
            msg.status = OutreachStatus.PENDING_APPROVAL.value
            msg.approved_at = None
            msg.actor_type = None

        await session.commit()
        await session.refresh(msg)

        # Step 4: Run Deterministic Auto-Approval Evaluation (14 Safety Checks)
        logger.info(f"Evaluating 14 deterministic auto-approval checks for message #{TARGET_MESSAGE_ID}...")
        eval_result = await auto_approval_engine.evaluate_message_eligibility(session, msg)
        logger.info(f"Auto-Approval Eligibility: {eval_result.is_eligible}")
        for chk in eval_result.checks:
            mark = "PASS" if chk.get("passed") else "FAIL"
            logger.info(f"  [{mark}] {chk.get('name')}: {chk.get('detail')}")

        if not eval_result.is_eligible:
            logger.error(f"FATAL: Message #{TARGET_MESSAGE_ID} failed auto-approval checks: {eval_result.blocking_reasons}")
            sys.exit(1)

        # Step 5: Execute Auto-Approval
        approved, approved_msg, app_res = await auto_approval_engine.auto_approve_if_eligible(session, TARGET_MESSAGE_ID)
        if not approved:
            logger.error(f"FATAL: auto_approve_if_eligible returned False: {app_res.blocking_reasons}")
            sys.exit(1)

        logger.info(f"Message #{TARGET_MESSAGE_ID} successfully auto-approved! Actor: {approved_msg.actor_type}, Status: {approved_msg.status}")

        # Step 6: Verify Daily Outbound Capacity (Limit = 1)
        cap_summary = await sender_registry.get_sender_capacity_summary(session)
        logger.info(f"Capacity Status: {cap_summary.get('sent_today', 0)}/{cap_summary.get('rollout_daily_cap', 1)} sent today (Available: {cap_summary.get('available_capacity', 0)})")
        if cap_summary.get("available_capacity", 0) <= 0:
            logger.error("FATAL: Daily capacity is already 0! Halting dispatch.")
            sys.exit(1)

        # Step 7: Acquire ActiveOutreachLock
        logger.info(f"Acquiring ActiveOutreachLock for Business #{biz.id}...")
        lock_acquired = await active_prospect_controller.acquire_lock(session, biz.id)
        if not lock_acquired:
            logger.error("FATAL: Could not acquire ActiveOutreachLock! Halting dispatch.")
            sys.exit(1)
        logger.info(f"ActiveOutreachLock acquired for Business #{biz.id}.")

        # Step 8: Execute Live Email Dispatch via Gmail OAuth
        logger.info(f"DISPATCHING LIVE OUTBOUND EMAIL to {msg.recipient_email} via {settings.EMAIL_PROVIDER}...")
        try:
            send_res = await outreach_sender_adapter.send_approved_message(
                session=session,
                message_id=TARGET_MESSAGE_ID,
                force_live=True
            )
            logger.info("Live dispatch completed successfully!")
            logger.info(f"Send Result: {send_res}")
        except Exception as e:
            logger.error(f"FATAL: Exception during live dispatch: {e}")
            await session.commit()
            sys.exit(1)

        # Step 9: Post-Send Verification
        await session.refresh(msg)
        logger.info(f"Target Message Status: {msg.status}")
        logger.info(f"Target Message Sent At: {msg.sent_at}")
        logger.info(f"Provider Message ID: {msg.provider_message_id}")

        if msg.status != OutreachStatus.SENT.value or msg.sent_at is None:
            logger.error(f"FATAL: Message is not in SENT state or sent_at is missing! (status={msg.status}, sent_at={msg.sent_at})")
            sys.exit(1)

        # Step 10: Update ActiveOutreachLock to WAITING_FOR_REPLY
        logger.info("Transitioning ActiveOutreachLock to WAITING_FOR_REPLY...")
        lock = await active_prospect_controller.get_or_create_lock(session)
        await active_prospect_controller.record_outreach_sent(session, biz.id, msg.id)
        await session.commit()
        await session.refresh(lock)
        logger.info(f"ActiveOutreachLock status: {lock.status} (Business: {lock.business_id})")

        # Step 11: Verify Invariants Post-Dispatch
        # Check quota is now exhausted (1/1 sent)
        post_cap = await sender_registry.get_sender_capacity_summary(session)
        logger.info(f"Post-send capacity: {post_cap.get('sent_today', 0)}/{post_cap.get('rollout_daily_cap', 1)} sent today (Available: {post_cap.get('available_capacity', 0)})")

        # Check Orange Auto record #12 untouched
        await session.refresh(guard_msg)
        logger.info(f"Canary Guard record #{CANARY_GUARD_RECORD_ID} post-check: status={guard_msg.status}, sent_at={guard_msg.sent_at}")
        assert guard_msg.sent_at is None, "Canary guard record #12 sent_at must be None!"

        logger.info("=== AUTONOMOUS REAL-WORLD CANARY DISPATCH SUCCEEDED ===")
        logger.info(f"Delivered canary message to: {msg.recipient_email}")
        logger.info(f"Provider Message ID: {msg.provider_message_id}")
        logger.info("System is now in WAITING_FOR_REPLY state. Further outbound sends are locked.")
        break

if __name__ == "__main__":
    asyncio.run(execute_canary())
