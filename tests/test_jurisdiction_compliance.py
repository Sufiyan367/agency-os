"""Targeted Verification Suite: Global Outbound Legal & Compliance Remediation.

Verifies:
1. DE cannot send (OUTBOUND_BLOCKED / jurisdiction_requires_consent)
2. IT cannot send (OUTBOUND_BLOCKED / jurisdiction_requires_consent)
3. ES cannot send (OUTBOUND_BLOCKED / jurisdiction_requires_consent)
4. CH cannot send (OUTBOUND_BLOCKED / jurisdiction_requires_consent)
5. Personal webmail is correctly handled (e.g. UK blocks @gmail, US permits with CAN-SPAM opt-out)
6. Prohibited-contact disclaimer blocks (negative disclaimers)
7. Provenance is persisted (source_url, observed_at, recipient_role, lawful_basis without generic fallback)
8. Compliant corporate prospect can pass (e.g. UK corporate subscriber on business domain)
9. Ambiguous prospect is blocked (unverified entity)
10. Existing suppression/dedup/memory gates remain active
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

from app.database.models import OutreachMessage, OutreachStatus, Business, Contact, Campaign
from app.campaigns.compliance_gate import campaign_compliance_gate
from app.compliance.recipient_classifier import (
    classify_recipient,
    RecipientClassification,
    is_personal_webmail,
    is_role_based_address
)
from app.compliance.negative_disclaimer import (
    detect_negative_disclaimer,
    contains_prohibited_contact_notice
)
from app.compliance.provenance import (
    resolve_lawful_basis,
    build_jurisdiction_provenance,
    STRICT_OPT_IN_JURISDICTIONS
)
from app.campaigns.models import QuotaCheckResult
from app.outreach.auto_approval import DeterministicAutoApprovalEngine

MOCK_QUOTA_RES = QuotaCheckResult(
    allowed=True,
    effective_limit=10,
    country_quota=10,
    campaign_quota=10,
    global_quota=200,
    provider_quota=500,
    sender_quota=200,
    rollout_level_limit=200,
    limiting_factor="country_quota",
    reason="Within limits",
    country_sent_today=0,
    global_sent_today=0,
    campaign_sent_today=0,
    rollout_limit=200,
    effective_remaining=10
)


@pytest.fixture
def mock_session():
    session = AsyncMock()
    # Mock execute returning empty/clean results for suppression, duplicates, etc.
    mock_res = MagicMock()
    mock_res.first.return_value = None
    mock_res.scalar.return_value = 0
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res
    return session


def make_mock_business(id=1, name="Acme Corp Ltd", domain="acmecorp.co.uk", country="UK"):
    biz = Business(
        id=id,
        name=name,
        domain=domain,
        country=country,
        website_url=f"https://{domain}",
        contact_page_url=f"https://{domain}/contact",
        created_at=datetime.utcnow()
    )
    biz.audits = []
    return biz


def make_mock_message(
    id=1,
    business_id=1,
    email="info@acmecorp.co.uk",
    body="Hello,\nWe analyzed your website speed.\nTo unsubscribe reply stop.\nAgency OS, 100 Real Street, City, Country"
):
    msg = OutreachMessage(
        id=id,
        business_id=business_id,
        recipient_email=email,
        subject="Audit of your digital presence",
        body=body,
        status=OutreachStatus.PENDING_APPROVAL.value,
        actor_type="HUMAN",
        auto_approval_eligibility={}
    )
    return msg


# TEST 1-4: Category C corridors (DE, IT, ES, CH) strictly blocked
@pytest.mark.asyncio
@pytest.mark.parametrize("country", ["DE", "IT", "ES", "CH"])
async def test_category_c_corridors_strictly_blocked(mock_session, country):
    biz = make_mock_business(name="Euro Partner GmbH", domain=f"partner.{country.lower()}", country=country)
    msg = make_mock_message(email=f"contact@partner.{country.lower()}")
    mock_session.get.return_value = biz

    with patch("app.outreach.compliance.compliance_guard.is_suppressed", new=AsyncMock(return_value=False)), \
         patch("app.campaigns.sender_registry.sender_registry.validate_sender_ready", return_value=(True, "Ready", {"email": "out@agency.com", "postal_address": "123 Verified Way"})), \
         patch("app.campaigns.quota_engine.quota_engine.evaluate_quota", new=AsyncMock(return_value=MOCK_QUOTA_RES)), \
         patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new=AsyncMock(return_value={"available_capacity": 10, "sent_today": 0, "safe_per_sender_daily_limit": 50, "rollout_daily_cap": 200})):
        
        gate_res = await campaign_compliance_gate.evaluate_pre_send(
            session=mock_session,
            message=msg,
            enforce_window=False
        )

    assert not gate_res.is_eligible
    assert any("OUTBOUND_BLOCKED / jurisdiction_requires_consent" in r for r in gate_res.failure_reasons)
    assert country in STRICT_OPT_IN_JURISDICTIONS


# TEST 5: Personal webmail handling across jurisdictions
def test_personal_webmail_classification_and_handling():
    # Webmail classification must be deterministic and never corporate
    assert is_personal_webmail("ceo.john@gmail.com") is True
    assert is_personal_webmail("director@yahoo.co.uk") is True
    assert is_personal_webmail("info@acmecorp.com") is False

    res_uk = classify_recipient(
        email="plumber99@gmail.com",
        business_name="Acme Plumbing Ltd",
        business_domain="acmeplumbing.co.uk"
    )
    assert res_uk == RecipientClassification.PERSONAL_WEBMAIL

    # UK/EU rejects personal webmail for B2B
    _, _, decision_uk, reason_uk = resolve_lawful_basis("UK", RecipientClassification.PERSONAL_WEBMAIL)
    assert decision_uk == "OUTBOUND_BLOCKED"
    assert "personal_webmail_ineligible" in reason_uk

    # US permits personal webmail under CAN-SPAM opt-out framework
    _, _, decision_us, reason_us = resolve_lawful_basis("US", RecipientClassification.PERSONAL_WEBMAIL)
    assert decision_us == "PERMITTED"
    assert reason_us is None


# TEST 6: Negative disclaimer detection
def test_negative_disclaimer_blocking():
    texts_with_disclaimer = [
        "We are not interested in agency services. Strictly no unsolicited emails or marketing inquiries.",
        "Please note: No commercial inquiries or sales pitches accepted through this contact form.",
        "Keine unaufgeforderte Werbung per E-Mail erwünscht.",
        "Pas de démarchage commercial svp.",
        "Prohibido el envío de publicidad no solicitada."
    ]
    for txt in texts_with_disclaimer:
        has_disc, phrase = detect_negative_disclaimer(txt)
        assert has_disc is True, f"Failed to detect negative disclaimer in: {txt}"
        assert phrase is not None

    clean_text = "Reach out to our sales engineering team for enterprise inquiries and partnership quotes."
    has_disc_clean, _ = detect_negative_disclaimer(clean_text)
    assert has_disc_clean is False


# TEST 7: Provenance persistence without generic CAN-SPAM fallback
def test_provenance_persistence():
    prov = build_jurisdiction_provenance(
        country_code="UK",
        email="operations@logistics.co.uk",
        business_name="Logistics UK Ltd",
        business_domain="logistics.co.uk",
        source_url="https://logistics.co.uk/contact",
        recipient_role="Operations Lead",
        recipient_classification=RecipientClassification.ROLE_BASED_CORPORATE,
        audit_summary="Observable page speed 42/100 and SEO opportunities."
    )
    prov_dict = prov.to_dict()
    assert prov_dict["jurisdiction"] == "UK"
    assert prov_dict["source_url"] == "https://logistics.co.uk/contact"
    assert prov_dict["recipient_classification"] == "ROLE_BASED_CORPORATE"
    assert "PECR_REG_22_CORPORATE_SUBSCRIBER" in prov_dict["lawful_basis"]
    assert "CAN-SPAM / GDPR B2B public legitimate interest" not in prov_dict["lawful_basis"]
    assert prov_dict["compliance_decision"] == "PERMITTED"


# TEST 8: Compliant corporate prospect passing
@pytest.mark.asyncio
async def test_compliant_uk_corporate_prospect_passes(mock_session):
    biz = make_mock_business(name="London Tech Solutions Ltd", domain="londontech.co.uk", country="UK")
    msg = make_mock_message(email="contact@londontech.co.uk")
    mock_session.get.return_value = biz

    with patch("app.outreach.compliance.compliance_guard.is_suppressed", new=AsyncMock(return_value=False)), \
         patch("app.campaigns.sender_registry.sender_registry.validate_sender_ready", return_value=(True, "Ready", {"email": "out@agency.com", "postal_address": "456 Enterprise Park, London"})), \
         patch("app.campaigns.quota_engine.quota_engine.evaluate_quota", new=AsyncMock(return_value=MOCK_QUOTA_RES)), \
         patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new=AsyncMock(return_value={"available_capacity": 10, "sent_today": 0, "safe_per_sender_daily_limit": 50, "rollout_daily_cap": 200})):
        
        gate_res = await campaign_compliance_gate.evaluate_pre_send(
            session=mock_session,
            message=msg,
            enforce_window=False
        )

    assert gate_res.is_eligible is True
    assert len(gate_res.failure_reasons) == 0
    assert "PECR_REG_22_CORPORATE_SUBSCRIBER" in msg.compliance_notes
    assert msg.auto_approval_eligibility["jurisdiction_provenance"]["compliance_decision"] == "PERMITTED"


# TEST 9: Ambiguous / unknown entity blocked
@pytest.mark.asyncio
async def test_ambiguous_prospect_blocked(mock_session):
    # Non-matching domain, no company entity suffix in UK
    biz = make_mock_business(name="Bob Smith", domain="randomsite.org", country="UK")
    msg = make_mock_message(email="bob@unrelateddomain.net")
    mock_session.get.return_value = biz

    with patch("app.outreach.compliance.compliance_guard.is_suppressed", new=AsyncMock(return_value=False)), \
         patch("app.campaigns.sender_registry.sender_registry.validate_sender_ready", return_value=(True, "Ready", {"email": "out@agency.com", "postal_address": "456 Enterprise Park"})), \
         patch("app.campaigns.quota_engine.quota_engine.evaluate_quota", new=AsyncMock(return_value=MOCK_QUOTA_RES)), \
         patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new=AsyncMock(return_value={"available_capacity": 10, "sent_today": 0, "safe_per_sender_daily_limit": 50, "rollout_daily_cap": 200})):
        
        gate_res = await campaign_compliance_gate.evaluate_pre_send(
            session=mock_session,
            message=msg,
            enforce_window=False
        )

    assert gate_res.is_eligible is False
    assert any("unverified_recipient_entity" in r for r in gate_res.failure_reasons)


# TEST 10: Existing suppression, duplicate prevention, and physical address gates remain strictly active
@pytest.mark.asyncio
async def test_existing_safety_gates_remain_active(mock_session):
    biz = make_mock_business(country="US")
    msg = make_mock_message(email="contact@uscorp.com")
    mock_session.get.return_value = biz

    # Case A: Suppressed recipient
    with patch("app.outreach.compliance.compliance_guard.is_suppressed", new=AsyncMock(return_value=True)), \
         patch("app.campaigns.sender_registry.sender_registry.validate_sender_ready", return_value=(True, "Ready", {"email": "out@agency.com", "postal_address": "123 Main St"})), \
         patch("app.campaigns.quota_engine.quota_engine.evaluate_quota", new=AsyncMock(return_value=MOCK_QUOTA_RES)), \
         patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new=AsyncMock(return_value={"available_capacity": 10, "sent_today": 0, "safe_per_sender_daily_limit": 50, "rollout_daily_cap": 200})):
        
        gate_res = await campaign_compliance_gate.evaluate_pre_send(session=mock_session, message=msg, enforce_window=False)
        assert gate_res.is_eligible is False
        assert any("suppression list" in r for r in gate_res.failure_reasons)

    # Case B: Missing opt-out footer
    msg_no_optout = make_mock_message(email="contact@uscorp.com", body="Hey let's talk business.")
    with patch("app.outreach.compliance.compliance_guard.is_suppressed", new=AsyncMock(return_value=False)), \
         patch("app.campaigns.sender_registry.sender_registry.validate_sender_ready", return_value=(True, "Ready", {"email": "out@agency.com", "postal_address": "123 Main St"})), \
         patch("app.campaigns.quota_engine.quota_engine.evaluate_quota", new=AsyncMock(return_value=MOCK_QUOTA_RES)), \
         patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new=AsyncMock(return_value={"available_capacity": 10, "sent_today": 0, "safe_per_sender_daily_limit": 50, "rollout_daily_cap": 200})):
        
        gate_res = await campaign_compliance_gate.evaluate_pre_send(session=mock_session, message=msg_no_optout, enforce_window=False)
        assert gate_res.is_eligible is False
        assert any("opt-out" in r.lower() or "postal" in r.lower() for r in gate_res.failure_reasons)


# TEST 11: DeterministicAutoApprovalEngine verifies jurisdiction and webmail blocks
@pytest.mark.asyncio
async def test_auto_approval_engine_jurisdiction_enforcement(mock_session):
    engine = DeterministicAutoApprovalEngine()

    # Case 1: Germany prospect must be rejected by auto-approval
    biz_de = make_mock_business(name="German Auto GmbH", domain="germanauto.de", country="DE")
    msg_de = make_mock_message(email="info@germanauto.de")
    mock_session.get.return_value = biz_de

    with patch("app.outreach.compliance.compliance_guard.is_suppressed", new=AsyncMock(return_value=False)), \
         patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new=AsyncMock(return_value={"available_capacity": 10, "sent_today": 0, "rollout_daily_cap": 200})), \
         patch("app.acquisition.controller.active_prospect_controller.get_or_create_lock", new=AsyncMock(return_value=MagicMock(status="IDLE", business_id=1))):
        
        res_de = await engine.evaluate_message_eligibility(mock_session, msg_de)
        assert res_de.is_eligible is False
        assert any("jurisdiction_requires_consent" in r for r in res_de.blocking_reasons)

    # Case 2: UK personal webmail must be rejected by auto-approval
    biz_uk = make_mock_business(name="UK Logistics Ltd", domain="uklogistics.co.uk", country="UK")
    msg_uk_webmail = make_mock_message(email="uklogistics@gmail.com")
    mock_session.get.return_value = biz_uk

    with patch("app.outreach.compliance.compliance_guard.is_suppressed", new=AsyncMock(return_value=False)), \
         patch("app.campaigns.sender_registry.sender_registry.get_sender_capacity_summary", new=AsyncMock(return_value={"available_capacity": 10, "sent_today": 0, "rollout_daily_cap": 200})), \
         patch("app.acquisition.controller.active_prospect_controller.get_or_create_lock", new=AsyncMock(return_value=MagicMock(status="IDLE", business_id=1))):
        
        res_uk = await engine.evaluate_message_eligibility(mock_session, msg_uk_webmail)
        assert res_uk.is_eligible is False
        assert any("personal_webmail_ineligible" in r for r in res_uk.blocking_reasons)
