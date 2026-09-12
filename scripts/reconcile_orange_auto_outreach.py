"""
Explicit, auditable reconciliation script for Orange Auto outreach message (id=12).
Target: Business ID 30, OutreachMessage ID 12.

Safety Invariants:
- Status remains PENDING_APPROVAL
- approved_at is set to NULL
- sent_at remains NULL
- provider_message_id remains NULL
- Inserts an auditable PipelineEvent documenting reconciliation
- Zero emails sent, zero approvals granted
"""
import os
import sys
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("reconciliation")

async def run_reconciliation():
    os.chdir("/opt/agency")
    sys.path.insert(0, "/opt/agency")

    from app.database.connection import AsyncSessionLocal
    from app.database.models import OutreachMessage, OutreachStatus, PipelineEvent, PipelineStage, Business

    async with AsyncSessionLocal() as session:
        # 1. Pre-condition checks
        msg = await session.get(OutreachMessage, 12)
        if not msg:
            logger.error("FATAL: OutreachMessage id=12 not found in database!")
            sys.exit(1)

        logger.info("=== PRE-RECONCILIATION STATE (outreach_messages.id=12) ===")
        logger.info(f"  ID:                  {msg.id}")
        logger.info(f"  Business ID:         {msg.business_id}")
        logger.info(f"  Status:              {msg.status}")
        logger.info(f"  Approved At:         {msg.approved_at}")
        logger.info(f"  Sent At:             {msg.sent_at}")
        logger.info(f"  Provider Msg ID:     {getattr(msg, 'provider_message_id', None)}")

        if msg.business_id != 30:
            logger.error(f"FATAL: Expected business_id=30, got {msg.business_id}")
            sys.exit(1)

        if msg.status != OutreachStatus.PENDING_APPROVAL.value:
            logger.error(f"FATAL: Expected status=PENDING_APPROVAL, got {msg.status}")
            sys.exit(1)

        if msg.sent_at is not None:
            logger.error(f"FATAL: Expected sent_at=None, got {msg.sent_at}")
            sys.exit(1)

        if getattr(msg, "provider_message_id", None) is not None:
            logger.error(f"FATAL: Expected provider_message_id=None, got {msg.provider_message_id}")
            sys.exit(1)

        # 2. Atomic Reconciliation Update
        logger.info("Executing atomic reconciliation: resetting approved_at to NULL...")
        msg.approved_at = None
        msg.status = OutreachStatus.PENDING_APPROVAL.value

        # 3. Create Audit PipelineEvent
        biz = await session.get(Business, msg.business_id)
        current_stage = biz.pipeline_stage if biz else PipelineStage.APPROVAL.value
        note = (
            "Reconciliation executed via auditable script: cleared stale approved_at timestamp. "
            "Draft status confirmed as PENDING_APPROVAL. Awaiting explicit operator authorization."
        )
        event = PipelineEvent(
            business_id=30,
            from_stage=current_stage,
            to_stage=PipelineStage.APPROVAL.value,
            deal_value=0.0,
            note=note
        )
        session.add(event)
        await session.commit()

        # 4. Post-condition verification
        await session.refresh(msg)
        logger.info("=== POST-RECONCILIATION STATE (outreach_messages.id=12) ===")
        logger.info(f"  ID:                  {msg.id}")
        logger.info(f"  Business ID:         {msg.business_id}")
        logger.info(f"  Status:              {msg.status}")
        logger.info(f"  Approved At:         {msg.approved_at}")
        logger.info(f"  Sent At:             {msg.sent_at}")
        logger.info(f"  Provider Msg ID:     {getattr(msg, 'provider_message_id', None)}")

        assert msg.id == 12, "ID mismatch"
        assert msg.business_id == 30, "Business ID mismatch"
        assert msg.status == OutreachStatus.PENDING_APPROVAL.value, "Status must remain PENDING_APPROVAL"
        assert msg.approved_at is None, "approved_at must be None (NULL)"
        assert msg.sent_at is None, "sent_at must remain None (NULL)"
        assert getattr(msg, "provider_message_id", None) is None, "provider_message_id must remain None (NULL)"

        logger.info("SUCCESS: Message #12 reconciled safely with zero sends and zero approvals.")

if __name__ == "__main__":
    asyncio.run(run_reconciliation())
