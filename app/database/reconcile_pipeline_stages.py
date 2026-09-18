"""Reconciliation Script for Orphaned APPROVAL Pipeline Stages.

Safely synchronizes Business.pipeline_stage for leads whose outreach messages
have already reached terminal states (SENT, REJECTED, FAILED, SEND_FAILED, OUTREACH_BLOCKED),
ensuring only genuinely pending outreach messages populate the APPROVAL stage.
"""

import asyncio
import logging
from sqlalchemy import select
from app.database.connection import AsyncSessionLocal
from app.database.models import Business, OutreachMessage, OutreachStatus, PipelineStage, PipelineEvent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reconcile_pipeline")


async def reconcile():
    async with AsyncSessionLocal() as session:
        q = select(Business).where(Business.pipeline_stage == PipelineStage.APPROVAL.value)
        businesses = (await session.execute(q)).scalars().all()
        logger.info(f"Found {len(businesses)} businesses currently marked as APPROVAL.")

        reconciled_count = 0

        for biz in businesses:
            mq = select(OutreachMessage).where(OutreachMessage.business_id == biz.id)
            msgs = (await session.execute(mq)).scalars().all()

            if not msgs:
                # No messages at all -> reset to QUALIFIED
                old_stage = biz.pipeline_stage
                biz.pipeline_stage = PipelineStage.QUALIFIED.value
                session.add(PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=PipelineStage.QUALIFIED.value,
                    deal_value=0.0,
                    note="Reconciled from APPROVAL: No outreach draft found, reset to QUALIFIED."
                ))
                reconciled_count += 1
                logger.info(f"Biz #{biz.id} ({biz.domain}) -> QUALIFIED (no messages)")
                continue

            # Check if any message is actively pending approval or queued
            has_pending = any(m.status in (OutreachStatus.PENDING_APPROVAL.value, OutreachStatus.OUTREACH_QUEUED.value) for m in msgs)
            if has_pending:
                # Genuinely pending approval - keep in APPROVAL stage
                logger.info(f"Biz #{biz.id} ({biz.domain}) -> KEPT in APPROVAL (active draft pending)")
                continue

            # Check if any message was SENT
            has_sent = any(m.status == OutreachStatus.SENT.value for m in msgs)
            if has_sent:
                old_stage = biz.pipeline_stage
                biz.pipeline_stage = PipelineStage.CONTACTED.value
                session.add(PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=PipelineStage.CONTACTED.value,
                    deal_value=0.0,
                    note="Reconciled from APPROVAL: Outreach message was already dispatched (SENT)."
                ))
                reconciled_count += 1
                logger.info(f"Biz #{biz.id} ({biz.domain}) -> CONTACTED (sent message present)")
                continue

            # Check if all messages were REJECTED
            all_rejected = all(m.status == OutreachStatus.REJECTED.value for m in msgs)
            if all_rejected:
                old_stage = biz.pipeline_stage
                biz.pipeline_stage = PipelineStage.REJECTED.value
                session.add(PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=PipelineStage.REJECTED.value,
                    deal_value=0.0,
                    note="Reconciled from APPROVAL: Outreach message was rejected by operator."
                ))
                reconciled_count += 1
                logger.info(f"Biz #{biz.id} ({biz.domain}) -> REJECTED (all messages rejected)")
                continue

            # All messages failed or blocked
            all_failed = all(m.status in (
                OutreachStatus.FAILED.value,
                OutreachStatus.SEND_FAILED.value,
                OutreachStatus.OUTREACH_BLOCKED.value,
                OutreachStatus.OUTBOUND_BLOCKED.value
            ) for m in msgs)
            if all_failed:
                old_stage = biz.pipeline_stage
                biz.pipeline_stage = PipelineStage.LOST.value
                session.add(PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=PipelineStage.LOST.value,
                    deal_value=0.0,
                    note="Reconciled from APPROVAL: Outreach delivery failed or was blocked."
                ))
                reconciled_count += 1
                logger.info(f"Biz #{biz.id} ({biz.domain}) -> LOST (all messages failed)")
                continue

        await session.commit()
        logger.info(f"Reconciliation complete: {reconciled_count} businesses updated out of {len(businesses)}.")


if __name__ == "__main__":
    asyncio.run(reconcile())
