"""
Unit and integration tests for the CEO Control Center — Phase 20.

Verifies:
1. GET /api/ceo/overview endpoint returns executive metrics, action required, pipeline funnel, active prospect, and system status.
2. All 8 executive metrics are accurately aggregated with safe dry-run revenue ($0.00 Dry Run).
3. Visual 9-stage pipeline funnel represents DISCOVERY through PAYMENT.
4. Active prospect displays score, offer price, audit summary, demo presence, and 8 deterministic QA gates.
5. Zero leaks: No filesystem paths, secrets, or API keys are exposed.
6. Safety invariants strictly held (EMAIL_DRY_RUN=True, payments disabled, revenue=0.0).
7. Dashboard HTML and JavaScript client contain all CEO Control Center views, buttons, and handlers.
"""
import os
import re
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.app import app
from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, AuditRun, Offer, Artifact, Proposal, PipelineStage, OutreachMessage
)
from app.delivery.requirements_engine import requirements_engine
from app.delivery.demo_factory import demo_factory
from app.delivery.demo_qa import demo_qa_engine
from app.payments.deal_service import deal_closing_service

created_biz_ids = []


@pytest.fixture(autouse=True)
async def ensure_db():
    await init_db()
    yield
    if created_biz_ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Artifact).where(Artifact.business_id.in_(created_biz_ids)))
            await session.execute(delete(Proposal).where(Proposal.business_id.in_(created_biz_ids)))
            await session.execute(delete(OutreachMessage).where(OutreachMessage.business_id.in_(created_biz_ids)))
            await session.execute(delete(Offer).where(Offer.business_id.in_(created_biz_ids)))
            await session.execute(delete(AuditRun).where(AuditRun.business_id.in_(created_biz_ids)))
            await session.execute(delete(Business).where(Business.id.in_(created_biz_ids)))
            await session.commit()
        created_biz_ids.clear()


async def create_ceo_test_prospect(session: AsyncSession, stage=PipelineStage.QUALIFIED_REPLY.value) -> Business:
    uid = uuid.uuid4().hex[:6]
    biz = Business(
        name=f"HomeIQ UAE Real Estate {uid}",
        domain=f"homeiq-{uid}.ae",
        country="AE",
        city="Dubai",
        niche="real-estate-ai",
        public_email=f"contact@homeiq-{uid}.ae",
        email_status="verified",
        pipeline_stage=stage
    )
    session.add(biz)
    await session.flush()

    audit = AuditRun(
        business_id=biz.id,
        url_audited=f"https://{biz.domain}/",
        performance_score=48.0,
        seo_score=85.0,
        a11y_score=82.0,
        ux_conversion_score=78.0,
        security_score=92.0,
        overall_health_score=62.0
    )
    session.add(audit)
    await session.flush()

    offer = Offer(
        business_id=biz.id,
        title="AI Real Estate Valuation & Lead Generation Speed Turnaround",
        recommended_price=1500.0,
        service_type="Speed Optimization"
    )
    session.add(offer)
    await session.commit()
    await session.refresh(biz)
    created_biz_ids.append(biz.id)
    return biz


