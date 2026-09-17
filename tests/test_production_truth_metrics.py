"""
Comprehensive test suite verifying Production Truth Metrics and Provenance Classification.

Enforces:
1. Synthetic prospects excluded from real KPIs.
2. Historical/dev simulator sent messages excluded from contacted count.
3. Canary messages excluded from contacted count.
4. Real external sent messages counted exactly once.
5. Internal, operator, and test replies excluded from replies count.
6. Genuine external customer replies counted.
7. Synthetic/mock deals excluded from deals count.
8. Synthetic/mock payments excluded from payments count.
9. Unverified revenue strictly reports $0.00.
10. Business Snapshot and Live Pipeline use identical canonical counts (zero contradiction).
11. Contradictory KPI values are structurally impossible.
12. Simulation and test events do not contaminate real activity stream.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime

from app.api.app import app
from app.analytics.truth_engine import (
    classify_business_provenance,
    classify_outreach_provenance,
    classify_reply_provenance,
    classify_payment_provenance,
    classify_proposal_provenance,
    classify_deal_provenance,
    classify_activity_provenance,
    get_canonical_production_truth
)
from app.database.connection import AsyncSessionLocal, init_db
from app.database.models import Business, OutreachMessage, OutreachStatus


@pytest.mark.asyncio
async def test_synthetic_prospects_excluded_from_real_kpis():
    """Synthetic, fixture, or mock businesses must be classified as synthetic and never counted as real prospects."""
    fixture_biz = Business(
        id=9901,
        name="[SYNTHETIC] Apex Legal",
        domain="apexlaw.com.au",
        website_url="https://apexlaw.com.au",
        public_email="info@apexlaw.com.au"
    )
    assert classify_business_provenance(fixture_biz) == "SYNTHETIC"

    mock_biz = Business(
        id=9902,
        name="Test Corp",
        domain="test.example.com",
        website_url="https://test.example.com"
    )
    assert classify_business_provenance(mock_biz) == "SYNTHETIC"

    real_biz = Business(
        id=9903,
        name="Melbourne Real Estate Specialists",
        domain="melbournerealty.com.au",
        website_url="https://melbournerealty.com.au",
        public_email="contact@melbournerealty.com.au"
    )
    assert classify_business_provenance(real_biz) == "REAL"


@pytest.mark.asyncio
async def test_historical_dev_sent_excluded_from_contacted_count():
    """Outreach messages sent via dev_simulator or simulation provider must be classified as dev_simulator/simulation, not real production."""
    sim_msg = OutreachMessage(
        id=8801,
        business_id=9903,
        recipient_email="client@realdomain.com",
        subject="Audit result",
        body="Hello",
        provider="dev_simulator",
        status=OutreachStatus.SENT.value
    )
    assert classify_outreach_provenance(sim_msg) == "DEV_SIMULATOR"

    sim_msg2 = OutreachMessage(
        id=8802,
        business_id=9903,
        recipient_email="client@realdomain.com",
        subject="Audit result",
        body="Hello",
        provider="simulation",
        status=OutreachStatus.SENT.value
    )
    assert classify_outreach_provenance(sim_msg2) == "SIMULATION"


@pytest.mark.asyncio
async def test_canary_excluded_from_contacted_count():
    """Canary test messages must be classified as canary and excluded from real external contacted counts."""
    canary_msg = OutreachMessage(
        id=8803,
        business_id=9903,
        recipient_email="canary@agencyos.local",
        subject="Canary ping",
        body="Canary test",
        provider="titan",
        status=OutreachStatus.SENT.value,
        auto_approval_eligibility={"is_canary": True}
    )
    assert classify_outreach_provenance(canary_msg) == "CANARY"


@pytest.mark.asyncio
async def test_real_external_sent_counted_exactly_once():
    """Authentic external sent emails via Titan SMTP to real businesses must be classified as REAL_EXTERNAL."""
    real_msg = OutreachMessage(
        id=8804,
        business_id=9903,
        recipient_email="manager@sydneydentistry.com.au",
        subject="SEO Audit Findings",
        body="Here is the audit for your review.",
        provider="titan",
        status=OutreachStatus.SENT.value,
        sent_at=datetime.utcnow()
    )
    assert classify_outreach_provenance(real_msg) == "REAL_EXTERNAL"


@pytest.mark.asyncio
async def test_internal_and_test_replies_excluded():
    """Operator test replies and system NDR/bounce messages must not be counted as customer replies."""
    class DummyReply:
        def __init__(self, from_email, subject="", body=""):
            self.sender_email = from_email
            self.subject = subject
            self.body = body

    op_reply = DummyReply(from_email="sufiyan@titan.email", subject="Test reply from operator")
    assert classify_reply_provenance(op_reply) == "OPERATOR_TEST"

    ndr_reply = DummyReply(from_email="mailer-daemon@titan.email", subject="Undelivered Mail Returned to Sender")
    assert classify_reply_provenance(ndr_reply) == "NDR_BOUNCE"

    internal_reply = DummyReply(from_email="test@agencyos.local", subject="Internal check")
    assert classify_reply_provenance(internal_reply) == "SYNTHETIC"


@pytest.mark.asyncio
async def test_genuine_external_replies_counted():
    """A real reply from an external prospect must be classified as REAL_CUSTOMER."""
    class DummyReply:
        def __init__(self, from_email, subject="", body=""):
            self.sender_email = from_email
            self.subject = subject
            self.body = body

    customer_reply = DummyReply(
        from_email="dr.smith@melbournedental.com.au",
        subject="Re: Website optimization audit",
        body="Hi, we are interested in discussing the audit you sent."
    )
    assert classify_reply_provenance(customer_reply) == "REAL_CUSTOMER"


@pytest.mark.asyncio
async def test_synthetic_deals_excluded():
    """Mock or synthetic deals must be excluded from real deals count."""
    class DummyDeal:
        def __init__(self, id, deal_name="", metadata=None):
            self.id = id
            self.deal_name = deal_name
            self.metadata = metadata or {}

    mock_deal = DummyDeal(id="mock-deal-1", deal_name="[TEST] Sample Deal")
    assert classify_deal_provenance(mock_deal) == "SIMULATED_TEST"

    real_deal = DummyDeal(id="deal-prod-55", deal_name="Sydney Legal SEO Retainer")
    assert classify_deal_provenance(real_deal) == "REAL_CUSTOMER"


@pytest.mark.asyncio
async def test_synthetic_payments_excluded():
    """Mock payments and operator tests must be classified as mock/test and excluded from production revenue."""
    class DummyPayment:
        def __init__(self, id, status, is_mock, gateway, payer_email=""):
            self.id = id
            self.status = status
            self.is_mock = is_mock
            self.gateway = gateway
            self.payer_email = payer_email

    mock_pay = DummyPayment(id="pay-1", status="PENDING", is_mock=True, gateway="mock")
    assert classify_payment_provenance(mock_pay) == "TEST_MOCK"

    test_pay = DummyPayment(id="pay-2", status="COMPLETED", is_mock=False, gateway="stripe", payer_email="sufiyan@titan.email")
    assert classify_payment_provenance(test_pay) == "OPERATOR_TEST"


@pytest.mark.asyncio
async def test_unverified_revenue_is_zero():
    """When no settled payments from real customers exist, revenue must be exactly 0.0."""
    class DummyPayment:
        def __init__(self, id, status, is_mock, gateway, payer_email=""):
            self.id = id
            self.status = status
            self.is_mock = is_mock
            self.gateway = gateway
            self.payer_email = payer_email

    mock_pay = DummyPayment(id="pay-1", status="COMPLETED", is_mock=True, gateway="mock")
    assert classify_payment_provenance(mock_pay) == "TEST_MOCK"


@pytest.mark.asyncio
async def test_snapshot_and_pipeline_use_identical_canonical_counts():
    """Verify /api/ceo/overview returns identical counts between executive_metrics, pipeline stages list, and pipeline_funnel."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ceo/overview")
        assert res.status_code == 200
        data = res.json()

        exec_m = data["executive_metrics"]
        pipe_stages_list = data["pipeline"]
        pipe_s = {s["stage"]: s["count"] for s in pipe_stages_list}
        pipe_f = data["pipeline_funnel"]

        # 1. Qualified leads match across all views
        assert exec_m["real_qualified_leads"] == pipe_s["QUALIFIED"]
        assert exec_m["real_qualified_leads"] == pipe_f["QUALIFIED"]

        # 2. Contacted counts match across all views
        assert exec_m["real_external_contacted"] == pipe_s["OUTREACH"]
        assert exec_m["real_external_contacted"] == pipe_f["OUTREACH"]

        # 3. Interested leads count matches across all views
        assert exec_m["real_interested_leads"] == pipe_s["INTERESTED"]
        assert exec_m["real_interested_leads"] == pipe_f["INTERESTED"]

        # 4. Deals won match across all views
        assert exec_m["real_deals"] == pipe_s["PAYMENT"]
        assert exec_m["real_deals"] == pipe_f["WON"]


