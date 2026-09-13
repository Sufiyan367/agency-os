"""Comprehensive Automated Test Suite for Mega Prompt 5.

Verifies:
1. UI Geometry Hardening & CSS Invariants.
2. Demo Acceptance & Proposal Engine (40/60 split, $500 floor).
3. Change Request Feedback Loop (v1 -> v2 without mutating v1).
4. Google Pay Instructions & Anti-Fraud Payment Verification Gate.
5. Production Pipeline Security Boundary & Execution (Build, 10-Gate QA, Deploy, Handover).
6. 4-Industry Validation (Automotive, Dental, Roofing, HVAC).
7. Orange Auto Canary Safety (#12 APPROVED invariant).
"""
import pytest
import os
import re
from datetime import datetime
from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.database.models import (
    Business, OutreachMessage, CustomerProject, ProjectSpecification, ProjectProposal,
    CustomerAcceptance, ProductionProject, ProductionBuild, ProductionQA,
    ProductionDeployment, HandoverRecord, Payment, Customer,
    CustomerAcceptanceStatus, CommercialProposalStatus, ProductionProjectStatus
)
from app.commercial.pricing_engine import PricingEngine
from app.commercial.proposal_engine import ProposalEngine
from app.commercial.acceptance_handler import AcceptanceHandler
from app.payments.workflow import PaymentWorkflowCoordinator
from app.production.pipeline import ProductionPipeline


# ==============================================================================
# 1. UI GEOMETRY HARDENING TESTS
# ==============================================================================

