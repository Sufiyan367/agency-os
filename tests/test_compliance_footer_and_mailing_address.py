import pytest
from email import message_from_bytes
from email.mime.text import MIMEText
from app.core.config import settings
from app.database.models import Business, OutreachMessage, Campaign, OutreachStatus
from app.outreach.compliance import compliance_guard
from app.outreach.sender import outreach_sender_adapter
from app.campaigns.sender_registry import sender_registry
from app.outreach.providers.titan_provider import TitanEmailProvider

@pytest.mark.asyncio
async def test_compliance_footer_renders_configured_business_address_and_unsubscribe(monkeypatch):
    approved_address = "Agency OS Operations, 548 Market St, Suite 34291, San Francisco, CA 94104, USA"
    monkeypatch.setattr(settings, "PHYSICAL_POSTAL_ADDRESS", approved_address)
    monkeypatch.setattr(settings, "CAN_SPAM_POSTAL_ADDRESS", None)

    footer = compliance_guard.format_compliance_footer(
        business_name="Acme Corp",
        recipient_email="test@example.com",
        postal_address=None,
        force=True
    )

    assert f"Mailing Address: {approved_address}" in footer
    assert "To opt out of future communications, reply 'unsubscribe'." in footer
    assert "Digital Strategy Advisory" not in footer
    assert "Al Faisaliah" not in footer
    assert "Riyadh" not in footer


@pytest.mark.asyncio
async def test_legacy_saudi_address_in_campaign_is_blocked_from_footer(monkeypatch):
    stale_address = "Digital Strategy Advisory, Level 14, Al Faisaliah Tower, King Fahd Rd, Riyadh 12212, Saudi Arabia"
    approved_address = "Agency OS Operations, 548 Market St, Suite 34291, San Francisco, CA 94104, USA"
    monkeypatch.setattr(settings, "PHYSICAL_POSTAL_ADDRESS", approved_address)

    footer = compliance_guard.format_compliance_footer(
        business_name="Acme Corp",
        recipient_email="test@example.com",
        postal_address=stale_address,
        force=True
    )

    assert "Al Faisaliah" not in footer
    assert "Digital Strategy Advisory" not in footer
    assert "Riyadh" not in footer
    assert f"Mailing Address: {approved_address}" in footer
    assert "reply 'unsubscribe'" in footer


@pytest.mark.asyncio
async def test_outbound_mime_body_contains_approved_address_and_no_faisaliah(db_session, monkeypatch):
    approved_address = "Agency OS Operations, 548 Market St, Suite 34291, San Francisco, CA 94104, USA"
    monkeypatch.setattr(settings, "PHYSICAL_POSTAL_ADDRESS", approved_address)
    monkeypatch.setattr(settings, "EMAIL_DRY_RUN", True)
    monkeypatch.setattr(settings, "DRY_RUN", True)

    biz = Business(
        name="Reliable Roofing Inc",
        domain="reliableroofingtest.com",
        country="US",
        city="Austin",
        niche="roofing",
        public_email="contact@reliableroofingtest.com"
    )
    db_session.add(biz)
    await db_session.commit()
    await db_session.refresh(biz)

    stale_address = "Digital Strategy Advisory, Level 14, Al Faisaliah Tower, King Fahd Rd, Riyadh 12212, Saudi Arabia"
    camp = Campaign(
        name="US Outbound Corridor",
        country_code="US",
        status="ACTIVE",
        timezone="America/New_York",
        daily_quota=10,
        postal_address=stale_address,
        sending_window_start=9,
        sending_window_end=17,
        enabled=True
    )
    db_session.add(camp)
    await db_session.commit()
    await db_session.refresh(camp)

    raw_body = "Hi Reliable Roofing team,\n\nI noticed an opportunity to accelerate your mobile lead conversion."
    msg = OutreachMessage(
        business_id=biz.id,
        campaign_id=camp.id,
        recipient_email=biz.public_email,
        subject="Quick observation regarding reliableroofingtest.com",
        body=raw_body,
        status=OutreachStatus.APPROVED.value
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)

    res = await outreach_sender_adapter.send_approved_message(
        session=db_session,
        message_id=msg.id,
        force_live=False,
        enforce_window=False
    )
    assert res["status"] == "SUCCESS"

    await db_session.refresh(msg)
    final_body = msg.body

    # Construct the exact MIMEText message as Titan would
    mime_msg = MIMEText(final_body, "plain", "utf-8")
    raw_payload = mime_msg.get_payload(decode=True)
    mime_payload = raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else str(raw_payload)

    # Assertions on final outbound MIME payload:
    # 1. Contains intended business mailing address
    assert f"Mailing Address: {approved_address}" in mime_payload
    # 2. Contains unsubscribe mechanism
    assert "To opt out of future communications, reply 'unsubscribe'." in mime_payload
    # 3. Contains NO incorrect 'Digital Strategy Advisory / Al Faisaliah Tower' footer
    assert "Digital Strategy Advisory" not in mime_payload
    assert "Al Faisaliah" not in mime_payload
    assert "Riyadh" not in mime_payload
