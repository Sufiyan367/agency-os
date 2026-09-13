import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.app import app
from app.database.connection import get_db
from app.database.models import (
    Business, Offer, OutreachMessage, OutreachStatus, SuppressionList, ActiveOutreachLock
)
from app.core.security import create_session_token
from app.core.config import settings
from app.outreach.auto_approval import auto_approval_engine
from app.outreach.sender import outreach_sender_adapter
from app.acquisition.controller import active_prospect_controller

# 1. Eligible outreach auto-approves
@pytest.mark.asyncio
async def test_eligible_outreach_auto_approves(db_session: AsyncSession):
    biz = Business(name="Auto Approve Corp", domain="autoapprove123.com", country="US", niche="Technology Services")
    db_session.add(biz)
    await db_session.flush()

    offer = Offer(business_id=biz.id, service_type="WEB_DEV", title="Platform Audit", recommended_price=750.0)
    db_session.add(offer)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        offer_id=offer.id,
        recipient_email="director@autoapprove123.com",
        subject="Technical Audit: Auto Approve Corp",
        body="We analyzed autoapprove123.com and identified opportunities to improve your mobile performance.",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    success, updated_msg, eval_res = await auto_approval_engine.auto_approve_if_eligible(db_session, msg.id)
    assert success is True
    assert updated_msg.status == OutreachStatus.APPROVED.value
    assert updated_msg.actor_type == "SYSTEM_AUTO_APPROVAL"
    assert updated_msg.approved_at is not None

# 2. Auto-approved eligible outreach can proceed to authorized send without second manual approval
@pytest.mark.asyncio
async def test_auto_approved_eligible_can_proceed_to_authorized_send(db_session: AsyncSession):
    biz = Business(name="Autonomous Flow Inc", domain="autoflow456.com", country="US", niche="Technology Services")
    db_session.add(biz)
    await db_session.flush()

    offer = Offer(business_id=biz.id, service_type="WEB_DEV", title="Workflow Upgrade", recommended_price=800.0)
    db_session.add(offer)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        offer_id=offer.id,
        recipient_email="ops@autoflow456.com",
        subject="Diagnostic Findings",
        body="Here are observations regarding autoflow456.com performance.",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    # Step 1: Auto-approve
    success, approved_msg, _ = await auto_approval_engine.auto_approve_if_eligible(db_session, msg.id)
    assert success is True
    assert approved_msg.actor_type == "SYSTEM_AUTO_APPROVAL"

    # Step 2: Send approved message (dry-run or live-simulated)
    res = await outreach_sender_adapter.send_approved_message(db_session, approved_msg.id, force_live=False)
    assert res.get("status") in ("sent", "SENT", "SUCCESS")
    assert approved_msg.status == OutreachStatus.SENT.value
    assert approved_msg.sent_at is not None

# 3. Ineligible outreach remains blocked
@pytest.mark.asyncio
async def test_ineligible_outreach_remains_blocked(db_session: AsyncSession):
    biz = Business(name="Ineligible Corp", domain="ineligible789.com", country="US", niche="Technology Services")
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="bad@ineligible789.com",
        subject="Get rich quick",
        body="We offer a 100% money back guarantee and guaranteed 10x return!",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    success, updated_msg, eval_res = await auto_approval_engine.auto_approve_if_eligible(db_session, msg.id)
    assert success is False
    assert updated_msg.status == OutreachStatus.PENDING_APPROVAL.value
    assert any("prohibited claims" in r.lower() for r in eval_res.blocking_reasons)

# 4. Opted-out lead cannot send
@pytest.mark.asyncio
async def test_opted_out_lead_cannot_send(db_session: AsyncSession):
    biz = Business(name="Opted Out LLC", domain="optedout123.com", country="US", niche="Technology Services")
    db_session.add(biz)
    await db_session.flush()

    supp = SuppressionList(email="unsub@optedout123.com", reason="UNSUBSCRIBE")
    db_session.add(supp)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="unsub@optedout123.com",
        subject="Inquiry",
        body="Hello there.",
        status=OutreachStatus.APPROVED.value,
        actor_type="SYSTEM_AUTO_APPROVAL"
    )
    db_session.add(msg)
    await db_session.commit()

    with pytest.raises(ValueError, match="previously opted out|suppressed"):
        await outreach_sender_adapter.send_approved_message(db_session, msg.id)

# 5. Duplicate send cannot occur
@pytest.mark.asyncio
async def test_duplicate_send_cannot_occur(db_session: AsyncSession):
    biz = Business(name="Dup Test LLC", domain="duptest123.com", country="US", niche="Technology Services")
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="ceo@duptest123.com",
        subject="Audit",
        body="Audit body content.",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()

    # First send succeeds
    res1 = await outreach_sender_adapter.send_approved_message(db_session, msg.id)
    assert res1.get("status") in ("sent", "SENT", "SUCCESS")
    assert msg.status == OutreachStatus.SENT.value

    # Second send attempt is blocked
    with pytest.raises(ValueError, match="already been sent|Duplicate dispatch is prohibited"):
        await outreach_sender_adapter.send_approved_message(db_session, msg.id)