def test_ui_geometry_css_invariants():
    """Verify CSS invariants in style.css and index.html to guarantee zero page blowout."""
    style_css_path = os.path.join("app", "frontend", "static", "style.css")
    assert os.path.exists(style_css_path), "style.css must exist"
    with open(style_css_path, "r", encoding="utf-8") as f:
        css = f.read()

    # 1. Main wrapper must not use fragile calc(100% - 250px)
    assert "width: calc(100% - 250px)" not in css, "Fragile width: calc(100% - 250px) must be eradicated"
    assert ".main-wrapper" in css
    assert "flex: 1 1 0" in css

    # 2. Dashboard grid must use CSS Grid with minmax(0, 1fr) 340px
    assert "grid-template-columns: minmax(0, 1fr) 340px;" in css
    # Fragile flexbox 72% / 28% must not exist
    assert "flex: 1 1 72%" not in css
    assert "flex: 0 0 28%" not in css

    # 3. Prospect layout grid must use resilient repeat(auto-fit, minmax(260px, 1fr))
    assert "repeat(auto-fit, minmax(260px, 1fr))" in css

    # 4. Modal content must use clamp sizing
    assert "max-width: clamp(320px, 92vw, 760px);" in css

    # 5. Live ops item and corridor rows must prevent blowout
    assert "overflow-wrap: anywhere;" in css
    assert "overflow: hidden !important;" in css

    # 6. Responsive breakpoint for dashboard collapse
    assert "@media (max-width: 1240px)" in css

    # Check index.html inline CSS as well
    index_html_path = os.path.join("app", "frontend", "templates", "index.html")
    assert os.path.exists(index_html_path), "index.html must exist"
    with open(index_html_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert "width: calc(100% - 240px)" not in html, "Fragile inline calc in index.html must be eradicated"
    assert "modal-request-changes" in html, "modal-request-changes must be in index.html"
    assert "modal-proposal-payment" in html, "modal-proposal-payment must be in index.html"
    assert "ceo-commercial-actions-bar" in html, "Commercial actions bar must be in index.html"


# ==============================================================================
# 2. COMMERCIAL PRICING ENGINE TESTS (4 INDUSTRIES & COMMERCIAL FLOOR)
# ==============================================================================

def test_commercial_pricing_engine_four_industries():
    """Verify deterministic pricing calculation across 4 industries with 40/60 milestone split."""
    industries = ["Automotive", "Dental", "Roofing", "HVAC"]
    for ind in industries:
        pricing = PricingEngine.calculate_pricing(
            industry=ind,
            selected_addons=["calendar_sync", "sms_notifications"]
        )
        assert pricing.total_price_usd >= 500.0, f"Total price must be >= $500 for {ind}"
        assert pricing.advance_deposit_usd == round(pricing.total_price_usd * 0.40, 2)
        assert pricing.balance_due_usd == round(pricing.total_price_usd * 0.60, 2)
        assert round(pricing.advance_deposit_usd + pricing.balance_due_usd, 2) == pricing.total_price_usd
        assert pricing.industry.lower() == ind.lower()


def test_commercial_pricing_engine_floor_enforcement():
    """Verify commercial floor of $500 is strictly enforced even if base price is tiny."""
    pricing = PricingEngine.calculate_pricing(
        industry="Unknown Tiny Niche",
        custom_base_price=150.0,
        selected_addons=[]
    )
    assert pricing.total_price_usd >= 500.0
    assert pricing.advance_deposit_usd >= 200.0


# ==============================================================================
# 3. DEMO ACCEPTANCE & PROPOSAL ENGINE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_demo_acceptance_and_proposal_generation():
    """Verify demo acceptance creates CustomerAcceptance and generates a valid ProjectProposal."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Apex Dental Care Test",
            domain="apexdentalcare-test.com",
            country="US",
            niche="Cosmetic & General Dentistry"
        )
        session.add(biz)
        await session.flush()

        proj = CustomerProject(
            project_id=f"proj_test_{int(datetime.utcnow().timestamp())}",
            business_id=biz.id,
            customer_slug="apex-dental-test",
            title="Apex Dental High-Conversion Web Portal",
            industry="Dental",
            status="DEMO_DELIVERED",
            current_stage="DEMO"
        )
        session.add(proj)
        await session.flush()

        spec = ProjectSpecification(
            project_id=proj.id,
            version=1,
            is_canonical=True,
            facts=[{"key": "services", "value": ["implants", "teeth whitening"]}],
            primary_language="typescript",
            framework="react"
        )
        session.add(spec)
        await session.commit()

        res = await AcceptanceHandler.accept_demo(
            session=session,
            project_id=proj.id,
            feedback_notes="The turnkey demo is accepted. Proceed to proposal and production.",
            actor="Apex Dental Management"
        )

        assert res["status"] == CustomerAcceptanceStatus.ACCEPTED.value
        assert res["project_id"] == proj.id
        assert "proposal" in res
        proposal_data = res["proposal"]
        assert proposal_data["total_price_usd"] >= 500.0
        assert proposal_data["advance_deposit_usd"] == round(proposal_data["total_price_usd"] * 0.40, 2)
        assert proposal_data["balance_due_usd"] == round(proposal_data["total_price_usd"] * 0.60, 2)

        p_stmt = select(ProjectProposal).where(ProjectProposal.project_id == proj.id)
        saved_prop = (await session.execute(p_stmt)).scalars().first()
        assert saved_prop is not None
        assert saved_prop.version == 1
        assert saved_prop.status == CommercialProposalStatus.PROPOSAL_GENERATED.value

        a_stmt = select(CustomerAcceptance).where(CustomerAcceptance.project_id == proj.id)
        saved_acc = (await session.execute(a_stmt)).scalars().first()
        assert saved_acc is not None
        assert saved_acc.status == CustomerAcceptanceStatus.ACCEPTED.value
        assert saved_acc.actor == "Apex Dental Management"


# ==============================================================================
# 4. CUSTOMER CHANGE REQUEST FEEDBACK LOOP (v1 -> v2 SPEC REBUILD)
# ==============================================================================

@pytest.mark.asyncio
async def test_customer_change_request_feedback_loop():
    """Verify requesting changes generates an immutable new spec version (v2) without mutating v1."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Vortex Roofing Test",
            domain="vortexroofing-test.com",
            country="US",
            niche="Commercial & Residential Roofing"
        )
        session.add(biz)
        await session.flush()

        proj = CustomerProject(
            project_id=f"proj_roof_{int(datetime.utcnow().timestamp())}",
            business_id=biz.id,
            customer_slug="vortex-roofing-test",
            title="Vortex Roofing Portal",
            industry="Roofing",
            status="DEMO_DELIVERED",
            current_stage="DEMO"
        )
        session.add(proj)
        await session.flush()

        v1_spec = ProjectSpecification(
            project_id=proj.id,
            version=1,
            is_canonical=True,
            facts=[{"key": "phone", "value": "555-0199"}],
            customer_requests=[{"request": "Include drone inspection booking"}],
            primary_language="typescript"
        )
        session.add(v1_spec)
        await session.commit()

        change_requests = [
            {"category": "color_scheme", "requested_change": "Change accent color from orange to slate navy (#1E293B)"},
            {"category": "features", "requested_change": "Add storm damage emergency inspection form"}
        ]
        res = await AcceptanceHandler.request_changes(
            session=session,
            project_id=proj.id,
            change_requests=change_requests,
            feedback_notes="Please update accent color and add storm damage emergency form.",
            actor="Vortex Roofing Owner"
        )

        assert res["status"] == CustomerAcceptanceStatus.CHANGES_REQUESTED.value
        assert res["new_specification_version"] == 2

        specs_stmt = select(ProjectSpecification).where(
            ProjectSpecification.project_id == proj.id
        ).order_by(ProjectSpecification.version.asc())
        specs = (await session.execute(specs_stmt)).scalars().all()
        assert len(specs) == 2
        assert specs[0].version == 1
        assert specs[0].is_canonical is False
        assert specs[1].version == 2
        assert specs[1].is_canonical is True
        req_texts = [r.get("request", "") for r in specs[1].customer_requests]
        assert any("slate navy" in t for t in req_texts)


