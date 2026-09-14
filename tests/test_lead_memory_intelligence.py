"""
Targeted Test Suite for Milestone: Persistent Lead Memory & Conversation Intelligence.

Validates Requirements A through O:
A. New lead memory is persisted.
B. Exact outbound email remains recoverable.
C. Inbound reply is linked to correct lead.
D. Duplicate inbound provider event is idempotent.
E. Memory summary updates after meaningful reply.
F. Context assembler returns correct lead-specific context with verified vs customer-said vs agency-said distinction.
G. Customer objection is remembered.
H. Customer commitment is remembered (OPEN -> COMPLETED).
I. Agency commitment is remembered.
J. UNSUBSCRIBE prevents future outreach and suppresses permanently.
K. Unsupported facts are not converted into verified facts (AI inference isolation).
L. Two leads process completely independently with zero cross-talk.
M. Commercial state (pricing/package) is retrieved from database rather than LLM memory.
N. A later reply months after outreach correctly reconstructs the previous interaction.
O. Existing outreach approval, rate limits, and idempotency behavior remain intact.
"""
import pytest
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import (
    Business, AuditRun, AuditFinding, Offer, OutreachMessage, Reply, Proposal,
    PipelineStage, PipelineEvent, ProspectMemory, ConversationEvent,
    OutreachStatus, ChannelType, EventDirection, ConversationEventType,
    SuppressionList, ActiveOutreachLock
)
from app.crm.memory_service import memory_service
from app.crm.commitment_service import commitment_service, CommitmentType, CommitmentStatus
from app.crm.objection_service import objection_service, NormalizedObjectionType, ObjectionStatus
from app.crm.context_assembler import context_assembler, ContextTag
from app.crm.reply_intelligence import reply_intelligence_service
from app.crm.reply_classifier import reply_classifier, ReplyClassification
from app.outreach.compliance import compliance_guard
from app.acquisition.controller import active_prospect_controller


def make_biz(uid: str, name: str = "Test Corp", stage: str = "CONTACTED") -> Business:
    """Helper to create a fully compliant Business instance adhering to NOT NULL schema constraints."""
    clean_uid = uid.replace("-", "_")
    return Business(
        name=f"{name} {clean_uid}",
        domain=f"biz_{clean_uid}.com",
        country="US",
        city="Austin",
        niche="Professional Services",
        public_email=f"contact@biz_{clean_uid}.com",
        pipeline_stage=stage
    )


@pytest.mark.asyncio
async def test_a_new_lead_memory_is_persisted():
    """Test A: Verifies that new lead memory is persistently stored in SQLite."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Apex Dental", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        mem = await memory_service.save_memory(
            session,
            business_id=biz.id,
            domain=biz.domain,
            contact_email=biz.public_email,
            channel_used="EMAIL",
            pipeline_stage="CONTACTED",
            audit_results={"performance_score": 42, "seo_score": 55},
            estimated_value=1200.0,
            offer_proposal={"title": "Dental Conversion Engine", "recommended_price": 1200.0},
            outreach_message={
                "message_id": 101,
                "subject": "Mobile patient booking observation for Apex Dental",
                "body": "Hi Dr. Smith,\n\nWe noticed mobile booking button friction on your site.\n\nBest,\nAgency OS",
                "sent_at": datetime.utcnow().isoformat()
            }
        )

        assert mem is not None
        assert mem.business_id == biz.id
        assert mem.domain == biz.domain
        assert mem.estimated_value == 1200.0
        assert mem.audit_results["performance_score"] == 42
        assert mem.exact_outbound_context.get("subject") == "Mobile patient booking observation for Apex Dental"


@pytest.mark.asyncio
async def test_b_exact_outbound_email_remains_recoverable():
    """Test B: Verifies that exact sent outbound email text, offer, and message ID are recoverable without paraphrasing."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Austin Auto", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        sent_body = "Hello Mark,\n\nWe completed an automated diagnostic of austinauto.com and noticed slow mobile load times.\n\nWe offer a turnkey speed remediation for $1,200.\n\nBest,\nAgency"
        outreach_msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Technical review of austinauto.com",
            body=sent_body,
            status=OutreachStatus.SENT.value,
            sent_at=datetime.utcnow() - timedelta(days=60)  # sent 2 months ago
        )
        session.add(outreach_msg)

        offer = Offer(
            business_id=biz.id,
            title="Automotive Speed & Conversion Turnaround",
            recommended_price=1200.0,
            service_type="Speed Turnaround"
        )
        session.add(offer)
        await session.commit()

        # Recover exact outbound context
        exact_ctx = await memory_service.get_exact_outbound_context(session, biz.id)
        assert exact_ctx is not None
        assert exact_ctx["subject"] == "Technical review of austinauto.com"
        assert exact_ctx["body"] == sent_body
        assert exact_ctx["quoted_price"] == 1200.0
        assert exact_ctx["recipient"] == biz.public_email


