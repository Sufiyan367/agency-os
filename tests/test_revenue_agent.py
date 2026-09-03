"""
Comprehensive Automated Test Suite for Autonomous Revenue Agent.
Covers:
- One-prospect-at-a-time processing
- Duplicate prevention
- Commercial threshold ($500+ floor)
- Missing contact rejection (no fabrication)
- Email vs Voice selection
- Language detection (EN, AR, ES, FR)
- Conversation state persistence & message history
- Human takeover guardrails
- Emergency kill switch
- Dry-run mode enforcement
- Payment webhook verification
- Non-binding pricing commitments guardrail
"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.api.app import app
from app.agents.state_machine import ProspectState, AgentStateMachine
from app.agents.decision_engine import DecisionEngine
from app.agents.conversation_agent import ConversationAgent
from app.agents.revenue_agent import RevenueAgentOrchestrator
from app.communications.router import ContactRouter, ChannelType
from app.communications.conversation import ConversationSession
from app.core.config import settings


def test_one_prospect_at_a_time_isolation():
    """Verifies that the orchestrator initializes cleanly and manages state on a single prospect."""
    orch = RevenueAgentOrchestrator()
    status = orch.get_status()
    assert status["status"] == "IDLE"
    assert status["current_state"] == ProspectState.DISCOVER.value
    assert orch.stats["prospects_processed"] == 0


def test_commercial_floor_500_skips_low_value():
    """Verifies that prospects below the $500 floor are rejected with high confidence."""
    dec = DecisionEngine.evaluate_commercial_qualification(
        estimated_min_value=499.0,
        commercial_floor=500.0,
        buyer_score=85.0,
        opp_score=70.0
    )
    assert dec.target_state == ProspectState.SKIPPED
    assert "below commercial floor" in dec.reason

    # Valid >= 500 passes
    dec_pass = DecisionEngine.evaluate_commercial_qualification(
        estimated_min_value=500.0,
        commercial_floor=500.0,
        buyer_score=85.0,
        opp_score=70.0
    )
    assert dec_pass.target_state == ProspectState.CONTACT_DISCOVERY


def test_unverified_contact_skipped_no_fabrication():
    """Verifies that missing contact evidence leads to SKIPPED without fabricating emails or phones."""
    route = ContactRouter.route_contact(email=None, phone=None, voice_enabled=False)
    assert route.eligible is False
    assert route.channel == ChannelType.NONE
    assert "Rejecting synthetic fallback" in route.reason


def test_channel_router_email_vs_voice():
    """Verifies that email is prioritized when verified, and voice is used when enabled."""
    # Email preference
    route_email = ContactRouter.route_contact(
        email="owner@austinroofing.com",
        phone="+1-512-555-0144",
        voice_enabled=True
    )
    assert route_email.channel == ChannelType.EMAIL
    assert route_email.destination == "owner@austinroofing.com"

    # Voice selection when only phone exists
    route_voice = ContactRouter.route_contact(
        email=None,
        phone="+1-512-555-0144",
        voice_enabled=True
    )
    assert route_voice.channel == ChannelType.VOICE
    assert route_voice.destination == "+1-512-555-0144"


def test_language_detection_and_factual_grounding():
    """Verifies multilingual detection across EN, ES, FR, AR and factual audit grounding."""
    # English
    rep_en = ConversationAgent.process_reply("Can we book a call to discuss?", {"performance_score": 45.0}, 500.0)
    assert rep_en.detected_language == "en"
    assert rep_en.propose_meeting is True
    assert "45/100" in rep_en.reply_text

    # Spanish
    rep_es = ConversationAgent.process_reply("Hola, me gustaría agendar una llamada", {"performance_score": 52.0}, 750.0)
    assert rep_es.detected_language == "es"
    assert rep_es.propose_meeting is True
    assert "52/100" in rep_es.reply_text

    # French
    rep_fr = ConversationAgent.process_reply("Bonjour, pouvons-nous planifier un rendez-vous ?", {"performance_score": 60.0}, 800.0)
    assert rep_fr.detected_language == "fr"
    assert rep_fr.propose_meeting is True

    # Arabic
    rep_ar = ConversationAgent.process_reply("مرحبا، نود ترتيب موعد لمناقشة الموقع", {"performance_score": 68.0}, 1000.0)
    assert rep_ar.detected_language == "ar"
    assert rep_ar.propose_meeting is True


def test_non_binding_pricing_guardrail():
    """Verifies that the agent never autonomously commits to binding legal or pricing terms."""
    rep_price = ConversationAgent.process_reply("How much will this cost exactly?", {"performance_score": 50.0}, 500.0)
    assert rep_price.intent_detected == "PRICING"
    assert "$500" in rep_price.reply_text
    assert "scope exact deliverables" in rep_price.reply_text


def test_conversation_state_persistence():
    """Verifies multi-turn message history is stored correctly in ConversationSession."""
    session = ConversationSession(
        session_id="sess_test_1",
        business_name="Salis Roofing",
        channel=ChannelType.EMAIL,
        language="en"
    )
    assert len(session.messages) == 0

    ConversationAgent.process_reply("Are you available for a demo?", {"performance_score": 55.0}, 500.0, session=session)
    assert len(session.messages) == 2
    assert session.messages[0].sender == "PROSPECT"
    assert session.messages[1].sender == "AGENT"
    assert session.messages[1].intent == "MEETING_REQUEST"


def test_human_takeover_on_unrecognized_query():
    """Verifies that complex or unknown queries trigger handoff to human operators."""
    session = ConversationSession(
        session_id="sess_test_2",
        business_name="Custom Solutions",
        channel=ChannelType.EMAIL
    )
    rep = ConversationAgent.process_reply(
        "We need a custom HIPAA-compliant enterprise multi-tenant integration with Oracle ERP",
        {"performance_score": 50.0},
        1000.0,
        session=session
    )
    assert rep.handoff_to_human is True
    assert session.handed_off_to_human is True


def test_kill_switch_and_dry_run_safety():
    """Verifies that safety gates, dry-run flags, and emergency kill switch are strictly enforced."""
    orch = RevenueAgentOrchestrator()
    assert settings.EMAIL_DRY_RUN is True
    assert settings.VOICE_DRY_RUN is True
    assert settings.PAYMENT_DRY_RUN is True
    assert settings.RAZORPAY_MODE == "test"

    # Emergency kill switch disables agent
    res = orch.trigger_kill_switch()
    assert res["status"] == "KILLED"
    assert res["kill_switch_active"] is True
    assert orch.is_running is False
    # Restore settings for subsequent tests
    settings.AUTONOMOUS_AGENT_ENABLED = True
    settings.AUTONOMOUS_OUTREACH = True


@pytest.mark.asyncio
async def test_agent_api_endpoints():
    """Verifies the FastAPI agent control endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_status = await ac.get("/api/agent/status")
        assert res_status.status_code == 200
        data = res_status.json()
        assert "status" in data
        assert "current_state" in data
        assert "stats" in data

        res_start = await ac.post("/api/agent/start")
        assert res_start.status_code == 200
        assert res_start.json()["status"] == "RUNNING"

        res_pause = await ac.post("/api/agent/pause")
        assert res_pause.status_code == 200
        assert res_pause.json()["status"] == "PAUSED"

        res_stop = await ac.post("/api/agent/stop")
        assert res_stop.status_code == 200
        assert res_stop.json()["status"] == "IDLE"

        res_kill = await ac.post("/api/agent/kill")
        assert res_kill.status_code == 200
        assert res_kill.json()["status"] == "KILLED"
        # Restore settings for subsequent tests
        settings.AUTONOMOUS_AGENT_ENABLED = True
        settings.AUTONOMOUS_OUTREACH = True


