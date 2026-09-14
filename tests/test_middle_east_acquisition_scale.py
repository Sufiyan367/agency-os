import pytest
import os
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from app.core.config import settings
from app.campaigns.config import campaign_config_loader
from app.campaigns.quota_engine import quota_engine
from app.acquisition.config import DEFAULT_COUNTRY_PROFILES
from app.lead_generation.adapters.real_web_discovery import EXPANDED_CITIES, NICHE_SEARCH_MAP
from app.database.models import ActiveOutreachLock, OutreachMessage, Business, SuppressionList, OutreachStatus
from app.models.entities import Lead
from app.acquisition.controller import active_prospect_controller
from app.acquisition.autonomous_controller import autonomous_acquisition_controller
from app.services.outreach import OutreachService


@pytest.mark.asyncio
async def test_middle_east_daily_capacity_is_70():
    """Verify that daily capacity cap is 70 for verified business outreach."""
    assert settings.MAX_OUTREACH_PER_DAY == 70

    # Check rollout level 6 in campaign config
    level_6 = campaign_config_loader._rollout_levels[6]
    assert level_6.daily_max_real_emails == 70


@pytest.mark.asyncio
async def test_middle_east_country_and_city_matrix():
    """Verify Middle East country coverage and city definitions."""
    me_countries = ["SA", "AE", "QA", "KW", "OM", "BH"]
    
    # Check acquisition config country profiles
    for code in me_countries:
        assert code in DEFAULT_COUNTRY_PROFILES, f"Market {code} missing from DEFAULT_COUNTRY_PROFILES"
        profile = DEFAULT_COUNTRY_PROFILES[code]
        assert len(profile["target_cities"]) >= 4, f"Market {code} has fewer than 4 cities"
        assert len(profile["target_niches"]) >= 5, f"Market {code} has fewer than 5 priority niches"

    # Check real web discovery expanded cities
    for code in me_countries:
        assert code in EXPANDED_CITIES, f"Market {code} missing from EXPANDED_CITIES"
        cities = EXPANDED_CITIES[code]
        assert len(cities) >= 4

    # Verify specific key cities
    assert "Riyadh" in EXPANDED_CITIES["SA"]
    assert "Al Khobar" in EXPANDED_CITIES["SA"]
    assert "Dubai" in EXPANDED_CITIES["AE"]
    assert "Abu Dhabi" in EXPANDED_CITIES["AE"]
    assert "Doha" in EXPANDED_CITIES["QA"]
    assert "Kuwait City" in EXPANDED_CITIES["KW"]
    assert "Muscat" in EXPANDED_CITIES["OM"]
    assert "Manama" in EXPANDED_CITIES["BH"]


@pytest.mark.asyncio
async def test_middle_east_high_value_niches():
    """Verify priority service niches are mapped for discovery."""
    priority_niches = [
        "hvac", "hvac-services", "roofing", "plumbing", "electrical",
        "dental-clinics", "aesthetic-clinics", "medical-clinics",
        "real-estate", "property-services", "automotive"
    ]
    for niche in priority_niches:
        assert niche in NICHE_SEARCH_MAP, f"Niche {niche} not in NICHE_SEARCH_MAP"


