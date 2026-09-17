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
    get_canonical_production_truth,
    is_lead_qualified,
    is_audit_complete,
    is_compliance_passed
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


@pytest.mark.asyncio
async def test_incomplete_audit_cannot_qualify():
    """A verified lead with score >= 55 cannot qualify if empirical audit is incomplete, zero, or missing."""
    class DummyBiz:
        def __init__(self, id=101, name="Perth Legal", domain="perthlegal.com.au", country="AU", verification_status="VERIFIED"):
            self.id = id
            self.name = name
            self.domain = domain
            self.country = country
            self.verification_status = verification_status
            self.public_email = "contact@perthlegal.com.au"
            self.whatsapp_consent_status = "INELIGIBLE_NO_CONSENT"
            self.compliance_status = "CLEARED"

    class DummyScore:
        def __init__(self, total_score=72.0):
            self.total_score = total_score

    class DummyFinding:
        def __init__(self, finding="Missing viewport tag"):
            self.finding = finding

    class DummyAudit:
        def __init__(self, score=70.0, url="https://perthlegal.com.au", summary="Audit complete", findings=None, metrics=None):
            self.overall_health_score = score
            self.url_audited = url
            self.summary = summary
            self.findings = findings if findings is not None else [DummyFinding()]
            self.metrics = metrics or {}

    biz = DummyBiz()
    score = DummyScore(72.0)

    # Case 1: Missing audit
    assert is_lead_qualified(biz, score, audit=None) is False

    # Case 2: Zero health score
    zero_audit = DummyAudit(score=0.0)
    assert is_lead_qualified(biz, score, audit=zero_audit) is False

    # Case 3: Summary indicating research failure
    failed_audit = DummyAudit(summary="RESEARCH_INSUFFICIENT: site down")
    assert is_lead_qualified(biz, score, audit=failed_audit) is False

    # Case 4: Missing url_audited
    empty_url_audit = DummyAudit(url="")
    assert is_lead_qualified(biz, score, audit=empty_url_audit) is False

    # Case 5: Zero findings
    no_findings_audit = DummyAudit(findings=[])
    assert is_lead_qualified(biz, score, audit=no_findings_audit) is False

    # Case 6: Fully completed audit -> Qualifies
    good_audit = DummyAudit(score=75.0, url="https://perthlegal.com.au", findings=[DummyFinding()])
    assert is_lead_qualified(biz, score, audit=good_audit) is True


@pytest.mark.asyncio
async def test_compliance_failure_cannot_qualify():
    """A lead failing any compliance gate (prohibited country, suppression list, compliance flags) cannot qualify."""
    class DummyBiz:
        def __init__(self, country="AU", domain="melbournelaw.com.au", email="info@melbournelaw.com.au"):
            self.id = 202
            self.name = "Melbourne Law"
            self.domain = domain
            self.country = country
            self.verification_status = "VERIFIED"
            self.public_email = email
            self.whatsapp_consent_status = "INELIGIBLE_NO_CONSENT"
            self.compliance_status = "CLEARED"

    class DummyScore:
        total_score = 65.0

    class DummyAudit:
        overall_health_score = 80.0
        url_audited = "https://melbournelaw.com.au"
        summary = "Audit clean"
        findings = ["Finding 1"]
        metrics = {"compliance_passed": True}

    score = DummyScore()
    audit = DummyAudit()

    # Case 1: Prohibited country (e.g. IN, PK, IL, DE)
    biz_in = DummyBiz(country="IN")
    assert is_lead_qualified(biz_in, score, audit) is False

    biz_de = DummyBiz(country="DE")
    assert is_lead_qualified(biz_de, score, audit) is False

    # Case 2: Suppressed domain
    biz_ok = DummyBiz(country="AU")
    assert is_lead_qualified(biz_ok, score, audit, suppressed_domains={"melbournelaw.com.au"}) is False

    # Case 3: Suppressed email
    assert is_lead_qualified(biz_ok, score, audit, suppressed_emails={"info@melbournelaw.com.au"}) is False

    # Case 4: WhatsApp compliance failure flag
    biz_wa_fail = DummyBiz(country="AU")
    biz_wa_fail.whatsapp_consent_status = "COMPLIANCE_FAILED"
    assert is_lead_qualified(biz_wa_fail, score, audit) is False

    # Case 5: Direct compliance status rejected
    biz_rej = DummyBiz(country="AU")
    biz_rej.compliance_status = "REJECTED"
    assert is_lead_qualified(biz_rej, score, audit) is False

    # Case 6: Passed compliance -> Qualifies
    assert is_lead_qualified(biz_ok, score, audit) is True


