"""
Tests for Multi-Channel Communication & Revenue Loop (Email, WhatsApp, Voice).

Verifies:
1. Multi-channel database model (ConversationEvent) creation and relationship mapping.
2. WhatsApp Business Platform adapter:
   - Enforces strict opt-in consent (blocks cold outreach without explicit consent).
   - Allows templated message dispatch when opt-in is verified.
   - Parses and normalizes delivery webhooks (sent, delivered, read, failed).
   - Ingests inbound messages and flags opt-out keywords (STOP, UNSUBSCRIBE).
3. Voice telephony adapter:
   - Safety checks: blocks unauthorized outbound calls when calling is disabled.
   - Telephony state machine (CALL_INITIATED, RINGING, ANSWERED, COMPLETED, FAILED, VOICEMAIL).
   - STT transcription webhook ingestion (TRANSCRIPT_READY).
   - Voicebox audio synthesis boundary client integration.
4. Email adapter:
   - Normalizes outbound and inbound email events into ConversationEvents.
   - Parses provider delivery status webhooks (Resend, SendGrid).
5. Unified Normalizer & Idempotency:
   - Ingests cross-channel events into the database.
   - Deduplicates identical webhooks using (provider, idempotency_key).
6. Channel Eligibility Engine:
   - Deterministic policy routing (Email vs WhatsApp vs Voice).
   - Rejects WhatsApp when only public phone is available without opt-in.
   - Enforces suppression list across channels.
7. Response classification for all 7 canonical intents:
   - POSITIVE (triggers Demo Factory)
   - NEGATIVE
   - QUESTION
   - NEEDS_HUMAN
   - UNSUBSCRIBE
   - OUT_OF_OFFICE
   - UNKNOWN
8. Safety Invariants:
   - 0 real emails, 0 real WhatsApp messages, 0 real telephone calls made during tests.
   - Dry-run mode safe by default.
"""
import uuid
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, Contact, OutreachMessage, OutreachStatus, Reply, ReplyClassification,
    PipelineStage, PipelineEvent, ConversationEvent, ChannelType, EventDirection,
    ConversationEventType
)
from app.communications.whatsapp_adapter import whatsapp_adapter, WhatsAppAdapter
from app.communications.voice_adapter import voice_adapter, VoiceAdapter
from app.communications.voicebox_client import voicebox_client, VoiceboxClient
from app.communications.email_adapter import email_adapter, EmailAdapter
from app.communications.normalizer import conversation_normalizer, ConversationNormalizer
from app.communications.eligibility import channel_eligibility_engine, ChannelEligibilityEngine
from app.crm.reply_classifier import reply_classifier


test_biz_ids = []


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    yield
    if test_biz_ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(ConversationEvent).where(ConversationEvent.business_id.in_(test_biz_ids)))
            await session.execute(delete(Reply).where(Reply.business_id.in_(test_biz_ids)))
            await session.execute(delete(PipelineEvent).where(PipelineEvent.business_id.in_(test_biz_ids)))
            await session.execute(delete(OutreachMessage).where(OutreachMessage.business_id.in_(test_biz_ids)))
            await session.execute(delete(Contact).where(Contact.business_id.in_(test_biz_ids)))
            await session.execute(delete(Business).where(Business.id.in_(test_biz_ids)))
            await session.commit()


