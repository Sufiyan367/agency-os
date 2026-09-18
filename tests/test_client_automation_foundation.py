"""
Agency OS — Client Automation Foundation Test Suite.

Verifies the 12 core foundation invariants:
1. Client isolation (multi-tenancy)
2. Knowledge isolation (no cross-tenant leakage)
3. Missed-call state transition
4. Appointment booking state transition
5. FAQ retrieval & grounding
6. Human escalation triggering
7. CRM state synchronization & transition validation
8. Notification dispatch
9. Provider fallback & safety defaults
10. n8n orchestration hook
11. Supervised orchestrator routing
12. Zero fake external dispatch (suppression & null provider discipline)
"""

import pytest
from datetime import datetime, timedelta

from app.client_automation.models import (
    ClientAutomationConfig,
    BusinessHours,
    ServiceItem,
    FAQItem,
    BookingRules,
    CancellationPolicy,
    EscalationRules,
    QualificationRule,
    LeadRecord,
    LeadStage,
    AppointmentRecord,
    AppointmentStatus,
    CallRecord,
    CallType,
    EscalationReason,
    AutomationModule,
)
from app.client_automation.brain import (
    ClientBrain,
    SharedBrainManager,
    shared_brain_manager,
    TenantIsolationError,
)
from app.client_automation.interfaces import (
    NullCallAnsweringProvider,
    NullMissedCallProvider,
    MockMissedCallProvider,
    LocalCalendarProvider,
    LocalCRMProvider,
    LocalNotificationProvider,
    LocalAnalyticsProvider,
)
from app.client_automation.missed_call import MissedCallAutomationService
from app.client_automation.appointments import AppointmentAutomationService
from app.client_automation.knowledge import KnowledgeEngine
from app.client_automation.qualification import ClientLeadQualifier
from app.client_automation.crm import ClientCRMStateMachine, InvalidStageTransitionError
from app.client_automation.orchestrator import SupervisedClientOrchestrator
from app.client_automation.analytics import ClientAnalyticsEngine
from app.automations.n8n_orchestrator import N8nOrchestratorBridge, n8n_orchestrator
from app.core.event_bus import event_bus, AgencyEvent


@pytest.fixture(autouse=True)
def setup_shared_brain():
    """Reset shared brain manager before each test."""
    shared_brain_manager.clear()


def make_client_a_config() -> ClientAutomationConfig:
    return ClientAutomationConfig(
        client_id="client_dental_abc",
        business_name="ABC Dental Clinic",
        contact_email="dr_abc@dental.example.com",
        contact_phone="+15551112222",
        timezone="America/New_York",
        business_hours=BusinessHours(open_time="08:00", close_time="17:00", days_of_week=[0, 1, 2, 3, 4, 5]),
        services=[
            ServiceItem(
                service_id="srv_clean",
                name="Dental Cleaning",
                description="Routine prophylaxis and oral examination",
                duration_minutes=45,
                price=120.0,
            ),
            ServiceItem(
                service_id="srv_implant",
                name="Dental Implant Consultation",
                description="Titanium post and crown evaluation",
                duration_minutes=60,
                price=250.0,
            ),
        ],
        faqs=[
            FAQItem(
                faq_id="faq_insurance",
                question="Do you accept dental insurance?",
                answer="Yes, ABC Dental Clinic accepts Delta Dental, MetLife, and Cigna.",
                keywords=["insurance", "coverage", "delta", "metlife", "cigna"],
            ),
            FAQItem(
                faq_id="faq_parking",
                question="Where can I park?",
                answer="Free parking is available behind the clinic building in spaces labeled 'ABC Dental'.",
                keywords=["parking", "garage", "lot", "car"],
            ),
        ],
        booking_rules=BookingRules(slot_duration_minutes=45, buffer_minutes=15),
        cancellation_policy=CancellationPolicy(notice_hours_required=24, fee_amount=50.0),
        escalation_rules=EscalationRules(
            human_email="reception@dental.example.com",
            escalation_keywords=["emergency", "speak to human", "manager", "lawsuit"],
        ),
        brand_voice="Professional, reassuring, and gentle.",
        qualification_rules=[
            QualificationRule(
                rule_id="q1",
                question="Are you experiencing active dental pain?",
                key="has_pain",
                expected_type="boolean",
                required=True,
                weight=2.0,
            ),
            QualificationRule(
                rule_id="q2",
                question="Do you have dental insurance or self-pay?",
                key="payment_method",
                expected_type="choice",
                allowed_values=["insurance", "self-pay"],
                required=True,
                weight=1.0,
            ),
        ],
    )


