"""
Unified Conversation Event Normalizer & Ingestion Engine.

Ingests events and status webhooks across Email, WhatsApp, and Voice.
Enforces:
1. Canonical schema normalization (ConversationEvent).
2. Strict idempotency and deduplication via (provider, idempotency_key).
3. Cross-channel CRM timeline persistence.
4. Intent classification triggers for incoming responses.
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.models import (
    ConversationEvent,
    Business,
    ChannelType,
    EventDirection,
    ConversationEventType,
    PipelineStage,
    PipelineEvent
)
from app.core.logging import logger
from app.crm.reply_classifier import reply_classifier


class ConversationNormalizer:
    """
    Normalizes multi-channel events and manages idempotent CRM persistence.
    """

    async def ingest_event(
        self,
        session: AsyncSession,
        business_id: int,
        normalized_payload: Dict[str, Any]
    ) -> ConversationEvent:
        """
        Ingests a normalized event payload into the database idempotently.
        If an event with the same provider and idempotency_key exists, returns it directly.
        """
        provider = normalized_payload.get("provider", "unknown")
        idempotency_key = normalized_payload.get("idempotency_key")

        # 1. Idempotency check
        if idempotency_key:
            stmt = select(ConversationEvent).where(
                ConversationEvent.provider == provider,
                ConversationEvent.idempotency_key == idempotency_key
            )
            existing = (await session.execute(stmt)).scalars().first()
            if existing:
                logger.info(
                    f"[Normalizer] Deduplicated event: provider={provider}, key={idempotency_key} "
                    f"(Event #{existing.id} already exists)."
                )
                return existing

        # 2. Construct new ConversationEvent
        channel = normalized_payload.get("channel", ChannelType.EMAIL.value)
        direction = normalized_payload.get("direction", EventDirection.OUTBOUND.value)
        event_type = normalized_payload.get("event_type", ConversationEventType.SENT.value)
        content = normalized_payload.get("content", "")
        provider_event_id = normalized_payload.get("provider_event_id")
        metadata_json = normalized_payload.get("metadata_json", {})

        event = ConversationEvent(
            business_id=business_id,
            channel=channel,
            direction=direction,
            provider=provider,
            provider_event_id=provider_event_id,
            event_type=event_type,
            content=content,
            metadata_json=metadata_json,
            idempotency_key=idempotency_key,
            created_at=datetime.utcnow()
        )
        session.add(event)
        await session.flush()

        # 3. Handle Inbound Responses & Intent Classification
        if direction == EventDirection.INBOUND.value and content:
            await self._handle_inbound_interaction(session, event, business_id, content)

        await session.commit()
        await session.refresh(event)
        return event

    async def _handle_inbound_interaction(
        self,
        session: AsyncSession,
        event: ConversationEvent,
        business_id: int,
        content: str
    ):
        """
        Classifies incoming interaction text across channels and updates CRM state.
        """
        try:
            classification_data = await reply_classifier.classify_text(content)
            cat = classification_data.get("classification", "UNKNOWN")
            conf = classification_data.get("confidence", 0.0)
            reason = classification_data.get("reasoning", "")
            suggested = classification_data.get("suggested_response", "")

            # Attach classification to event metadata
            event.metadata_json = dict(event.metadata_json or {})
            event.metadata_json.update({
                "classification": cat,
                "confidence": conf,
                "classification_reason": reason,
                "suggested_response": suggested,
                "classified_at": datetime.utcnow().isoformat()
            })

            biz = await session.get(Business, business_id)
            if not biz:
                return

            # Advance CRM stage or trigger Demo Factory for positive responses
            is_positive = cat in ("POSITIVE", "INTERESTED", "MEETING_REQUEST", "PRICE_REQUEST")
            old_stage = biz.pipeline_stage

            if is_positive:
                biz.pipeline_stage = PipelineStage.QUALIFIED_REPLY.value
                pipe_evt = PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=biz.pipeline_stage,
                    deal_value=0.0,
                    note=f"[{event.channel}] Positive response received ({conf*100:.0f}% conf): {content[:100]}"
                )
                session.add(pipe_evt)

                # Autonomous demo generation for positive replies
                try:
                    from app.acquisition.autonomous_controller import autonomous_acquisition_controller
                    await autonomous_acquisition_controller._step_process_reply(
                        session=session,
                        business_id=biz.id,
                        reply_category=cat,
                        reply_body=content
                    )
                except Exception as demo_err:
                    logger.error(f"[Normalizer] Demo trigger error for biz {biz.id}: {demo_err}")

            elif cat in ("UNSUBSCRIBE", "NOT_INTERESTED", "NEGATIVE"):
                biz.pipeline_stage = PipelineStage.LOST.value
                pipe_evt = PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=biz.pipeline_stage,
                    deal_value=0.0,
                    note=f"[{event.channel}] Opt-out / negative response received: {content[:100]}"
                )
                session.add(pipe_evt)

            elif cat == "QUESTION":
                biz.pipeline_stage = PipelineStage.REPLIED.value
                pipe_evt = PipelineEvent(
                    business_id=biz.id,
                    from_stage=old_stage,
                    to_stage=biz.pipeline_stage,
                    deal_value=0.0,
                    note=f"[{event.channel}] Question received. Drafted suggested reply for operator review."
                )
                session.add(pipe_evt)

        except Exception as e:
            logger.error(f"[Normalizer] Error processing inbound interaction for biz {business_id}: {e}")


# Global singleton instance
conversation_normalizer = ConversationNormalizer()