# 6. Daily cap prevents additional send
@pytest.mark.asyncio
async def test_daily_cap_prevents_additional_send(db_session: AsyncSession):
    biz = Business(name="Cap Test Corp", domain="captest123.com", country="US", niche="Technology Services")
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="contact@captest123.com",
        subject="Audit",
        body="Audit body.",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()

    with patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new_callable=AsyncMock) as mock_cap:
        mock_cap.return_value = {"available_capacity": 0, "sent_today": 1, "rollout_daily_cap": 1, "rollout_stage_name": "Canary"}
        with pytest.raises(ValueError, match="Daily sender capacity exhausted|Daily rollout capacity exhausted"):
            await outreach_sender_adapter.send_approved_message(db_session, msg.id, force_live=True)

# 7. ActiveOutreachLock prevents concurrent send
@pytest.mark.asyncio
async def test_active_outreach_lock_prevents_concurrent_send(db_session: AsyncSession):
    biz = Business(name="Lock Test Corp", domain="locktest123.com", country="US", niche="Technology Services")
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="exec@locktest123.com",
        subject="Audit",
        body="Audit body.",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()

    # Hold the lock
    lock = await active_prospect_controller.get_or_create_lock(db_session)
    lock.status = "HELD"
    await db_session.commit()

    with pytest.raises(ValueError, match="ActiveOutreachLock is currently held|ActiveOutreachLock is held"):
        await outreach_sender_adapter.send_approved_message(db_session, msg.id, force_live=True)

# 8. Provider failure produces send_failed, not SENT
@pytest.mark.asyncio
async def test_provider_failure_produces_send_failed_not_sent(db_session: AsyncSession):
    biz = Business(name="Fail Test Corp", domain="failtest123.com", country="US", niche="Technology Services")
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="fail@failtest123.com",
        subject="Audit",
        body="Audit body.",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()

    with patch("app.outreach.sender.get_email_provider") as mock_prov:
        prov_instance = AsyncMock()
        prov_instance.send_email.side_effect = RuntimeError("SMTP connection dropped by peer")
        mock_prov.return_value = prov_instance

        with pytest.raises(RuntimeError, match="Email delivery failed"):
            await outreach_sender_adapter.send_approved_message(db_session, msg.id, force_live=False)

        assert msg.status == OutreachStatus.FAILED.value
        assert msg.sent_at is None

# 9. Approval endpoint does not return generic 500 for deterministic policy blocks
@pytest.mark.asyncio
async def test_approval_endpoint_does_not_return_500_for_policy_block(db_session: AsyncSession):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        biz = Business(name="Blocked Lead LLC", domain="blockedlead.com", country="US", niche="Technology Services")
        db_session.add(biz)
        await db_session.flush()

        # Suppressed lead
        supp = SuppressionList(email="blocked@blockedlead.com", reason="UNSUBSCRIBE")
        db_session.add(supp)
        await db_session.flush()

        msg = OutreachMessage(
            business_id=biz.id,
            recipient_email="blocked@blockedlead.com",
            subject="Audit",
            body="Body.",
            status=OutreachStatus.PENDING_APPROVAL.value
        )
        db_session.add(msg)
        await db_session.commit()

        token = create_session_token("admin", "admin")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                f"/api/queue/{msg.id}/approve",
                json={"force_live": True, "auto_send": True, "actor": "HUMAN"},
                headers={"Cookie": f"agency_session={token}"}
            )
            # Must return 200 with status=blocked (NEVER 500!)
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "blocked"
            assert "reason" in data
    finally:
        app.dependency_overrides.clear()

# 10. SYSTEM_AUTO_APPROVAL is recorded correctly
@pytest.mark.asyncio
async def test_system_auto_approval_recorded_correctly(db_session: AsyncSession):
    biz = Business(name="Actor Record LLC", domain="actorrecord.com", country="US", niche="Technology Services")
    db_session.add(biz)
    await db_session.flush()

    offer = Offer(business_id=biz.id, service_type="WEB_DEV", title="Audit", recommended_price=600.0)
    db_session.add(offer)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        offer_id=offer.id,
        recipient_email="ops@actorrecord.com",
        subject="Audit: Actor Record",
        body="Technical overview for your digital systems.",
        status=OutreachStatus.PENDING_APPROVAL.value
    )
    db_session.add(msg)
    await db_session.commit()

    success, approved_msg, _ = await auto_approval_engine.auto_approve_if_eligible(db_session, msg.id)
    assert success is True
    assert approved_msg.actor_type == "SYSTEM_AUTO_APPROVAL"

# 11. /api/ml/health works when NumPy is installed
@pytest.mark.asyncio
async def test_ml_health_endpoint_response(db_session: AsyncSession):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_session_token("admin", "admin")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get(
                "/api/ml/health",
                headers={"Cookie": f"agency_session={token}"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "SUCCESS"
            assert "health" in data
            assert "composite_health_score" in data["health"]
    finally:
        app.dependency_overrides.clear()

# 12. /api/ml/health returns safe degraded status if dependency is unavailable
@pytest.mark.asyncio
async def test_ml_health_degraded_fallback_without_crash(db_session: AsyncSession):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    try:
        token = create_session_token("admin", "admin")
        transport = ASGITransport(app=app)
        with patch("app.ml.health_service.model_health_service.get_model_health", side_effect=ModuleNotFoundError("numpy")):
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get(
                    "/api/ml/health",
                    headers={"Cookie": f"agency_session={token}"}
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["status"] == "SUCCESS"
                assert data["health"]["status"] == "DEGRADED"
                assert data["health"]["active_scoring_engine"] == "HEURISTIC_RULE_FALLBACK"
                assert data["health"]["missing_dependency"] == "numpy"
    finally:
        app.dependency_overrides.clear()