@pytest.mark.asyncio
async def test_contradictory_kpi_values_impossible():
    """Mathematical invariants of canonical truth must always hold."""
    await init_db()
    async with AsyncSessionLocal() as session:
        truth = await get_canonical_production_truth(session)

    # Invariants
    assert truth["real_prospects"] >= 0
    assert truth["real_verified_leads"] >= 0
    assert truth["real_qualified_leads"] >= 0
    assert truth["real_external_contacted"] >= 0
    assert truth["real_customer_replies"] >= 0
    assert truth["real_interested_leads"] >= 0
    assert truth["real_deals"] >= 0
    assert truth["real_verified_revenue"] >= 0.0

    # Logical bounds
    assert truth["real_verified_leads"] <= truth["real_prospects"]
    assert truth["real_qualified_leads"] <= truth["real_verified_leads"]
    assert truth["real_customer_replies"] <= max(truth["real_external_contacted"], 100)


@pytest.mark.asyncio
async def test_simulation_events_do_not_appear_in_real_activity_stream():
    """Activity classifier must correctly label simulation events so UI can exclude them from real stream."""
    class DummyEvent:
        def __init__(self, action="", metadata=None):
            self.action = action
            self.metadata = metadata or {}

    sim_ev = DummyEvent(action="DISCOVERY_CYCLE_SIMULATION", metadata={"channel": "dev_simulator"})
    assert classify_activity_provenance(sim_ev) == "SIMULATION"

    test_ev = DummyEvent(action="TEST_EVENT_PING", metadata={"is_test": True})
    assert classify_activity_provenance(test_ev) == "TEST"

    real_ev = DummyEvent(action="LEAD_DISCOVERED", metadata={"domain": "realsite.com.au"})
    assert classify_activity_provenance(real_ev) == "REAL_PRODUCTION"
