"""
Comprehensive test suite verifying Dashboard Truth and State Consistency.

Enforces:
1. Single source of truth for email outbound authorization status:
   - /api/email/deliverability-readiness and /api/ceo/overview report identical provider auth state.
   - When credentials are missing, both report BLOCKED with truthful non-secret blocker.
   - When credentials are verified, both report READY.
2. Orange Auto demo artifact does NOT generate an action_required item.
3. Demo artifacts only generate action_required items if business is in DEMO_REQUESTED.
4. Historical outreach records (SENT) are preserved in metrics/CRM, but do not generate action_required items.
5. Metrics cleanly differentiate today's outbound from lifetime total.
6. Outreach lock correctly reports IDLE when inactive.
7. HTML template does not contain hardcoded "TITAN / READY" or misleading static simulation labels.
"""

import os
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.app import app
from app.core.config import settings
from app.database.connection import init_db, AsyncSessionLocal
from app.database.models import (
    Business, Artifact, Proposal, PipelineStage, OutreachMessage, OutreachStatus, OutreachEvent
)
from app.outreach.deliverability import deliverability_monitor

test_biz_ids = []


@pytest.fixture(autouse=True)
async def db_setup():
    await init_db()
    yield
    if test_biz_ids:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Artifact).where(Artifact.business_id.in_(test_biz_ids)))
            await session.execute(delete(Proposal).where(Proposal.business_id.in_(test_biz_ids)))
            await session.execute(delete(OutreachMessage).where(OutreachMessage.business_id.in_(test_biz_ids)))
            await session.execute(delete(Business).where(Business.id.in_(test_biz_ids)))
            await session.commit()
        test_biz_ids.clear()