def make_client_b_config() -> ClientAutomationConfig:
    return ClientAutomationConfig(
        client_id="client_legal_xyz",
        business_name="XYZ Law Associates",
        contact_email="counsel@xyzlaw.example.com",
        contact_phone="+15553334444",
        timezone="America/Chicago",
        business_hours=BusinessHours(open_time="09:00", close_time="18:00", days_of_week=[0, 1, 2, 3, 4]),
        services=[
            ServiceItem(
                service_id="srv_consult",
                name="Corporate Legal Consultation",
                description="Commercial contract and IP review",
                duration_minutes=60,
                price=500.0,
            )
        ],
        faqs=[
            FAQItem(
                faq_id="faq_retainer",
                question="How much is your initial retainer?",
                answer="XYZ Law Associates requires a standard $3,000 evergreen retainer.",
                keywords=["retainer", "deposit", "cost"],
            )
        ],
    )


# -----------------------------------------------------------------
# 1. CLIENT ISOLATION
# -----------------------------------------------------------------
def test_1_client_isolation():
    config_a = make_client_a_config()
    config_b = make_client_b_config()

    brain_a = shared_brain_manager.register_client(config_a)
    brain_b = shared_brain_manager.register_client(config_b)

    lead_a = LeadRecord(
        lead_id="lead_100",
        client_id="client_dental_abc",
        contact_name="Alice Smith",
        contact_phone="+15559990001",
    )
    brain_a.upsert_lead(lead_a)

    # Lead should exist in Brain A
    assert brain_a.get_lead("lead_100") is not None
    assert brain_a.get_lead("lead_100").contact_name == "Alice Smith"

    # Lead must NEVER exist in Brain B
    assert brain_b.get_lead("lead_100") is None

    # Attempting to save Lead A into Brain B must raise TenantIsolationError
    with pytest.raises(TenantIsolationError):
        brain_b.upsert_lead(lead_a)


# -----------------------------------------------------------------
# 2. KNOWLEDGE ISOLATION
# -----------------------------------------------------------------
def test_2_knowledge_isolation():
    config_a = make_client_a_config()
    config_b = make_client_b_config()

    brain_a = shared_brain_manager.register_client(config_a)
    brain_b = shared_brain_manager.register_client(config_b)

    # Search for insurance in Client A (should match)
    matches_a = brain_a.search_knowledge("insurance coverage")
    assert len(matches_a) > 0
    assert "Delta Dental" in matches_a[0]["content"]

    # Search for insurance in Client B (must return 0 matches)
    matches_b = brain_b.search_knowledge("insurance coverage")
    assert len(matches_b) == 0

    # Search for retainer in Client B (should match)
    matches_retainer_b = brain_b.search_knowledge("retainer deposit")
    assert len(matches_retainer_b) > 0
    assert "$3,000" in matches_retainer_b[0]["content"]

    # Search for retainer in Client A (must return 0 matches)
    assert len(brain_a.search_knowledge("retainer deposit")) == 0


# -----------------------------------------------------------------
# 3. MISSED CALL STATE TRANSITION
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_3_missed_call_state_transition():
    config_a = make_client_a_config()
    brain_a = shared_brain_manager.register_client(config_a)

    mock_provider = MockMissedCallProvider()
    service = MissedCallAutomationService(provider=mock_provider)

    # Simulate missed call during open hours (Monday 10:00 AM)
    open_time = datetime(2026, 9, 21, 10, 0)  # Monday
    result = await service.handle_missed_call(
        client_id="client_dental_abc",
        caller_phone="+15557778888",
        caller_name="Bob Jones",
        is_suppressed=False,
        call_time=open_time,
    )

    assert result["success"] is True
    assert result["textback_sent"] is True
    assert result["is_after_hours"] is False
    assert "ABC Dental Clinic" in result["message_body"]

    # Check that lead was created in CRM
    leads = brain_a.list_leads()
    assert len(leads) == 1
    assert leads[0].contact_phone == "+15557778888"
    assert leads[0].stage == LeadStage.INQUIRY

    # Check Call Record
    calls = brain_a.list_call_logs()
    assert len(calls) == 1
    assert calls[0].disposition == "TEXTBACK_SENT"
    assert len(mock_provider.sent_messages) == 1