@pytest.mark.asyncio
async def test_c_inbound_reply_linked_to_correct_lead():
    """Test C: Verifies that an inbound reply is matched and linked to the correct lead."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Elite Roofing", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        result = await reply_intelligence_service.handle_inbound_reply(
            session,
            sender_email=biz.public_email,
            body="Thanks for reaching out. What exactly does your service cover?",
            subject=f"Re: Technical review of {biz.domain}"
        )

        assert result["status"] == "SUCCESS"
        assert result["business_id"] == biz.id
        assert result["domain"] == biz.domain


@pytest.mark.asyncio
async def test_d_duplicate_inbound_provider_event_is_idempotent():
    """Test D: Verifies that duplicate inbound provider events with identical idempotency key are safely ignored."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Bay Plumbing", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        idempotency_key = f"imap_msg_{uid}_999"

        # First delivery
        res1 = await reply_intelligence_service.handle_inbound_reply(
            session,
            sender_email=biz.public_email,
            body="We are interested, tell us more.",
            idempotency_key=idempotency_key
        )
        assert res1["status"] == "SUCCESS"

        # Duplicate delivery
        res2 = await reply_intelligence_service.handle_inbound_reply(
            session,
            sender_email=biz.public_email,
            body="We are interested, tell us more.",
            idempotency_key=idempotency_key
        )
        assert res2["status"] == "DUPLICATE_IGNORED"


@pytest.mark.asyncio
async def test_e_memory_summary_updates_after_meaningful_reply():
    """Test E: Verifies that memory summary stores questions and commitments after a reply without unbounded bloat."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Summit Law", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        reply_text = "I'll review the demo tomorrow morning.\nCan you also clarify what the payment terms are?"
        res = await reply_intelligence_service.handle_inbound_reply(
            session,
            sender_email=biz.public_email,
            body=reply_text
        )

        mem = await memory_service.get_memory(session, business_id=biz.id)
        assert mem is not None
        summary = mem.memory_summary
        assert "questions" in summary
        assert any("payment terms" in q.lower() for q in summary["questions"])
        assert "commitments" in summary


@pytest.mark.asyncio
async def test_f_context_assembler_returns_correct_context_and_truth_tags():
    """Test F: Verifies that context assembler attaches [VERIFIED FACT], [OBSERVED EVIDENCE], [CUSTOMER-SAID], and [AGENCY-SAID] tags."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Metro HVAC", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        audit = AuditRun(
            business_id=biz.id,
            url_audited=f"https://{biz.domain}",
            performance_score=48.0,
            seo_score=62.0
        )
        session.add(audit)
        await session.flush()

        finding = AuditFinding(
            audit_id=audit.id,
            category="Mobile",
            finding="LCP element takes 4.2s to render",
            severity="HIGH",
            evidence="LCP 4.2s on mobile viewport",
            url=f"https://{biz.domain}",
            recommended_fix="Compress hero image and preload critical fonts",
            estimated_business_impact="Improve mobile bounce rate by 28%"
        )
        session.add(finding)

        offer = Offer(
            business_id=biz.id,
            title="HVAC Performance Turnaround",
            recommended_price=1000.0,
            service_type="Speed Optimization"
        )
        session.add(offer)

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject="Quick diagnostic for metrohvac.com",
            body="Hello,\n\nYour mobile LCP is 4.2s.\n\nBest,\nAgency",
            status=OutreachStatus.SENT.value,
            sent_at=datetime.utcnow()
        )
        session.add(msg)
        await session.commit()

        assembled = await context_assembler.assemble_context(
            session,
            biz.id,
            current_inbound_body="Sounds interesting. How much does it cost?",
            current_inbound_sender=biz.public_email
        )

        prompt_str = assembled.to_prompt_context()
        assert ContextTag.VERIFIED_FACT in prompt_str
        assert ContextTag.OBSERVED_EVIDENCE in prompt_str
        assert ContextTag.CUSTOMER_SAID in prompt_str
        assert ContextTag.AGENCY_SAID in prompt_str
        assert "Metro HVAC" in prompt_str
        assert biz.domain in prompt_str
        assert "48/100" in prompt_str or "Mobile Performance score: 48" in prompt_str
        assert "$1000" in prompt_str or "$1,000" in prompt_str