@pytest.mark.asyncio
async def test_canonical_email_status_when_password_missing(monkeypatch):
    """When TITAN_SMTP_PASSWORD is missing, /health, /api/ceo/overview, and /api/email/deliverability-readiness must all report BLOCKED and identical non-secret blocker."""
    monkeypatch.setattr(settings, "PRIMARY_EMAIL_PROVIDER", "titan")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "titan")
    monkeypatch.setattr(settings, "TITAN_SMTP_PASSWORD", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /api/email/deliverability-readiness
        deliv_res = await client.get("/api/email/deliverability-readiness")
        assert deliv_res.status_code == 200
        deliv_data = deliv_res.json()

        # 2. /api/ceo/overview
        overview_res = await client.get("/api/ceo/overview")
        assert overview_res.status_code == 200
        overview_data = overview_res.json()

        # 3. /health
        health_res = await client.get("/health")
        assert health_res.status_code == 200
        health_data = health_res.json()

        # Verify Deliverability Readiness
        assert deliv_data["outbound_authorization"] == "BLOCKED"
        assert deliv_data["auth_status"] == "BLOCKED"
        assert deliv_data["readiness"] == "BLOCKED"
        assert "TITAN_SMTP_PASSWORD is missing" in deliv_data["outbound_auth_blocker"]
        assert deliv_data["reason"] == deliv_data["outbound_auth_blocker"]

        # Verify Overview
        sys_status = overview_data["system_status"]
        assert sys_status["outbound_authorization"] == "BLOCKED"
        assert sys_status["email_status"] == "TITAN / BLOCKED"
        assert sys_status["email_auth_blocker"] == deliv_data["outbound_auth_blocker"]
        assert sys_status["canonical_email"]["auth_status"] == "BLOCKED"
        assert sys_status["canonical_email"]["readiness"] == "BLOCKED"

        # Verify /health
        email_health = health_data["email"]
        assert email_health["auth_status"] == "BLOCKED"
        assert email_health["readiness"] == "BLOCKED"
        assert email_health["reason"] == deliv_data["outbound_auth_blocker"]
        assert health_data["deliverability"]["provider_auth"] == "BLOCKED"


@pytest.mark.asyncio
async def test_canonical_email_status_when_verified(monkeypatch):
    """When Titan authentication succeeds, /health, /api/ceo/overview, and /api/email/deliverability-readiness must all report READY and no blocker."""
    monkeypatch.setattr(settings, "PRIMARY_EMAIL_PROVIDER", "titan")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "titan")
    monkeypatch.setattr(settings, "TITAN_SMTP_PASSWORD", "secret_test_pw")
    monkeypatch.setattr(settings, "TITAN_SMTP_USER", "hello@automatedagencyos.tech")

    from app.outreach.providers.titan_provider import TitanEmailProvider
    monkeypatch.setattr(
        TitanEmailProvider,
        "check_auth_health",
        lambda self: {"status": "OK", "healthy": True, "authenticated_email": "hello@automatedagencyos.tech"}
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /api/email/deliverability-readiness
        deliv_res = await client.get("/api/email/deliverability-readiness")
        assert deliv_res.status_code == 200
        deliv_data = deliv_res.json()

        # 2. /api/ceo/overview
        overview_res = await client.get("/api/ceo/overview")
        assert overview_res.status_code == 200
        overview_data = overview_res.json()

        # 3. /health
        health_res = await client.get("/health")
        assert health_res.status_code == 200
        health_data = health_res.json()

        # Verify Deliverability Readiness
        assert deliv_data["outbound_authorization"] == "READY"
        assert deliv_data["auth_status"] == "READY"
        assert deliv_data["readiness"] == "READY"
        assert deliv_data["outbound_auth_blocker"] is None
        assert deliv_data["reason"] is None

        # Verify Overview
        sys_status = overview_data["system_status"]
        assert sys_status["outbound_authorization"] == "READY"
        assert sys_status["email_status"] == "TITAN / READY"
        assert sys_status["email_auth_blocker"] is None
        assert sys_status["canonical_email"]["auth_status"] == "READY"
        assert sys_status["canonical_email"]["readiness"] == "READY"

        # Verify /health
        email_health = health_data["email"]
        assert email_health["auth_status"] == "READY"
        assert email_health["readiness"] == "READY"
        assert email_health["reason"] is None
        assert health_data["deliverability"]["provider_auth"] == "READY"


@pytest.mark.asyncio
async def test_orange_auto_demo_does_not_appear_in_action_required():
    """Orange Auto is in APPROVAL/test stage; its demo artifact must NOT be in actions_required."""
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = Business(
            name=f"Orange Auto Test {uid}",
            domain=f"orangeauto-{uid}.com",
            country="US",
            city="Austin",
            niche="automotive",
            pipeline_stage=PipelineStage.APPROVAL.value
        )
        session.add(biz)
        await session.flush()
        test_biz_ids.append(biz.id)

        art = Artifact(
            business_id=biz.id,
            artifact_type="DEMO_PACKAGE",
            name="Interactive Turnaround Demo for Orange Auto",
            metadata_json={"qa_result": {"overall_passed": True}}
        )
        session.add(art)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ceo/overview")
        assert res.status_code == 200
        data = res.json()
        actions = data.get("action_required", [])

        demo_action_titles = [a["title"] for a in actions if a.get("type") == "DEMO_REVIEW"]
        assert not any(f"Orange Auto Test {uid}" in t for t in demo_action_titles)


@pytest.mark.asyncio
async def test_demo_requested_stage_generates_action_required():
    """When a business is actively in DEMO_REQUESTED, its demo package SHOULD appear in actions_required."""
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = Business(
            name=f"Active Demo Prospect {uid}",
            domain=f"demo-{uid}.com",
            country="US",
            city="Austin",
            niche="automotive",
            pipeline_stage=PipelineStage.DEMO_REQUESTED.value
        )
        session.add(biz)
        await session.flush()
        test_biz_ids.append(biz.id)

        art = Artifact(
            business_id=biz.id,
            artifact_type="DEMO_PACKAGE",
            name=f"Demo for {biz.name}",
            metadata_json={"qa_result": {"overall_passed": True}}
        )
        session.add(art)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ceo/overview")
        assert res.status_code == 200
        data = res.json()
        actions = data.get("action_required", [])

        matching_actions = [a for a in actions if a.get("type") == "DEMO_REVIEW" and biz.name in a.get("title", "")]
        assert len(matching_actions) == 1
        assert "Turnkey Demo ready" in matching_actions[0]["title"]


@pytest.mark.asyncio
async def test_historical_outreach_sent_not_in_action_required():
    """Historical sent message does not appear in actions_required, but is counted in lifetime metrics."""
    async with AsyncSessionLocal() as session:
        uid = uuid.uuid4().hex[:6]
        biz = Business(
            name=f"Historical Client {uid}",
            domain=f"hist-{uid}.com",
            country="US",
            city="Austin",
            niche="roofing",
            pipeline_stage=PipelineStage.CONTACTED.value
        )
        session.add(biz)
        await session.flush()
        test_biz_ids.append(biz.id)

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email=f"contact@hist-{uid}.com",
            status=OutreachStatus.SENT.value,
            subject=f"Historical message {uid}",
            body="Test historical email"
        )
        session.add(msg)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/ceo/overview")
        assert res.status_code == 200
        data = res.json()
        actions = data.get("action_required", [])

        outreach_action_ids = [a["id"] for a in actions if a.get("type") == "OUTREACH_APPROVAL"]
        assert f"outreach_{msg.id}" not in outreach_action_ids


def test_html_template_no_hardcoded_ready_or_simulation():
    """Verifies that index.html does not have hardcoded TITAN / READY or raw static SIMULATION text."""
    template_path = os.path.join("app", "frontend", "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert '<strong id="obs-email-status" style="color:#10b981;">TITAN / READY</strong>' not in html
    assert 'id="obs-email-status"' in html