@pytest.mark.asyncio
async def test_ceo_overview_api_baseline_structure():
    """Validates baseline structure and keys of GET /api/ceo/overview."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ceo/overview")
        assert res.status_code == 200
        data = res.json()

        # Top-level contracts
        assert "executive_metrics" in data
        assert "action_required" in data
        assert "pipeline_funnel" in data
        assert "active_prospect" in data
        assert "system_status" in data

        # Executive Metrics: 8 KPIs
        metrics = data["executive_metrics"]
        assert "total_prospects" in metrics
        assert "qualified_prospects" in metrics
        assert "outreach_awaiting_approval" in metrics
        assert "interested_leads" in metrics
        assert "active_demos" in metrics
        assert "proposals_awaiting_action" in metrics
        assert "payments_awaiting_authorization" in metrics
        assert "revenue_collected" in metrics
        assert "revenue_label" in metrics

        assert isinstance(metrics["total_prospects"], int)
        assert isinstance(metrics["qualified_prospects"], int)
        assert metrics["revenue_collected"] == 0.0
        assert "Dry Run" in metrics["revenue_label"]

        # 9-Stage Pipeline Funnel
        funnel = data["pipeline_funnel"]
        expected_stages = [
            "DISCOVERY", "QUALIFIED", "OUTREACH", "INTERESTED",
            "REQUIREMENTS", "DEMO", "QA", "PROPOSAL", "PAYMENT"
        ]
        for stage in expected_stages:
            assert stage in funnel
            assert isinstance(funnel[stage], int)

        # System Status & Safeguards
        status = data["system_status"]
        assert status["email_mode"] == "DRY RUN"
        assert status["payment_mode"] == "DISABLED"
        assert isinstance(status["inbox_polling"], bool)
        assert status["worker_status"] in ["Running", "Idle", "Online", "Standby"]


@pytest.mark.asyncio
async def test_ceo_overview_active_prospect_with_demo_and_qa_gates():
    """Validates that an active prospect with a generated demo returns demo and 8 QA gates."""
    async with AsyncSessionLocal() as session:
        biz = await create_ceo_test_prospect(session, stage=PipelineStage.QUALIFIED_REPLY.value)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)
        qa_res = demo_qa_engine.validate_demo(demo_res, packet)
        proposal = await deal_closing_service.create_proposal(
            session=session,
            business_id=biz.id,
            title="AI Valuation & Speed Turnaround Proposal",
            total_value=1500.0,
            advance_required=500.0
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ceo/overview")
        assert res.status_code == 200
        data = res.json()

        active = data["active_prospect"]
        assert active is not None
        assert active["id"] == biz.id
        assert "HomeIQ" in active["company_name"]
        assert active["domain"] == biz.domain
        assert active["score"] == 62.0
        assert active["offer_price"] in ["$1,500", "$2,500"]
        assert active["target_service"] != ""
        assert active["audit_summary"] != ""

        # Demo & 8 QA gates
        demo = active["demo"]
        assert demo["exists"] is True
        assert demo["demo_id"].upper().startswith("DEMO")
        assert demo["qa"] is not None
        assert demo["qa"]["overall_passed"] is True
        assert demo["qa"]["total_checks"] == 8
        assert demo["qa"]["passed_checks"] == 8

        checks = demo["qa"]["checks"]
        assert len(checks) == 8
        gate_names = [c["name"] for c in checks]
        assert "REQUIREMENTS_COVERAGE" in gate_names
        assert "ZERO_PLACEHOLDERS" in gate_names
        assert "COMMERCIAL_ALIGNMENT" in gate_names
        assert "DETERMINISTIC_CHECKSUM" in gate_names

        # Commercial Proposal & Payment (Dry Run Safe)
        assert active["proposal"]["status"] == "DRAFT"
        assert active["proposal"]["amount"] == 1500.0
        assert active["payment"]["is_dry_run"] is True


@pytest.mark.asyncio
async def test_ceo_overview_zero_leak_security_and_safety_invariants():
    """Validates that zero internal filesystem paths, credentials, or unsafe payment states leak."""
    async with AsyncSessionLocal() as session:
        biz = await create_ceo_test_prospect(session)
        packet = await requirements_engine.build_requirements_packet(session, biz.id)
        demo_res = await demo_factory.generate_demo_package(session, biz.id, packet)
        qa_res = demo_qa_engine.validate_demo(demo_res, packet)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ceo/overview")
        assert res.status_code == 200
        raw_text = res.text

        # 1. No absolute server paths leaked
        assert "C:\\Users\\" not in raw_text
        assert "C:/Users/" not in raw_text
        assert "/delivery/demos/" not in raw_text
        assert "\\delivery\\demos\\" not in raw_text

        # 2. No secrets/tokens leaked
        assert "sk-" not in raw_text
        assert "client_secret" not in raw_text
        assert "refresh_token" not in raw_text

        # 3. Safe revenue & payment invariants
        data = res.json()
        assert data["executive_metrics"]["revenue_collected"] == 0.0
        assert data["system_status"]["payment_mode"] == "DISABLED"
        assert data["system_status"]["email_mode"] == "DRY RUN"


@pytest.mark.asyncio
async def test_ceo_overview_action_required_queue_aggregation():
    """Validates that outreach queue items needing approval are surfaced in action_required."""
    async with AsyncSessionLocal() as session:
        biz = await create_ceo_test_prospect(session, stage=PipelineStage.APPROVAL.value)
        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=f"contact@{biz.domain}",
            status="PENDING_APPROVAL",
            subject="Strategic Partnership Opportunity for HomeIQ",
            body="Empirical audit shows opportunities for conversion enhancement."
        )
        session.add(msg)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ceo/overview")
        assert res.status_code == 200
        data = res.json()

        actions = data["action_required"]
        assert len(actions) > 0
        approval_actions = [a for a in actions if a["type"] == "OUTREACH_APPROVAL"]
        assert len(approval_actions) > 0
        item = approval_actions[0]
        assert "HomeIQ" in item["company"]
        assert "Outreach pending approval" in item["title"]
        assert item["item_id"] is not None


def test_ceo_dashboard_templates_and_scripts_contain_control_center():
    """Validates that index.html and app.js include all CEO Control Center elements and client functions."""
    target_root = "s:/AGENCY/BY AG"
    html_path = os.path.join(target_root, "app", "frontend", "templates", "index.html")
    js_path = os.path.join(target_root, "app", "frontend", "static", "app.js")

    assert os.path.exists(html_path)
    assert os.path.exists(js_path)

    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # 1. 7 CEO Navigation Items
    assert 'data-view="overview"' in html_content
    assert 'data-view="leads"' in html_content
    assert 'data-view="actions"' in html_content
    assert 'data-view="pipeline"' in html_content
    assert 'data-view="demos"' in html_content
    assert 'data-view="proposals"' in html_content
    assert 'data-view="system"' in html_content

    # 2. Friendly Error Banner
    assert 'id="ceo-error-banner"' in html_content
    assert 'id="ceo-error-msg"' in html_content

    # 3. 8 KPI Element IDs
    assert 'id="ceo-val-total-prospects"' in html_content
    assert 'id="ceo-val-qualified-prospects"' in html_content
    assert 'id="ceo-val-outreach-approval"' in html_content
    assert 'id="ceo-val-interested-leads"' in html_content
    assert 'id="ceo-val-active-demos"' in html_content
    assert 'id="ceo-val-proposals-action"' in html_content
    assert 'id="ceo-val-payments-auth"' in html_content
    assert 'id="ceo-val-revenue-dryrun"' in html_content

    # 4. 9-Stage Visual Pipeline Funnel
    assert 'id="ceo-pipeline-funnel-bar"' in html_content
    assert 'id="funnel-step-discovery"' in html_content
    assert 'id="funnel-step-qualified"' in html_content
    assert 'id="funnel-step-outreach"' in html_content
    assert 'id="funnel-step-interested"' in html_content
    assert 'id="funnel-step-requirements"' in html_content
    assert 'id="funnel-step-demo"' in html_content
    assert 'id="funnel-step-qa"' in html_content
    assert 'id="funnel-step-proposal"' in html_content
    assert 'id="funnel-step-payment"' in html_content

    # 5. Action Required & System Status
    assert 'id="ceo-action-required-list"' in html_content
    assert 'id="ceo-sys-inbox"' in html_content
    assert 'id="ceo-sys-email"' in html_content
    assert 'id="ceo-sys-payment"' in html_content
    assert 'id="ceo-sys-worker"' in html_content
    assert 'id="ceo-sys-last-activity"' in html_content

    # 6. Active Prospect Card with Demo & QA
    assert 'id="ceo-active-prospect-card"' in html_content
    assert 'id="ceo-demo-qa-badge"' in html_content
    assert 'id="ceo-btn-preview-demo"' in html_content
    assert 'id="ceo-demo-qa-gates"' in html_content

    with open(js_path, "r", encoding="utf-8") as f:
        js_content = f.read()

    # Client logic functions
    assert "async function loadCeoControlCenter()" in js_content
    assert "function renderCeoActionsRequired(" in js_content
    assert "function renderCeoPipelineFunnel(" in js_content
    assert "function renderCeoActiveProspect(" in js_content
    assert "function renderCeoSystemStatus(" in js_content
    assert "function previewActiveDemo()" in js_content
    assert "function showCeoError(" in js_content
    assert "function hideCeoError()" in js_content