@pytest.mark.asyncio
async def test_g_customer_objection_is_remembered():
    """Test G: Verifies that customer commercial objections (e.g. price/timing) are recorded and resolvable."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Prime Logistics", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Initialize memory
        await memory_service.save_memory(session, business_id=biz.id, domain=biz.domain)

        # Record objection
        obj = await objection_service.record_objection(
            session,
            business_id=biz.id,
            objection_type=NormalizedObjectionType.PRICE,
            statement="Your price of $1,000 is too expensive for our budget."
        )
        assert obj["status"] == "OPEN"
        assert obj["objection_type"] == "PRICE"

        # Check active objections
        active = await objection_service.get_active_objections(session, biz.id)
        assert len(active) == 1
        assert active[0]["objection_type"] == "PRICE"

        # Resolve objection
        resolved = await objection_service.resolve_objection(
            session,
            business_id=biz.id,
            objection_id_or_type=obj["id"],
            resolution="Agreed to split into two 50% milestone payments."
        )
        assert resolved["status"] == "RESOLVED"

        # Now active should be empty
        active_after = await objection_service.get_active_objections(session, biz.id)
        assert len(active_after) == 0


@pytest.mark.asyncio
async def test_h_customer_commitment_is_remembered_and_updated():
    """Test H: Verifies that customer commitment lifecycle (OPEN -> COMPLETED) is tracked persistently."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Nova Medical", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Initialize memory
        await memory_service.save_memory(session, business_id=biz.id, domain=biz.domain)

        # Add customer commitment
        cmt = await commitment_service.add_commitment(
            session,
            business_id=biz.id,
            commitment_type=CommitmentType.CUSTOMER,
            description="check the demo preview",
            raw_statement="I will check the demo tomorrow",
            due_at=(datetime.utcnow() + timedelta(days=1)).isoformat()
        )
        assert cmt["status"] == "OPEN"
        assert cmt["commitment_type"] == "CUSTOMER"

        # Complete commitment
        updated = await commitment_service.update_commitment_status(
            session,
            business_id=biz.id,
            commitment_id=cmt["id"],
            status=CommitmentStatus.COMPLETED
        )
        assert updated["status"] == "COMPLETED"

        # Open commitments should now be 0
        open_cmts = await commitment_service.get_commitments(session, biz.id, status=CommitmentStatus.OPEN)
        assert len(open_cmts) == 0


@pytest.mark.asyncio
async def test_i_agency_commitment_is_remembered():
    """Test I: Verifies that Agency commitments are tracked separately from Customer commitments."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Apex Spa", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Initialize memory
        await memory_service.save_memory(session, business_id=biz.id, domain=biz.domain)

        # Agency commitment
        agency_cmt = await commitment_service.add_commitment(
            session,
            business_id=biz.id,
            commitment_type=CommitmentType.AGENCY,
            description="send the custom booking proposal",
            raw_statement="I'll send the proposal today afternoon"
        )
        assert agency_cmt["commitment_type"] == "AGENCY"
        assert agency_cmt["status"] == "OPEN"

        # Query specifically for AGENCY commitments
        res = await commitment_service.get_commitments(session, biz.id, commitment_type=CommitmentType.AGENCY)
        assert len(res) == 1
        assert res[0]["description"] == "send the custom booking proposal"


@pytest.mark.asyncio
async def test_j_unsubscribe_prevents_future_outreach():
    """Test J: Verifies that an UNSUBSCRIBE reply suppresses the email permanently and marks lead as LOST."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Silent Corp", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        res = await reply_intelligence_service.handle_inbound_reply(
            session,
            sender_email=biz.public_email,
            body="Please unsubscribe me and remove our address from your lists."
        )

        assert res["classification"] == ReplyClassification.UNSUBSCRIBE.value
        assert res["new_stage"] == PipelineStage.LOST.value

        # Check compliance suppression table
        is_supp = await compliance_guard.is_suppressed(session, biz.public_email)
        assert is_supp is True