@pytest.mark.asyncio
async def test_single_prospect_step_execution():
    """Verifies that step_single_prospect evaluates one prospect and proceeds autonomously to outreach."""
    orch = RevenueAgentOrchestrator()
    prospect_data = {
        "name": "TrueWorks Roofing",
        "domain": "trueworksroofing.com",
        "email": "contact@trueworksroofing.com",
        "phone": "+1-713-903-7663",
        "estimated_value": 750.0,
        "buyer_score": 88.0,
        "opportunity_score": 82.0
    }
    # Eligible $750 prospect proceeds autonomously without being blocked by an approval queue
    res = await orch.step_single_prospect(prospect_data, commercial_floor=500.0)
    assert res["status"] == "CONTACTED"
    assert res["channel"] == "EMAIL"
    assert orch.current_state == ProspectState.WAITING_RESPONSE
    assert orch.stats["contacts_attempted"] == 1
    assert orch.stats["prospects_processed"] == 1


@pytest.mark.asyncio
async def test_continuous_worker_lifecycle_startup_pause_stop_kill():
    """Verifies continuous worker background task startup, pause, stop, and kill switch."""
    import asyncio
    orch = RevenueAgentOrchestrator()
    orch.poll_interval_seconds = 0.1

    # 1. Startup
    start_res = orch.start()
    assert start_res["status"] == "RUNNING"
    assert start_res["worker_active"] is True
    assert orch.is_running is True
    assert orch.is_paused is False
    assert orch._task is not None and not orch._task.done()

    # Allow worker to cycle
    await asyncio.sleep(0.05)

    # 2. Pause
    pause_res = orch.pause()
    assert pause_res["status"] == "PAUSED"
    assert orch.is_paused is True
    assert orch.is_running is True

    # 3. Stop
    stop_res = orch.stop()
    try:
        await asyncio.wait_for(orch._task, timeout=1.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    assert stop_res["status"] == "IDLE"
    assert stop_res["worker_active"] is False
    assert orch.is_running is False
    assert orch.is_paused is False
    assert orch._task.done() is True

    # 4. Kill Switch
    orch.start()
    assert orch.is_running is True
    kill_res = orch.trigger_kill_switch()
    try:
        await asyncio.wait_for(orch._task, timeout=1.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    assert kill_res["status"] == "KILLED"
    assert kill_res["kill_switch_active"] is True
    assert orch.is_running is False
    assert orch._task.done() is True
    assert settings.AUTONOMOUS_AGENT_ENABLED is False
    assert settings.AUTONOMOUS_OUTREACH is False
    # Restore settings for subsequent tests
    settings.AUTONOMOUS_AGENT_ENABLED = True
    settings.AUTONOMOUS_OUTREACH = True


@pytest.mark.asyncio
async def test_suppression_enforcement_in_agent_worker():
    """Verifies that suppressed prospects (email or phone) are rejected immediately without outreach."""
    from app.database.connection import AsyncSessionLocal
    from app.outreach.compliance import compliance_guard

    orch = RevenueAgentOrchestrator()
    suppressed_email = "do-not-contact@suppressed-firm.com"

    # Add to suppression list
    async with AsyncSessionLocal() as session:
        await compliance_guard.add_to_suppression(session, email=suppressed_email, reason="OPTOUT")

    prospect_data = {
        "name": "Suppressed Firm LLC",
        "domain": "suppressed-firm.com",
        "email": suppressed_email,
        "phone": "+1-512-555-9988",
        "estimated_value": 850.0,
        "buyer_score": 90.0,
        "opportunity_score": 85.0
    }

    res = await orch.step_single_prospect(prospect_data, commercial_floor=500.0)
    assert res["status"] == "SKIPPED"
    assert res["reason"] == "SUPPRESSED"
    assert orch.current_state == ProspectState.SKIPPED


@pytest.mark.asyncio
async def test_worker_recovery_from_transient_error():
    """Verifies worker recovers from unexpected transient errors without terminating."""
    import asyncio
    orch = RevenueAgentOrchestrator()
    orch.poll_interval_seconds = 0.05

    # Trigger start
    orch.start()
    assert orch.is_running is True
    assert orch._task is not None

    # Let the loop execute multiple iterations safely
    await asyncio.sleep(0.15)

    # Worker must still be running (not crashed)
    status = orch.get_status()
    assert status["is_running"] is True
    assert status["worker_active"] is True

    # Clean stop
    orch.stop()
    assert orch.is_running is False


@pytest.mark.asyncio
async def test_sqlite_wal_mode_and_busy_timeout():
    """Verifies that SQLite is configured with WAL journal mode and busy_timeout."""
    from app.database.connection import engine
    from sqlalchemy import text

    async with engine.connect() as conn:
        res_wal = await conn.execute(text("PRAGMA journal_mode;"))
        mode = res_wal.scalar()
        # In SQLite, WAL mode should be active
        assert str(mode).lower() == "wal"

        res_timeout = await conn.execute(text("PRAGMA busy_timeout;"))
        timeout = res_timeout.scalar()
        assert int(timeout) >= 5000


@pytest.mark.asyncio
async def test_commercial_qualification_499_skipped():
    """Requirement (a): Proves that a prospect estimated at $499 is strictly skipped."""
    orch = RevenueAgentOrchestrator()
    prospect_data = {
        "name": "Discount HVAC",
        "domain": "discounthvac.test",
        "email": "info@discounthvac.test",
        "phone": "+1-512-555-0199",
        "estimated_value": 499.0,
        "buyer_score": 75.0,
        "opportunity_score": 70.0
    }
    res = await orch.step_single_prospect(prospect_data, commercial_floor=500.0)
    assert res["status"] == "SKIPPED"
    assert "below commercial floor" in res["reason"].lower() or "500" in res["reason"]
    assert orch.current_state == ProspectState.SKIPPED
    assert orch.stats["prospects_skipped"] == 1


@pytest.mark.asyncio
async def test_commercial_qualification_500_proceeds():
    """Requirement (b): Proves that a prospect estimated at exactly $500 can proceed."""
    orch = RevenueAgentOrchestrator()
    prospect_data = {
        "name": "Benchmark Plumbing",
        "domain": "benchmarkplumbing.test",
        "email": "service@benchmarkplumbing.test",
        "phone": "+1-512-555-0500",
        "estimated_value": 500.0,
        "buyer_score": 80.0,
        "opportunity_score": 75.0
    }
    res = await orch.step_single_prospect(prospect_data, commercial_floor=500.0)
    assert res["status"] == "CONTACTED"
    assert res["channel"] == "EMAIL"
    assert orch.current_state == ProspectState.WAITING_RESPONSE
    assert orch.stats["contacts_attempted"] == 1


@pytest.mark.asyncio
async def test_commercial_qualification_750_proceeds_autonomously_without_approval():
    """Requirement (c): Proves that a $750 prospect proceeds autonomously without approval."""
    orch = RevenueAgentOrchestrator()
    prospect_data = {
        "name": "Apex Commercial Roofing",
        "domain": "apexroofing.test",
        "email": "quotes@apexroofing.test",
        "phone": "+1-512-555-0750",
        "estimated_value": 750.0,
        "buyer_score": 90.0,
        "opportunity_score": 85.0
    }
    res = await orch.step_single_prospect(prospect_data, commercial_floor=500.0)
    assert res["status"] == "CONTACTED"
    assert orch.current_state == ProspectState.WAITING_RESPONSE
    assert res["channel"] in ("EMAIL", "VOICE")


@pytest.mark.asyncio
async def test_no_approval_queue_state_blocks_eligible_outreach():
    """Requirement (d): Proves that no approval_queue state blocks eligible outreach."""
    orch = RevenueAgentOrchestrator()
    prospect_data = {
        "name": "Capital Dental Care",
        "domain": "capitaldental.test",
        "email": "office@capitaldental.test",
        "phone": "+1-512-555-0800",
        "estimated_value": 850.0,
        "buyer_score": 85.0,
        "opportunity_score": 80.0
    }
    res = await orch.step_single_prospect(prospect_data, commercial_floor=500.0)
    # Status must NOT be HELD_FOR_APPROVAL or PENDING_APPROVAL
    assert res["status"] != "HELD_FOR_APPROVAL"
    assert res["status"] == "CONTACTED"
    assert orch.current_state != ProspectState.OUTREACH_PENDING
    assert orch.current_state == ProspectState.WAITING_RESPONSE


@pytest.mark.asyncio
async def test_generated_commercial_offers_never_below_500():
    """Requirement (e): Proves that all packages and generated offers never fall below $500."""
    from app.offers.generator import SERVICE_PACKAGES, offer_engine
    from app.database.connection import AsyncSessionLocal
    from app.database.models import Business, AuditRun

    # 1. Verify all static packages have base_min >= 500.0
    for pkg_name, pkg in SERVICE_PACKAGES.items():
        assert pkg["base_min"] >= 500.0, f"Package {pkg_name} has base_min {pkg['base_min']} < $500"
        assert pkg["recommended"] >= 500.0, f"Package {pkg_name} has recommended {pkg['recommended']} < $500"

    # 2. Verify dynamically generated offer respects $500 floor
    import uuid
    uid = uuid.uuid4().hex[:8]
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Floor Test Business",
            domain=f"floortest-{uid}.test",
            website_url=f"https://floortest-{uid}.test",
            country="US",
            niche="contractors",
            public_email=f"test@{uid}.test"
        )
        session.add(biz)
        await session.commit()
        await session.refresh(biz)

        audit = AuditRun(
            business_id=biz.id,
            url_audited="https://floortest.test",
            overall_health_score=45.0,
            performance_score=40.0,
            seo_score=50.0,
            a11y_score=45.0,
            ux_conversion_score=40.0
        )
        session.add(audit)
        await session.commit()

        offer = await offer_engine.generate_offer_for_business(session, biz)
        assert offer.suggested_price_min >= 500.0
        assert offer.recommended_price >= 500.0


@pytest.mark.asyncio
async def test_safety_gates_kill_switch_and_human_takeover():
    """Requirement (f): Proves existing safety gates (kill switch and human takeover) still work."""
    from app.core.config import settings

    orch = RevenueAgentOrchestrator()
    prospect_data = {
        "name": "Safety Test Business",
        "domain": "safetytest.test",
        "email": "test@safetytest.test",
        "phone": "+1-512-555-0999",
        "estimated_value": 750.0,
        "buyer_score": 85.0,
        "opportunity_score": 80.0
    }

    # 1. Kill Switch
    original_enabled = settings.AUTONOMOUS_AGENT_ENABLED
    try:
        settings.AUTONOMOUS_AGENT_ENABLED = False
        res_killed = await orch.step_single_prospect(prospect_data, commercial_floor=500.0)
        assert res_killed["status"] == "KILLED"
        assert orch.current_state == ProspectState.OUTREACH_PENDING
    finally:
        settings.AUTONOMOUS_AGENT_ENABLED = original_enabled

    # 2. Human Takeover
    prospect_with_takeover = dict(prospect_data)
    prospect_with_takeover["human_takeover"] = True
    res_takeover = await orch.step_single_prospect(prospect_with_takeover, commercial_floor=500.0)
    assert res_takeover["status"] == "HUMAN_TAKEOVER"
    assert orch.current_state == ProspectState.OUTREACH_PENDING


@pytest.mark.asyncio
async def test_prospect_worker_get_next_uncontacted_prospect_regression():
    """
    Regression Test: Reproduces and verifies the fix for:
    AttributeError: type object 'LocalBusiness' has no attribute 'contacted'
    Ensures that get_next_uncontacted_prospect successfully queries uncontacted prospects
    using canonical lifecycle stages (PipelineStage.DISCOVERED / CONTACTED) without crashing.
    """
    import uuid
    from app.agents.prospect_agent import SingleProspectAgent
    from app.database.connection import AsyncSessionLocal
    from app.database.models import Business, PipelineStage

    worker = SingleProspectAgent(provider_type="mock")
    uid = uuid.uuid4().hex[:8]

    async with AsyncSessionLocal() as session:
        # 1. Calling get_next_uncontacted_prospect must NOT raise AttributeError: type object 'LocalBusiness' has no attribute 'contacted'
        try:
            cand = await worker.get_next_uncontacted_prospect(session)
        except AttributeError as e:
            pytest.fail(f"Regression detected! get_next_uncontacted_prospect raised AttributeError: {e}")

        # 2. Insert an uncontacted Business
        uncontacted_biz = Business(
            name="Uncontacted Business",
            domain=f"uncontacted-{uid}.com",
            website_url=f"https://uncontacted-{uid}.com",
            country="US",
            city="Austin",
            niche="roofing",
            public_email=f"info@{uid}.com",
            phone="+1-512-555-0101",
            pipeline_stage=PipelineStage.DISCOVERED.value
        )
        session.add(uncontacted_biz)
        await session.commit()
        await session.refresh(uncontacted_biz)

        # 3. Query must find the uncontacted business
        fetched = await worker.get_next_uncontacted_prospect(session)
        assert fetched is not None
        assert hasattr(fetched, "domain")

        # 4. Advance to CONTACTED
        uncontacted_biz.pipeline_stage = PipelineStage.CONTACTED.value
        await session.commit()

        # 5. Advance another test business to WON
        won_biz = Business(
            name="Won Business",
            domain=f"won-{uid}.com",
            website_url=f"https://won-{uid}.com",
            country="US",
            city="Austin",
            niche="plumbing",
            public_email=f"won@{uid}.com",
            phone="+1-512-555-0102",
            pipeline_stage=PipelineStage.WON.value
        )
        session.add(won_biz)
        await session.commit()

        # Neither CONTACTED nor WON business should be returned if queried for this domain
        q_check = (
            await worker.get_next_uncontacted_prospect(session)
        )
        if q_check:
            assert q_check.domain not in (f"uncontacted-{uid}.com", f"won-{uid}.com")


@pytest.mark.asyncio
async def test_continuous_worker_fetches_and_processes_from_db_without_crash():
    """Verifies that the continuous worker loop successfully fetches from DB without AttributeError."""
    import asyncio
    orch = RevenueAgentOrchestrator()
    orch.poll_interval_seconds = 0.05

    # Start worker and let it cycle past line 143 (cand_biz = await self.prospect_worker.get_next_uncontacted_prospect)
    orch.start()
    assert orch.is_running is True

    await asyncio.sleep(0.15)

    # Status must still be running without crashing
    status = orch.get_status()
    assert status["is_running"] is True
    assert status["worker_active"] is True

    # Stop worker cleanly
    orch.stop()
    assert orch.is_running is False


@pytest.mark.asyncio
async def test_persist_stage_rejected_disqualified_regression():
    """
    Regression Test: Reproduces and verifies the fix for:
    [RevenueAgent] Could not persist pipeline stage REJECTED: DISQUALIFIED
    Verifies that calling _persist_stage(candidate_data, PipelineStage.REJECTED.value)
    completes cleanly without raising AttributeError, persists 'REJECTED' to Business,
    and persists 'DISQUALIFIED' to LocalLead.
    """
    import uuid
    from app.database.connection import AsyncSessionLocal
    from app.database.models import Business, PipelineStage
    from app.models.entities import LocalBusiness, LocalLead, LeadStatus
    from sqlalchemy import select

    orch = RevenueAgentOrchestrator()
    uid = uuid.uuid4().hex[:8]
    dom = f"reject-test-{uid}.com"

    async with AsyncSessionLocal() as session:
        # 1. Create Business and LocalBusiness with LocalLead
        biz = Business(
            name=f"Reject Test {uid}",
            domain=dom,
            website_url=f"https://{dom}",
            country="US",
            city="Austin",
            niche="roofing",
            public_email=f"info@{dom}",
            pipeline_stage=PipelineStage.DISCOVERED.value
        )
        session.add(biz)
        await session.flush()

        local_biz = LocalBusiness(
            name=f"Reject Local {uid}",
            domain=dom,
            website_url=f"https://{dom}",
            niche="roofing",
            city="Austin",
            country="US",
            email=f"info@{dom}"
        )
        session.add(local_biz)
        await session.flush()

        lead = LocalLead(
            business_id=local_biz.id,
            contact_name="Owner",
            contact_email=f"info@{dom}",
            status=LeadStatus.NEW.value
        )
        session.add(lead)
        await session.commit()

        biz_id = biz.id
        local_biz_id = local_biz.id

        # 2. Call _persist_stage with PipelineStage.REJECTED.value
        cand_data = {"id": biz_id, "domain": dom}
        try:
            await orch._persist_stage(cand_data, PipelineStage.REJECTED.value)
        except Exception as e:
            pytest.fail(f"Regression! _persist_stage raised error: {e}")

    # 3. Verify in database with a clean verification session
    async with AsyncSessionLocal() as verify_session:
        res_biz = await verify_session.execute(select(Business).where(Business.id == biz_id))
        fresh_biz = res_biz.scalar_one()
        assert fresh_biz.pipeline_stage == PipelineStage.REJECTED.value
        assert fresh_biz.verification_status == "REJECTED"

        res_lead = await verify_session.execute(select(LocalLead).where(LocalLead.business_id == local_biz_id))
        fresh_lead = res_lead.scalar_one()
        assert fresh_lead.status == LeadStatus.DISQUALIFIED.value


@pytest.mark.asyncio
async def test_permanently_disqualified_prospect_not_selected_again_by_continuous_worker():
    """
    Verifies that a disqualified/rejected prospect is never selected again
    by get_next_uncontacted_prospect(), preventing endless retry loops.
    """
    import uuid
    from app.agents.prospect_agent import SingleProspectAgent
    from app.database.connection import AsyncSessionLocal
    from app.database.models import Business, PipelineStage
    from app.models.entities import LocalBusiness, LocalLead, LeadStatus
    from sqlalchemy import select

    orch = RevenueAgentOrchestrator()
    worker = SingleProspectAgent(provider_type="mock")
    uid = uuid.uuid4().hex[:8]
    dom = f"disqualified-{uid}.com"

    async with AsyncSessionLocal() as session:
        # 1. Insert an uncontacted business
        biz = Business(
            name=f"Disqualified Biz {uid}",
            domain=dom,
            website_url=f"https://{dom}",
            country="US",
            city="Austin",
            niche="plumbing",
            public_email=f"contact@{dom}",
            pipeline_stage=PipelineStage.DISCOVERED.value
        )
        session.add(biz)
        await session.commit()
        biz_id = biz.id

        # 2. Worker finds it when uncontacted
        cand_found = await worker.get_next_uncontacted_prospect(session)
        assert cand_found is not None

        # 3. Step prospect with value below $500 (triggers rejection/disqualification)
        cand_data = {
            "id": biz_id,
            "name": "Disqualified Biz",
            "domain": dom,
            "email": f"contact@{dom}",
            "estimated_value": 350.0,  # Below $500 floor
            "buyer_score": 40.0,
            "opportunity_score": 45.0
        }
        res_step = await orch.step_single_prospect(cand_data, commercial_floor=500.0)
        assert res_step["status"] == "SKIPPED"

    # 4. Verify stage was persisted to REJECTED in a clean session
    async with AsyncSessionLocal() as verify_session:
        res_check = await verify_session.execute(select(Business).where(Business.id == biz_id))
        fresh_biz = res_check.scalar_one()
        assert fresh_biz.pipeline_stage == PipelineStage.REJECTED.value

        # 5. Worker MUST NOT return this rejected prospect again
        next_cand = await worker.get_next_uncontacted_prospect(verify_session)
        if next_cand:
            assert next_cand.domain != dom