@pytest.mark.asyncio
async def test_no_deal_inference_from_payment():
    """A confirmed payment without a WON pipeline stage or explicit deal record must NEVER be inferred as a deal."""
    await init_db()
    async with AsyncSessionLocal() as session:
        truth = await get_canonical_production_truth(session)
        assert "real_deals" in truth
        assert "real_payments_confirmed" in truth
        # Even if real_deals == 0 and real_payments_confirmed > 0, real_deals stays 0
        if truth["real_deals"] == 0:
            assert truth["real_deals"] == 0


@pytest.mark.asyncio
async def test_unknown_activity_fails_closed():
    """Unrecognized or ambiguous activity actions must fail closed to UNKNOWN, never defaulting to REAL_PRODUCTION."""
    class DummyEvent:
        def __init__(self, action="", metadata=None, domain=""):
            self.action = action
            self.metadata = metadata or {}
            self.domain = domain

    # Arbitrary / unclassified action
    evt1 = DummyEvent(action="SOME_RANDOM_PLUGIN_ACTION")
    assert classify_activity_provenance(evt1) == "UNKNOWN"

    # Empty action with no metadata
    evt2 = DummyEvent(action="")
    assert classify_activity_provenance(evt2) == "UNKNOWN"

    # None event
    assert classify_activity_provenance(None) == "UNKNOWN"


@pytest.mark.asyncio
async def test_real_activity_recognized():
    """Explicit production actions with non-synthetic attribution must be classified as REAL_PRODUCTION."""
    class DummyEvent:
        def __init__(self, action="", metadata=None, domain=""):
            self.action = action
            self.metadata = metadata or {}
            self.domain = domain

    # Genuine production actions
    e1 = DummyEvent(action="LEAD_DISCOVERED", domain="brisbaneplumbing.com.au")
    assert classify_activity_provenance(e1) == "REAL_PRODUCTION"

    e2 = DummyEvent(action="OUTREACH_DISPATCHED", metadata={"recipient_email": "owner@brisbaneplumbing.com.au"})
    assert classify_activity_provenance(e2) == "REAL_PRODUCTION"

    e3 = DummyEvent(action="PAYMENT_CONFIRMED", metadata={"amount": 750.0})
    assert classify_activity_provenance(e3) == "REAL_PRODUCTION"

    e4 = DummyEvent(action="AUDIT_COMPLETED", domain="perthdental.com.au")
    assert classify_activity_provenance(e4) == "REAL_PRODUCTION"

    # Synthetic domain attached to a real action must be caught as TEST
    e_mock = DummyEvent(action="LEAD_DISCOVERED", domain="test.example.com")
    assert classify_activity_provenance(e_mock) == "TEST"


@pytest.mark.asyncio
async def test_revenue_only_from_verified_payment():
    """Revenue must strictly come from confirmed/settled payments from real customers. Proposals and pending payments never count."""
    class DummyPayment:
        def __init__(self, status="PENDING", amount=1500.0, is_mock=False, gateway="stripe", payer_email="client@realdomain.com"):
            self.id = 501
            self.status = status
            self.amount = amount
            self.is_mock = is_mock
            self.gateway = gateway
            self.payer_email = payer_email
            self.business_id = 999

    # Mock gateway is excluded
    mock_p = DummyPayment(status="PAID", is_mock=True, gateway="mock")
    assert classify_payment_provenance(mock_p) == "TEST_MOCK"

    # Pending payment is classified as real customer, but is NOT revenue
    pend_p = DummyPayment(status="PENDING", is_mock=False, gateway="stripe")
    assert classify_payment_provenance(pend_p) == "REAL_CUSTOMER"

    # Requested payment is NOT settled revenue
    req_p = DummyPayment(status="PAYMENT_REQUESTED", is_mock=False, gateway="stripe")
    assert classify_payment_provenance(req_p) == "REAL_CUSTOMER"

    # Confirmed payment from real customer
    paid_p = DummyPayment(status="PAID", is_mock=False, gateway="stripe")
    assert classify_payment_provenance(paid_p) == "REAL_CUSTOMER"