# ==============================================================================
# 5. PAYMENT WORKFLOW & ANTI-FRAUD GATE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_google_pay_instructions_and_anti_fraud_verification():
    """Verify Google Pay payment instructions, strict anti-fraud rejection, and production unlock."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Reliable HVAC Pros Test",
            domain="reliablehvac-test.com",
            country="US",
            niche="HVAC Installation & Emergency Repair"
        )
        session.add(biz)
        await session.flush()

        proj = CustomerProject(
            project_id=f"proj_hvac_{int(datetime.utcnow().timestamp())}",
            business_id=biz.id,
            customer_slug="reliable-hvac-test",
            title="Reliable HVAC Fast Dispatch System",
            industry="HVAC",
            status="DEMO_ACCEPTED",
            current_stage="PROPOSAL"
        )
        session.add(proj)
        await session.flush()

        prop = ProjectProposal(
            project_id=proj.id,
            business_id=biz.id,
            proposal_id=f"prop_hvac_{int(datetime.utcnow().timestamp())}",
            version=1,
            total_price_usd=1200.0,
            advance_deposit_usd=480.0,
            balance_due_usd=720.0,
            status=CommercialProposalStatus.PROPOSAL_GENERATED.value
        )
        session.add(prop)
        await session.commit()

        instr = await PaymentWorkflowCoordinator.issue_proposal_payment_instructions(
            session=session,
            proposal_id=prop.id,
            provider_name="google_pay"
        )
        assert instr["status"] == "PAYMENT_PENDING"
        assert instr["amount_usd"] == 480.0
        assert instr["provider"] == "google_pay"
        payment_id = instr["payment_id"]

        untrusted_sources = ["customer_message", "screenshot", "ai_inference", "manual_claim", "unverified"]
        for bad_source in untrusted_sources:
            with pytest.raises(PermissionError) as exc_info:
                await PaymentWorkflowCoordinator.verify_payment(
                    session=session,
                    payment_id=payment_id,
                    verified_by="Client Claims",
                    transaction_reference="FAKE_UTR_123",
                    amount_received=480.0,
                    source=bad_source
                )
            assert "untrusted" in str(exc_info.value).lower()

        with pytest.raises(ValueError) as exc_info:
            await PaymentWorkflowCoordinator.verify_payment(
                session=session,
                payment_id=payment_id,
                verified_by="CEO_VERIFIER",
                transaction_reference="LEGIT_UTR_456",
                amount_received=200.0,
                source="CEO_VERIFICATION"
            )
        assert "underpayment rejected" in str(exc_info.value).lower()

        test_utr = f"UTR_TEST_{int(datetime.utcnow().timestamp())}"
        v_res = await PaymentWorkflowCoordinator.verify_payment(
            session=session,
            payment_id=payment_id,
            verified_by="CEO_VERIFIER",
            transaction_reference=test_utr,
            amount_received=480.0,
            source="CEO_VERIFICATION"
        )
        assert v_res["status"] == "VERIFIED_PAYMENT"
        assert v_res["delivery_unlocked"] is True
        assert v_res["production_project_id"] is not None
        prod_project_id = v_res["production_project_id"]

        pay2 = Payment(
            customer_id=1,
            business_id=biz.id,
            proposal_id=prop.id,
            amount=480.0,
            currency="USD",
            payment_type="ADVANCE_DEPOSIT",
            status="PAYMENT_PENDING",
            reference_id="pay_test_dup"
        )
        session.add(pay2)
        await session.commit()

        with pytest.raises(ValueError) as exc_info:
            await PaymentWorkflowCoordinator.verify_payment(
                session=session,
                payment_id=pay2.id,
                verified_by="CEO_VERIFIER",
                transaction_reference=test_utr,
                amount_received=480.0,
                source="CEO_VERIFICATION"
            )
        assert "fraud detected" in str(exc_info.value).lower() or "already been verified" in str(exc_info.value).lower()

        prod_proj = await session.get(ProductionProject, prod_project_id)
        assert prod_proj is not None
        assert prod_proj.is_payment_verified is True
        assert prod_proj.status == ProductionProjectStatus.UNLOCKED.value


# ==============================================================================
# 6. PRODUCTION PIPELINE EXECUTION (BUILD, 10-GATE QA, DEPLOY, HANDOVER)
# ==============================================================================

@pytest.mark.asyncio
async def test_production_pipeline_complete_lifecycle():
    """Verify production build, 10-gate QA, deployment, and customer handover documentation."""
    async with AsyncSessionLocal() as session:
        biz = Business(
            name="Precision Auto Body Test",
            domain="precisionautobody-test.com",
            country="US",
            niche="Collision Repair & Fleet Service"
        )
        session.add(biz)
        await session.flush()

        proj = CustomerProject(
            project_id=f"proj_auto_{int(datetime.utcnow().timestamp())}",
            business_id=biz.id,
            customer_slug="precision-auto-test",
            title="Precision Auto Body Operations Portal",
            industry="Automotive",
            status="DEMO_ACCEPTED"
        )
        session.add(proj)
        await session.flush()

        spec = ProjectSpecification(
            project_id=proj.id,
            version=1,
            is_canonical=True,
            facts=[{"key": "fleet_dispatch", "value": "Active 24/7"}],
            primary_language="typescript",
            framework="react"
        )
        session.add(spec)
        await session.flush()

        prod_proj = ProductionProject(
            project_id=proj.id,
            business_id=biz.id,
            production_slug="precision-auto-test",
            is_payment_verified=True,
            status=ProductionProjectStatus.UNLOCKED.value
        )
        session.add(prod_proj)
        await session.commit()

        # Step 1: Production Build
        b_res = await ProductionPipeline.build_production(session=session, production_project_id=prod_proj.id)
        assert b_res["status"] == "SUCCESS"
        assert b_res["clean_packaging"] is True
        assert b_res["routes_count"] >= 3
        assert os.path.exists(b_res["artifact_path"]), f"Production artifact must exist at {b_res['artifact_path']}"
        assert not b_res["demo_watermark_detected"], "Production artifact must not contain demo watermarks"

        # Step 2: 10-Gate Production QA
        q_res = await ProductionPipeline.run_production_qa(session=session, production_project_id=prod_proj.id)
        assert q_res["status"] == "PASSED"
        assert q_res["passed_gates"] == 10
        assert q_res["total_gates"] == 10
        assert q_res["passed"] is True
        assert len(q_res["qa_signature"]) >= 8

        # Step 3: Production Deployment
        d_res = await ProductionPipeline.deploy_production(session=session, production_project_id=prod_proj.id)
        assert d_res["status"] == "DEPLOYED"
        assert d_res["live_url"].startswith("http")

        # Step 4: Customer Handover
        h_res = await ProductionPipeline.generate_handover_package(session=session, production_project_id=prod_proj.id)
        assert h_res["handover_slug"] == "precision-auto-test"
        assert os.path.exists(h_res["handover_dir"])
        assert "zero_secrets_exposed" in h_res["security_attestation"].lower() or "audited" in h_res["security_attestation"].lower()

        # Step 5: Check Status Endpoint
        status_data = await ProductionPipeline.get_production_status(session=session, production_project_id=prod_proj.id)
        assert status_data["is_payment_verified"] is True
        assert status_data["status"] == ProductionProjectStatus.HANDOVER_DELIVERED.value
        assert status_data["latest_qa"]["score"] == 100.0


# ==============================================================================
# 7. ORANGE AUTO CANARY ISOLATION GUARANTEE
# ==============================================================================

@pytest.mark.asyncio
async def test_orange_auto_canary_remains_approved_and_unmodified():
    """Verify Orange Auto Canary (#12, Business 30) is intact in APPROVED status and has not been dispatched."""
    async with AsyncSessionLocal() as session:
        msg = await session.get(OutreachMessage, 12)
        if msg is not None:
            assert msg.status == "APPROVED", "OutreachMessage #12 status MUST be APPROVED"
            assert msg.sent_at is None, "OutreachMessage #12 must NEVER have been sent/dispatched in tests"
            assert msg.business_id == 30

        biz_30 = await session.get(Business, 30)
        if biz_30 is not None:
            assert "orange auto" in (biz_30.name or "").lower(), "Business #30 must be Orange Auto"