# -----------------------------------------------------------------
# 4. APPOINTMENT STATE TRANSITION
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_4_appointment_state_transition():
    config_a = make_client_a_config()
    brain_a = shared_brain_manager.register_client(config_a)

    lead = LeadRecord(
        lead_id="lead_dental_01",
        client_id="client_dental_abc",
        contact_name="Charlie Brown",
        contact_phone="+15554445555",
        contact_email="charlie@example.com",
        stage=LeadStage.QUALIFIED,
    )
    brain_a.upsert_lead(lead)

    cal_provider = LocalCalendarProvider()
    notif_provider = LocalNotificationProvider()
    apt_service = AppointmentAutomationService(calendar_provider=cal_provider, notification_provider=notif_provider)

    # Next Tuesday at 09:00 AM
    target_dt = datetime(2026, 9, 22, 9, 0)
    slots = await apt_service.get_available_slots("client_dental_abc", target_dt, "srv_clean")
    assert "09:00" in slots

    # Book slot
    booking = await apt_service.book_appointment(
        client_id="client_dental_abc",
        lead_id="lead_dental_01",
        service_id="srv_clean",
        start_time=target_dt,
        notes="First time patient cleaning",
    )

    assert booking["success"] is True
    assert booking["lead_stage"] == "BOOKED"
    assert booking["confirmation_code"].startswith("CONF-")

    # Lead should now be in BOOKED stage
    updated_lead = brain_a.get_lead("lead_dental_01")
    assert updated_lead.stage == LeadStage.BOOKED

    # Slot 09:00 should no longer be available
    updated_slots = await apt_service.get_available_slots("client_dental_abc", target_dt, "srv_clean")
    assert "09:00" not in updated_slots


# -----------------------------------------------------------------
# 5. FAQ RETRIEVAL & GROUNDING
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_5_faq_retrieval():
    config_a = make_client_a_config()
    shared_brain_manager.register_client(config_a)

    # Ask grounded question
    res = await KnowledgeEngine.answer_query(
        client_id="client_dental_abc",
        query="Where can I park when I visit?",
    )

    assert res["answered"] is True
    assert res["escalate"] is False
    assert "Free parking is available behind the clinic" in res["answer"]


# -----------------------------------------------------------------
# 6. HUMAN ESCALATION
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_6_escalation():
    config_a = make_client_a_config()
    brain_a = shared_brain_manager.register_client(config_a)

    # Explicit human request
    res_human = await KnowledgeEngine.answer_query(
        client_id="client_dental_abc",
        query="I need to speak to a human or manager immediately",
    )
    assert res_human["escalate"] is True
    assert res_human["escalation_reason"] == EscalationReason.EXPLICIT_HUMAN_REQUEST.value

    # Unknown out-of-scope question (e.g. quantum mechanics)
    res_unknown = await KnowledgeEngine.answer_query(
        client_id="client_dental_abc",
        query="How does quantum entanglement affect general relativity?",
    )
    assert res_unknown["escalate"] is True
    assert res_unknown["escalation_reason"] == EscalationReason.LOW_CONFIDENCE.value

    # Check brain escalations list
    escalations = brain_a.list_escalations()
    assert len(escalations) == 2


# -----------------------------------------------------------------
# 7. CRM SYNCHRONIZATION & TRANSITION VALIDATION
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_7_crm_synchronization():
    config_a = make_client_a_config()
    brain_a = shared_brain_manager.register_client(config_a)

    lead = LeadRecord(
        lead_id="lead_crm_1",
        client_id="client_dental_abc",
        contact_name="Diana Prince",
        stage=LeadStage.INQUIRY,
    )
    brain_a.upsert_lead(lead)

    # Valid transition: INQUIRY -> QUALIFIED
    updated = await ClientCRMStateMachine.transition_stage(
        client_id="client_dental_abc",
        lead_id="lead_crm_1",
        to_stage=LeadStage.QUALIFIED,
        reason="Answered screening questions",
    )
    assert updated.stage == LeadStage.QUALIFIED

    # Invalid transition: QUALIFIED cannot jump straight to COMPLETED
    with pytest.raises(InvalidStageTransitionError):
        await ClientCRMStateMachine.transition_stage(
            client_id="client_dental_abc",
            lead_id="lead_crm_1",
            to_stage=LeadStage.COMPLETED,
        )