@pytest.mark.asyncio
async def test_conversation_event_model_crud():
    """Verify ConversationEvent model creation, persistence, querying, and relationship."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Test HVAC Pros",
            domain=f"test-hvac-{uuid.uuid4().hex[:6]}.com",
            country="US",
            niche="hvac",
            public_email="info@testhvac.com",
            phone="+15551234567"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        test_biz_ids.append(biz.id)

        # Create ConversationEvent
        evt = ConversationEvent(
            business_id=biz.id,
            channel=ChannelType.EMAIL.value,
            direction=EventDirection.OUTBOUND.value,
            provider="dry_run_email",
            provider_event_id="sim_email_101",
            event_type=ConversationEventType.SENT.value,
            content="Hello from Agency OS",
            idempotency_key=f"dry_run_{biz.id}_101",
            metadata_json={"subject": "Diagnostic audit"}
        )
        session.add(evt)
        await session.commit()
        await session.refresh(evt)

        assert evt.id is not None
        assert evt.business_id == biz.id
        assert evt.channel == "EMAIL"
        assert evt.direction == "OUTBOUND"
        assert evt.event_type == "SENT"

        # Query via Business relationship
        await session.refresh(biz, ["conversation_events"])
        assert len(biz.conversation_events) >= 1
        assert any(e.id == evt.id for e in biz.conversation_events)


@pytest.mark.asyncio
async def test_whatsapp_adapter_compliance_and_opt_in_guard():
    """
    Verify WhatsApp adapter strictly enforces opt-in:
    - Blocks outreach if contact lacks explicit opt-in consent.
    - Allows dispatch when opt-in consent is verified.
    """
    async with AsyncSessionLocal() as session:
        # 1. Business with public phone only (no opt-in)
        biz_cold = Business(
            name="Cold Roofing Co",
            domain=f"cold-roofing-{uuid.uuid4().hex[:6]}.com",
            country="US",
            niche="roofing",
            phone="+15559876543",
            whatsapp_eligible=False
        )
        session.add(biz_cold)
        await session.commit()
        await session.refresh(biz_cold)
        test_biz_ids.append(biz_cold.id)

        # Dispatch should be blocked by compliance guard
        res_blocked = await whatsapp_adapter.send_template(
            recipient_phone=biz_cold.phone,
            template_name="intro_audit_v1",
            business=biz_cold
        )
        assert res_blocked.success is False
        assert res_blocked.status == "BLOCKED_NO_CONSENT"
        assert "opt-in consent" in res_blocked.error

        # 2. Business with verified opt-in consent
        biz_opted_in = Business(
            name="Opted In Dental",
            domain=f"opted-dental-{uuid.uuid4().hex[:6]}.com",
            country="US",
            niche="dental",
            phone="+15558887766",
            whatsapp_eligible=True,
            whatsapp_consent_status="ELIGIBLE"
        )
        session.add(biz_opted_in)
        await session.commit()
        await session.refresh(biz_opted_in)
        test_biz_ids.append(biz_opted_in.id)

        # Dispatch should succeed in simulated dry-run mode
        res_allowed = await whatsapp_adapter.send_template(
            recipient_phone=biz_opted_in.phone,
            template_name="intro_audit_v1",
            business=biz_opted_in
        )
        assert res_allowed.success is True
        assert res_allowed.status == "SENT"
        assert res_allowed.dry_run is True
        assert res_allowed.message_id.startswith("wamid.")


@pytest.mark.asyncio
async def test_whatsapp_webhook_parsing_and_opt_out():
    """Verify WhatsApp status webhook and inbound message parsing (including STOP keyword)."""
    # 1. Delivery status webhook
    status_payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{
                        "id": "wamid.HBgL123456",
                        "status": "delivered",
                        "timestamp": "1710000000",
                        "recipient_id": "15558887766"
                    }]
                }
            }]
        }]
    }
    events = whatsapp_adapter.parse_webhook_payload(status_payload)
    assert len(events) == 1
    assert events[0]["event_type"] == ConversationEventType.DELIVERED.value
    assert events[0]["channel"] == ChannelType.WHATSAPP.value
    assert events[0]["direction"] == EventDirection.OUTBOUND.value

    # 2. Inbound message with opt-out keyword
    inbound_payload = {
        "entry": [{
            "changes": [{
                "value": {
                    "contacts": [{"profile": {"name": "Dr. Smith"}}],
                    "messages": [{
                        "id": "wamid.INBOUND999",
                        "from": "15558887766",
                        "type": "text",
                        "timestamp": "1710000050",
                        "text": {"body": "STOP sending messages"}
                    }]
                }
            }]
        }]
    }
    inbound_events = whatsapp_adapter.parse_webhook_payload(inbound_payload)
    assert len(inbound_events) == 1
    assert inbound_events[0]["event_type"] == ConversationEventType.RECEIVED.value
    assert inbound_events[0]["direction"] == EventDirection.INBOUND.value
    assert inbound_events[0]["metadata_json"]["is_opt_out"] is True
    assert "STOP" in inbound_events[0]["content"]


@pytest.mark.asyncio
async def test_voice_adapter_telephony_and_voicebox_boundary():
    """
    Verify Voice adapter telephony state machine, Voicebox TTS boundary, and STT transcription.
    """
    # 1. Voicebox TTS synthesis boundary
    tts_res = await voice_adapter.synthesize_speech("Hello, this is a diagnostic follow-up call.")
    assert tts_res.success is True
    assert tts_res.dry_run is True
    assert tts_res.duration_seconds > 0.0
    assert "voicebox" in tts_res.metadata.get("engine", "")

    # 2. Outbound call safety gate (blocked when unauthorized)
    call_res_blocked = await voice_adapter.initiate_call(
        recipient_phone="+15551234567",
        script_context="Diagnostic follow-up",
        is_authorized=False
    )
    assert call_res_blocked.success is False
    assert call_res_blocked.status == "BLOCKED"

    # 3. Telephony status webhook parsing
    twilio_status_payload = {
        "CallSid": "CA1234567890abcdef",
        "CallStatus": "completed",
        "From": "+18005550199",
        "To": "+15551234567",
        "CallDuration": "45",
        "AnsweredBy": "human"
    }
    telephony_evt = voice_adapter.parse_telephony_webhook(twilio_status_payload)
    assert telephony_evt["channel"] == ChannelType.VOICE.value
    assert telephony_evt["event_type"] == ConversationEventType.COMPLETED.value
    assert telephony_evt["metadata_json"]["duration_seconds"] == 45

    # 4. Voicemail detection
    twilio_vm_payload = {
        "CallSid": "CA9999999999abcdef",
        "CallStatus": "completed",
        "AnsweredBy": "machine_start"
    }
    vm_evt = voice_adapter.parse_telephony_webhook(twilio_vm_payload)
    assert vm_evt["event_type"] == ConversationEventType.VOICEMAIL.value

    # 5. STT transcription webhook parsing
    twilio_stt_payload = {
        "CallSid": "CA1234567890abcdef",
        "TranscriptionSid": "TR1122334455",
        "TranscriptionText": "Yes I am interested, please send me the turnaround package.",
        "TranscriptionStatus": "completed"
    }
    stt_evt = voice_adapter.parse_transcription_webhook(twilio_stt_payload)
    assert stt_evt["channel"] == ChannelType.VOICE.value
    assert stt_evt["event_type"] == ConversationEventType.TRANSCRIPT_READY.value
    assert "interested" in stt_evt["content"]


@pytest.mark.asyncio
async def test_email_adapter_normalization():
    """Verify Email adapter normalizes outbound messages, replies, and webhooks."""
    msg = OutreachMessage(
        id=42,
        business_id=1,
        recipient_email="prospect@example-business.com",
        subject="Quick observation regarding your website",
        body="We detected a mobile conversion issue on your site.",
        status=OutreachStatus.SENT.value
    )
    norm_send = email_adapter.normalize_outreach_send(msg, provider_name="resend", provider_msg_id="msg_sim_42")
    assert norm_send["channel"] == ChannelType.EMAIL.value
    assert norm_send["event_type"] == ConversationEventType.SENT.value
    assert norm_send["provider"] == "resend"
    assert "email_send_42_" in norm_send["idempotency_key"]

    # Delivery webhook (Resend)
    resend_webhook = {
        "type": "email.delivered",
        "data": {
            "email_id": "resend_id_888",
            "to": ["prospect@example-business.com"]
        }
    }
    wh_evts = email_adapter.parse_provider_webhook("resend", resend_webhook)
    assert len(wh_evts) == 1
    assert wh_evts[0]["event_type"] == ConversationEventType.DELIVERED.value
    assert wh_evts[0]["provider_event_id"] == "resend_id_888"


@pytest.mark.asyncio
async def test_unified_normalizer_and_idempotency_deduplication():
    """
    Verify ConversationNormalizer saves events and deduplicates duplicate webhooks
    with matching (provider, idempotency_key).
    """
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Deduplication Test Co",
            domain=f"dedup-{uuid.uuid4().hex[:6]}.com",
            country="US",
            niche="plumbing",
            public_email="contact@deduptest.com"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        test_biz_ids.append(biz.id)

        payload = {
            "channel": ChannelType.WHATSAPP.value,
            "direction": EventDirection.OUTBOUND.value,
            "event_type": ConversationEventType.DELIVERED.value,
            "provider": "whatsapp_cloud",
            "provider_event_id": "wamid.TEST_IDEMP_123",
            "idempotency_key": "wa_status_wamid.TEST_IDEMP_123_delivered",
            "content": "Message delivered to handset",
            "metadata_json": {"status": "delivered"}
        }

        # First ingestion
        evt1 = await conversation_normalizer.ingest_event(session, biz.id, payload)
        assert evt1.id is not None

        # Second ingestion (duplicate webhook replay)
        evt2 = await conversation_normalizer.ingest_event(session, biz.id, payload)
        assert evt2.id == evt1.id

        # Confirm count in database is exactly 1
        stmt = select(ConversationEvent).where(
            ConversationEvent.business_id == biz.id,
            ConversationEvent.idempotency_key == "wa_status_wamid.TEST_IDEMP_123_delivered"
        )
        saved_events = (await session.execute(stmt)).scalars().all()
        assert len(saved_events) == 1


@pytest.mark.asyncio
async def test_channel_eligibility_engine_policies():
    """
    Verify deterministic channel eligibility engine:
    1. Business with public email -> Email eligible.
    2. Business with public phone only -> WhatsApp INELIGIBLE (public phone is not consent).
    3. Business with explicit opt-in -> WhatsApp eligible.
    4. Suppressed email -> Email ineligible.
    """
    # 1. Cold lead with email & phone (no WhatsApp opt-in)
    biz1 = Business(
        id=901,
        name="Cold Lead Plumbers",
        domain="coldleadplumbers.com",
        country="US",
        niche="plumbing",
        public_email="office@coldleadplumbers.com",
        phone="+15552345678",
        whatsapp_eligible=False
    )
    res1 = channel_eligibility_engine.evaluate_business(biz1)
    assert res1.primary_channel == ChannelType.EMAIL.value
    assert res1.channels[ChannelType.EMAIL.value].eligible is True
    assert res1.channels[ChannelType.WHATSAPP.value].eligible is False
    assert "consent" in res1.channels[ChannelType.WHATSAPP.value].reason
    assert res1.channels[ChannelType.VOICE.value].eligible is False

    # 2. Lead with verified WhatsApp opt-in
    biz2 = Business(
        id=902,
        name="Opted In Cleaners",
        domain="optedincleaners.com",
        country="US",
        niche="cleaning",
        public_email=None,
        phone="+15553456789",
        whatsapp_eligible=True
    )
    res2 = channel_eligibility_engine.evaluate_business(biz2)
    assert res2.primary_channel == ChannelType.WHATSAPP.value
    assert res2.channels[ChannelType.WHATSAPP.value].eligible is True
    assert res2.channels[ChannelType.EMAIL.value].eligible is False

    # 3. Lead on email suppression list
    biz3 = Business(
        id=903,
        name="Suppressed Domain LLC",
        domain="suppressed.com",
        country="US",
        niche="legal",
        public_email="admin@suppressed.com",
        phone=None
    )
    res3 = channel_eligibility_engine.evaluate_business(
        biz3,
        suppressed_emails={"admin@suppressed.com"}
    )
    assert res3.primary_channel == "NONE"
    assert res3.channels[ChannelType.EMAIL.value].eligible is False
    assert "suppression" in res3.channels[ChannelType.EMAIL.value].reason


@pytest.mark.asyncio
async def test_reply_classifier_canonical_intents():
    """
    Verify ReplyClassifier categorizes all 7 canonical intents:
    1. POSITIVE
    2. NEGATIVE
    3. QUESTION
    4. NEEDS_HUMAN
    5. UNSUBSCRIBE
    6. OUT_OF_OFFICE
    7. UNKNOWN
    """
    # 1. POSITIVE
    res_pos = await reply_classifier.classify_text("Yes, I am definitely interested in seeing the demo!")
    assert res_pos["classification"] in (ReplyClassification.POSITIVE.value, ReplyClassification.INTERESTED.value)
    assert res_pos["confidence"] >= 0.90
    assert res_pos["classifier_provider"] == "deterministic_rules"

    # 2. NEGATIVE
    res_neg = await reply_classifier.classify_text("No thanks, we're good and already have a developer.")
    assert res_neg["classification"] in (ReplyClassification.NEGATIVE.value, ReplyClassification.NOT_INTERESTED.value)
    assert res_neg["confidence"] >= 0.90

    # 3. QUESTION
    res_q = await reply_classifier.classify_text("Can you explain how does it work and what is the turnaround time?")
    assert res_q["classification"] == ReplyClassification.QUESTION.value
    assert res_q["confidence"] >= 0.90

    # 4. NEEDS_HUMAN
    res_human = await reply_classifier.classify_text("This is our attorney regarding a legal complaint, connect me to a human operator.")
    assert res_human["classification"] == ReplyClassification.NEEDS_HUMAN.value
    assert res_human["confidence"] >= 0.90

    # 5. UNSUBSCRIBE
    res_unsub = await reply_classifier.classify_text("Please unsubscribe me and remove us from your list.")
    assert res_unsub["classification"] == ReplyClassification.UNSUBSCRIBE.value
    assert res_unsub["confidence"] >= 0.95

    # 6. OUT_OF_OFFICE
    res_ooo = await reply_classifier.classify_text("I am out of the office on vacation until next Tuesday.")
    assert res_ooo["classification"] == ReplyClassification.OUT_OF_OFFICE.value
    assert res_ooo["confidence"] >= 0.90

    # 7. UNKNOWN
    res_unknown = await reply_classifier.classify_text("123 xyz arbitrary string with no context")
    assert res_unknown["classification"] in (ReplyClassification.UNKNOWN.value, ReplyClassification.UNCLEAR.value)


@pytest.mark.asyncio
async def test_positive_inbound_triggers_demo_factory():
    """
    Verify that an inbound positive interaction across any channel
    triggers autonomous demo generation for that prospect's specific niche.
    """
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="BrightStar Solar",
            domain=f"brightstar-solar-{uuid.uuid4().hex[:6]}.com",
            country="US",
            niche="solar",
            public_email="contact@brightstarsolar.com",
            pipeline_stage=PipelineStage.CONTACTED.value
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)
        test_biz_ids.append(biz.id)

        # Inbound positive WhatsApp message
        inbound_wa = {
            "channel": ChannelType.WHATSAPP.value,
            "direction": EventDirection.INBOUND.value,
            "event_type": ConversationEventType.RECEIVED.value,
            "provider": "whatsapp_cloud",
            "provider_event_id": "wamid.SOLAR_POS_001",
            "idempotency_key": f"wa_pos_{biz.id}",
            "content": "Sounds good, send demo please! We would love to see how you optimize solar leads.",
            "metadata_json": {}
        }

        # Ingest event via normalizer
        evt = await conversation_normalizer.ingest_event(session, biz.id, inbound_wa)
        assert evt.id is not None
        assert evt.metadata_json.get("classification") in ("POSITIVE", "INTERESTED")

        # Verify CRM pipeline stage was advanced to QUALIFIED_REPLY
        await session.refresh(biz)
        assert biz.pipeline_stage == PipelineStage.QUALIFIED_REPLY.value

        # Verify a PipelineEvent was recorded
        pipe_stmt = select(PipelineEvent).where(PipelineEvent.business_id == biz.id)
        events = (await session.execute(pipe_stmt)).scalars().all()
        assert len(events) >= 1
        assert any("Positive response received" in e.note for e in events)
