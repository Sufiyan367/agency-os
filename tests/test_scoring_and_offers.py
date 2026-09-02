import pytest
from app.database.models import Business, AuditRun
from app.auditing.engine import website_audit_engine
from app.scoring.engine import lead_scoring_engine
from app.offers.generator import offer_engine

@pytest.mark.asyncio
async def test_scoring_and_offer_generation(db_session):
    biz = Business(
        name="Test Dental Clinic",
        domain="testdental.com",
        website_url="https://testdental.com",
        country="US",
        niche="dental-practices",
        public_email="office@testdental.com"
    )
    db_session.add(biz)
    await db_session.commit()

    # Audit first
    await website_audit_engine.audit_business(db_session, biz)

    # Score
    lead_score = await lead_scoring_engine.score_business(db_session, biz)
    assert lead_score.total_score >= 0.0 and lead_score.total_score <= 100.0
    assert lead_score.priority in ("A", "B", "C", "LOW")
    assert "Lead Score:" in lead_score.rationale
    assert biz.pipeline_stage in ("QUALIFIED", "AUDITED")

    # Offer
    offer = await offer_engine.generate_offer_for_business(db_session, biz)
    assert offer.recommended_price >= 400.0
    assert len(offer.deliverables) > 0
    assert len(offer.title) > 5