# -----------------------------------------------------------------
# 8. NOTIFICATION DISPATCH
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_8_notification_dispatch():
    provider = LocalNotificationProvider()
    res = await provider.send_notification(
        client_id="client_dental_abc",
        channel="email",
        recipient="dr_abc@dental.example.com",
        subject="Booking Notification",
        body="New appointment confirmed for Alice.",
        priority="HIGH",
    )

    assert res["status"] == "SENT_LOCAL"
    assert len(provider.dispatched_notifications) == 1
    assert provider.dispatched_notifications[0]["subject"] == "Booking Notification"


# -----------------------------------------------------------------
# 9. PROVIDER FALLBACK & SAFETY DEFAULTS
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_9_provider_fallback():
    null_voice = NullCallAnsweringProvider()
    null_sms = NullMissedCallProvider()

    config_a = make_client_a_config()

    voice_res = await null_voice.answer_call({}, config_a)
    assert voice_res["status"] == "UNCONFIGURED"
    assert voice_res["routed"] is False

    sms_res = await null_sms.send_textback("+15550009999", "Test", "client_dental_abc")
    assert sms_res["status"] == "INTEGRATION_REQUIRED"
    assert sms_res["success"] is False


# -----------------------------------------------------------------
# 10. N8N ORCHESTRATION HOOK
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_10_n8n_orchestration_hook():
    bridge = N8nOrchestratorBridge()
    bridge.hook_event_bus()

    # Publish client automation event
    evt = AgencyEvent(
        event_id="EVT-TEST-CL-01",
        correlation_id="CORR-CL-01",
        event_type="CLIENT_MISSED_CALL_PROCESSED",
        entity_type="client_automation",
        entity_id=0,
        payload={"client_id": "client_dental_abc", "call_id": "CALL-123", "textback_sent": True},
    )
    await bridge.handle_agency_event(evt)

    # Verify event was captured in bridge sink
    sink = bridge.get_mock_sink()
    matching = [e for e in sink if e["event_type"] == "AGENCY_CLIENT_MISSED_CALL_PROCESSED"]
    assert len(matching) > 0
    assert matching[0]["payload"]["action"] == "CLIENT_MISSED_CALL_OBSERVED"
    assert matching[0]["payload"]["client_id"] == "client_dental_abc"


# -----------------------------------------------------------------
# 11. SUPERVISED ORCHESTRATOR ROUTING
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_11_orchestrator_routing():
    config_a = make_client_a_config()
    brain_a = shared_brain_manager.register_client(config_a)

    orchestrator = SupervisedClientOrchestrator()

    # Route routine question
    q_res = await orchestrator.route_inbound_event(
        client_id="client_dental_abc",
        event_type="INBOUND_QUESTION",
        payload={"query": "Do you accept dental insurance?"},
    )
    assert q_res["answered"] is True
    assert "Delta Dental" in q_res["answer"]

    # Route lead qualification
    lead_res = await orchestrator.route_inbound_event(
        client_id="client_dental_abc",
        event_type="LEAD_SUBMISSION",
        payload={
            "contact_name": "Edward Norton",
            "contact_phone": "+15558889999",
            "answers": {"has_pain": True, "payment_method": "insurance"},
        },
    )
    assert lead_res["is_qualified"] is True
    assert lead_res["score"] == 100.0


# -----------------------------------------------------------------
# 12. ZERO FAKE EXTERNAL DISPATCH (SUPPRESSION & SAFETY)
# -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_12_no_fake_external_dispatch():
    config_a = make_client_a_config()
    brain_a = shared_brain_manager.register_client(config_a)

    mock_provider = MockMissedCallProvider()
    service = MissedCallAutomationService(provider=mock_provider)

    # Missed call from a suppressed caller
    res = await service.handle_missed_call(
        client_id="client_dental_abc",
        caller_phone="+15559999999",
        caller_name="OptedOutUser",
        is_suppressed=True,
    )

    # Text-back must be blocked
    assert res["status"] == "SUPPRESSED"
    assert res["textback_sent"] is False
    assert len(mock_provider.sent_messages) == 0

    # Analytics verification
    metrics = ClientAnalyticsEngine.get_client_dashboard_metrics("client_dental_abc")
    assert metrics["suppressed_calls"] == 1
    assert metrics["textbacks_dispatched"] == 0