@pytest.mark.asyncio
async def test_active_outreach_lock_freed_after_send(db_session):
    """
    Verify that ActiveOutreachLock is released (IDLE) after dispatch,
    ensuring no single-prospect bottleneck blocks subsequent candidates.
    """
    biz = Business(
        name="Gulf HVAC Solutions",
        domain="gulfhvac.example.com",
        country="AE",
        niche="hvac",
        pipeline_stage="OUTREACH_READY"
    )
    db_session.add(biz)
    await db_session.flush()

    msg = OutreachMessage(
        business_id=biz.id,
        recipient_email="contact@gulfhvac.example.com",
        subject="Optimizing HVAC response latency",
        body="B2B automation opportunity proposal.",
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.flush()

    # Slot claimed initially
    lock = await active_prospect_controller.get_or_create_lock(db_session)
    lock.business_id = biz.id
    lock.status = "ACTIVE"
    lock.current_stage = "APPROVED"
    await db_session.commit()

    # Dispatch using dry-run sender
    res = await active_prospect_controller.approve_and_send(
        session=db_session,
        business_id=biz.id,
        message_id=msg.id,
        force_live=False
    )

    assert res["status"] == "SENT"
    assert res["lock_status"] == "IDLE"

    # Verify lock in database is IDLE
    fresh_lock = await active_prospect_controller.get_or_create_lock(db_session)
    assert fresh_lock.status == "IDLE"


@pytest.mark.asyncio
async def test_sent_stage_does_not_block_pipeline(db_session):
    """
    Verify that when a prospect is already dispatched, the autonomous controller
    releases the slot so the pipeline advances to the next candidate.
    """
    biz = Business(
        name="Riyadh Dental Clinic",
        domain="riyadhdental.example.sa",
        country="SA",
        niche="dental-clinics",
        pipeline_stage="SENT"
    )
    db_session.add(biz)
    await db_session.flush()

    lock = await active_prospect_controller.get_or_create_lock(db_session)
    lock.business_id = biz.id
    lock.status = "IDLE"
    lock.current_stage = "SENT"
    await db_session.commit()

    # Running autonomous cycle with a SENT prospect should release slot
    cycle_res = await autonomous_acquisition_controller.advance_cycle_step(db_session)
    assert cycle_res["status"] in ("RELEASED_AFTER_SEND", "SELECTED", "NO_CANDIDATE")

    # Slot should now be released
    fresh_lock = await active_prospect_controller.get_or_create_lock(db_session)
    assert fresh_lock.status in ("IDLE", "ACTIVE")
    if fresh_lock.status == "IDLE":
        assert fresh_lock.business_id is None


@pytest.mark.asyncio
async def test_suppression_blocks_outreach_dispatch(db_session):
    """Verify that suppressed prospects cannot be dispatched."""
    from app.outreach.compliance import compliance_guard
    from app.models.entities import LocalBusiness, LocalLead, LocalOutreachMessage

    suppressed_email = "optout@dohaclinic.example.qa"
    await compliance_guard.add_to_suppression(
        session=db_session,
        email=suppressed_email,
        reason="UNSUBSCRIBE"
    )

    is_supp = await compliance_guard.is_suppressed(db_session, email=suppressed_email)
    assert is_supp is True

    # Attempt send via OutreachService should raise ValueError
    outreach_svc = OutreachService()
    lbiz = LocalBusiness(
        name="Doha Clinic",
        domain="dohaclinic.example.qa",
        niche="healthcare",
        email=suppressed_email
    )
    db_session.add(lbiz)
    await db_session.flush()

    lead = LocalLead(
        business_id=lbiz.id,
        contact_name="Doctor",
        contact_email=suppressed_email,
        status="NEW",
        lead_score=75.0,
        qualification="QUALIFIED"
    )
    db_session.add(lead)
    await db_session.flush()

    msg = LocalOutreachMessage(
        lead_id=lead.id,
        recipient=suppressed_email,
        channel="EMAIL",
        subject="Hello",
        body="Test message",
        status="DRAFTED"
    )
    db_session.add(msg)
    await db_session.commit()

    with pytest.raises(ValueError, match="suppression list"):
        await outreach_svc.approve_and_send(db_session, msg.id)


@pytest.mark.asyncio
async def test_daily_quota_blocks_excess_sends(db_session):
    """Verify that reaching daily quota prevents additional sends."""
    from app.outreach.compliance import compliance_guard
    from app.models.entities import LocalBusiness, LocalLead, LocalOutreachMessage

    with patch.object(settings, "MAX_OUTREACH_PER_DAY", 0):
        can_send = await compliance_guard.can_send_today(db_session)
        assert can_send is False

        outreach_svc = OutreachService()
        lbiz = LocalBusiness(
            name="Kuwait Services",
            domain="kuwaitservices.example.kw",
            niche="home-services",
            email="valid@kuwaitservices.example.kw"
        )
        db_session.add(lbiz)
        await db_session.flush()

        lead = LocalLead(
            business_id=lbiz.id,
            contact_name="Manager",
            contact_email="valid@kuwaitservices.example.kw",
            status="NEW",
            lead_score=80.0,
            qualification="QUALIFIED"
        )
        db_session.add(lead)
        await db_session.flush()

        msg = LocalOutreachMessage(
            lead_id=lead.id,
            recipient="valid@kuwaitservices.example.kw",
            channel="EMAIL",
            subject="Hello",
            body="Test body",
            status="DRAFTED"
        )
        db_session.add(msg)
        await db_session.commit()

        with pytest.raises(ValueError, match="Daily outreach quota"):
            await outreach_svc.approve_and_send(db_session, msg.id)