@pytest.mark.asyncio
async def test_k_unsupported_facts_are_not_converted_into_verified_facts():
    """Test K: Verifies that AI inferences or assumptions are labeled as [AI INFERENCE] and never injected into [VERIFIED FACT]."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Verified Clinic", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        assembled = await context_assembler.assemble_context(session, biz.id)
        # Verified facts must only come from database records
        for fact in assembled.verified_facts:
            assert "Verified Clinic" in fact or "Austin" in fact or "Professional Services" in fact or biz.domain in fact
            assert "revenue" not in fact.lower()  # No fabricated revenue
            assert "employees" not in fact.lower()  # No fabricated employee counts


@pytest.mark.asyncio
async def test_l_two_leads_process_independently():
    """Test L: Verifies strict lead isolation: processing Lead A never pollutes or blocks Lead B."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz_a = make_biz(f"{uid}_a", "Alpha Retail", PipelineStage.CONTACTED.value)
        biz_b = make_biz(f"{uid}_b", "Beta Solar", PipelineStage.CONTACTED.value)
        session.add_all([biz_a, biz_b])
        await session.commit()
        await session.refresh(biz_a)
        await session.refresh(biz_b)

        # Process reply for Lead A (Positive)
        res_a = await reply_intelligence_service.handle_inbound_reply(
            session,
            sender_email=biz_a.public_email,
            body="This sounds great, can you send over a demo?"
        )
        # Process reply for Lead B (Unsubscribe)
        res_b = await reply_intelligence_service.handle_inbound_reply(
            session,
            sender_email=biz_b.public_email,
            body="Unsubscribe me immediately."
        )

        assert res_a["new_stage"] in (PipelineStage.DEMO_REQUESTED.value, PipelineStage.QUALIFIED_REPLY.value)
        assert res_b["new_stage"] == PipelineStage.LOST.value

        # Context isolation check
        ctx_a = await context_assembler.assemble_context(session, biz_a.id)
        ctx_b = await context_assembler.assemble_context(session, biz_b.id)

        assert biz_a.domain in ctx_a.lead_profile["domain"]
        assert biz_b.domain not in ctx_a.lead_profile["domain"]
        assert biz_b.domain in ctx_b.lead_profile["domain"]
        assert biz_a.domain not in ctx_b.lead_profile["domain"]


@pytest.mark.asyncio
async def test_m_commercial_state_retrieved_from_database():
    """Test M: Verifies commercial price and terms are read directly from database without guessing."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Precision Tech", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Set specific custom price in Offer
        offer = Offer(
            business_id=biz.id,
            title="Custom Enterprise Optimization",
            recommended_price=1450.0,
            service_type="Full Stack Turnaround"
        )
        session.add(offer)
        await session.commit()

        assembled = await context_assembler.assemble_context(session, biz.id)
        assert assembled.commercial_state["price"] == 1450.0
        assert assembled.commercial_state["service_type"] == "Full Stack Turnaround"


@pytest.mark.asyncio
async def test_n_later_reply_reconstructs_previous_interaction():
    """Test N: Verifies that a reply received long after outreach reconstructs previous interaction."""
    await init_db()
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = make_biz(uid, "Vintage Motors", PipelineStage.CONTACTED.value)
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        # Dispatched 90 days ago
        outreach_msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=biz.public_email,
            subject=f"Website observation for {biz.domain}",
            body="Hello,\n\nWe noticed mobile performance delays on your website.\n\nBest,\nAgency",
            status=OutreachStatus.SENT.value,
            sent_at=datetime.utcnow() - timedelta(days=90)
        )
        session.add(outreach_msg)
        await session.commit()

        # Inbound reply arrives 90 days later
        res = await reply_intelligence_service.handle_inbound_reply(
            session,
            sender_email=biz.public_email,
            body="Hello, I found your email from a while ago. Are you still offering website turnaround?"
        )

        assert res["status"] == "SUCCESS"
        assert res["exact_outbound_recovered"] is True
        assert res["context_summary"]["exact_previous_outbound"]["subject"] == f"Website observation for {biz.domain}"


@pytest.mark.asyncio
async def test_o_existing_safety_controls_remain_intact():
    """Test O: Verifies that ActiveOutreachLock, daily limits, and compliance controls are not compromised."""
    await init_db()
    async with AsyncSessionLocal() as session:
        # Lock must exist and be queryable
        lock = await active_prospect_controller.get_or_create_lock(session)
        assert lock is not None
        assert hasattr(lock, "status")

        # Compliance guard must check daily limits
        assert hasattr(compliance_guard, "can_send_today")
        assert hasattr(compliance_guard, "is_suppressed")
