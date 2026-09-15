import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from app.database.connection import Base
from app.database.models import (
    Business, AuditRun, AuditFinding, OutreachMessage, OutreachStatus, PipelineStage
)
from app.outreach.composer.models import (
    CanonicalProspect, ResearchFact, SenderIdentity, ComplianceProfile, ComposedEmail
)
from app.outreach.composer.entity_resolver import EntityResolver
from app.outreach.composer.solution_catalog import SolutionCatalog
from app.outreach.composer.composer import GeneralizedOutreachComposer, generalized_composer
from app.outreach.composer.validator import PreSendValidator
from app.outreach.personalization import outreach_personalizer


@pytest.fixture
def valid_sender():
    return SenderIdentity(
        sender_name="Alex Morgan",
        sender_email="alex@automatedagencyos.tech",
        sender_company="Agency OS",
        sender_role="Digital Systems Lead",
        reply_to="alex@automatedagencyos.tech"
    )


@pytest.fixture
def standard_prospect():
    return CanonicalProspect(
        prospect_id=101,
        company_name="Lone Star Dental Group",
        website="lonestardental.com",
        canonical_company_domain="lonestardental.com",
        recipient_email="info@lonestardental.com",
        recipient_name="Dr. Sarah Jenkins",
        industry="Dental",
        city="Austin",
        state_or_region="TX",
        country="US",
        phone="+15125550199"
    )


# =====================================================================
# TEST CASE A: Normal Prospect -> Correct Company / Domain / Location -> PASS
# =====================================================================
def test_case_a_normal_prospect_concise_valid_email(standard_prospect, valid_sender):
    facts = [
        ResearchFact(
            prospect_id=standard_prospect.prospect_id,
            fact="Primary appointment call-to-action is delayed below the mobile fold",
            source="audit:ux",
            category="conversion",
            metric_value=48.0
        )
    ]
    capabilities = {"has_online_booking": False, "has_after_hours_flow": False}
    solution = SolutionCatalog.match_solution(standard_prospect, facts, capabilities)

    # 1. Entity validation passes
    entity_res = EntityResolver.resolve_and_validate(standard_prospect)
    assert entity_res.is_valid is True

    # 2. Compose variants
    variants = generalized_composer.compose_variants(
        prospect=standard_prospect,
        facts=facts,
        solution=solution,
        sender=valid_sender,
        compliance=ComplianceProfile(enabled=False)
    )
    assert len(variants) == 3

    chosen = variants[0]
    # Verify concise word count
    assert 40 <= chosen.word_count <= 160
    assert "Hi Dr. Sarah Jenkins," in chosen.body
    assert "Lone Star Dental Group" in chosen.body
    assert "lonestardental.com" in chosen.body
    assert "Best,\nAlex Morgan\nDigital Systems Lead\nAgency OS" in chosen.body

    # Zero internal system branding or alien locations
    assert "autonomous growth engine" not in chosen.body.lower()
    assert "digital strategy advisory" not in chosen.body.lower()
    assert "al faisaliah" not in chosen.body.lower()
    assert "riyadh" not in chosen.body.lower()

    # Pre-send validation passes
    val_res = PreSendValidator.validate_email(chosen, standard_prospect, valid_sender, capabilities)
    assert val_res.is_valid is True


# =====================================================================
# TEST CASE B: Missing Recipient Name -> Generic Greeting -> PASS
# =====================================================================
def test_case_b_missing_recipient_name_uses_generic_greeting(standard_prospect, valid_sender):
    prospect = CanonicalProspect(
        prospect_id=102,
        company_name="Vance HVAC Services",
        website="vancehvac.com",
        canonical_company_domain="vancehvac.com",
        recipient_email="service@vancehvac.com",
        recipient_name=None,  # Missing recipient name
        industry="HVAC",
        city="Houston",
        country="US"
    )
    facts = [
        ResearchFact(
            prospect_id=102,
            fact="Inquiry response pathway relies on manual phone dispatch",
            source="audit:ux",
            category="conversion"
        )
    ]
    solution = SolutionCatalog.match_solution(prospect, facts, {})
    variants = generalized_composer.compose_variants(prospect, facts, solution, valid_sender)
    chosen = variants[0]

    assert "Hi Vance HVAC Services team," in chosen.body
    val_res = PreSendValidator.validate_email(chosen, prospect, valid_sender, {})
    assert val_res.is_valid is True


# =====================================================================
# TEST CASE C: Website / Domain Mismatch -> BLOCK
# =====================================================================
def test_case_c_domain_mismatch_blocks_entity_resolution():
    mismatched_prospect = CanonicalProspect(
        prospect_id=103,
        company_name="Apex Roofing",
        website="otherroofing.com",  # Mismatched website
        canonical_company_domain="apexroofing.com",
        recipient_email="contact@apexroofing.com",
        industry="Roofing"
    )
    res = EntityResolver.resolve_and_validate(mismatched_prospect)
    assert res.is_valid is False
    assert any("does not match canonical company domain" in e for e in res.errors)


# =====================================================================
# TEST CASE D: Wrong / Alien Location In Copy -> BLOCK
# =====================================================================
def test_case_d_wrong_location_blocks_pre_send_validation(standard_prospect, valid_sender):
    contaminated_email = ComposedEmail(
        subject="Quick question",
        body=(
            "Hi team, we reviewed lonestardental.com for Lone Star Dental Group. "
            "Our office at Al Faisaliah Tower in Riyadh noticed your booking pathway. "
            "Best, Alex Morgan Agency OS"
        ),
        word_count=45,
        variant_name="Test",
        prospect_id=standard_prospect.prospect_id,
        solution_matched="conversion_optimization"
    )
    val_res = PreSendValidator.validate_email(contaminated_email, standard_prospect, valid_sender)
    assert val_res.is_valid is False
    assert any("Alien location" in e for e in val_res.errors)


# =====================================================================
# TEST CASE E: Unsupported / Contradictory Research Claim -> BLOCK
# =====================================================================
def test_case_e_contradictory_claim_blocks_pre_send(standard_prospect, valid_sender):
    capabilities = {"has_online_booking": True}  # Research proved online booking DOES exist
    contradictory_email = ComposedEmail(
        subject="Regarding your website",
        body=(
            "Hi team, while reviewing lonestardental.com for Lone Star Dental Group, "
            "we noticed you have no online booking system for patients. "
            "Best, Alex Morgan Agency OS"
        ),
        word_count=42,
        variant_name="Test",
        prospect_id=standard_prospect.prospect_id,
        solution_matched="conversion_optimization"
    )
    val_res = PreSendValidator.validate_email(contradictory_email, standard_prospect, valid_sender, capabilities)
    assert val_res.is_valid is False
    assert any("Semantic contradiction" in e for e in val_res.errors)


# =====================================================================
# TEST CASE F: Cross-Prospect Contact Email -> BLOCK
# =====================================================================
def test_case_f_cross_prospect_contact_email_blocks():
    cross_prospect = CanonicalProspect(
        prospect_id=104,
        company_name="Austin Dental Clinic",
        website="austindental.com",
        canonical_company_domain="austindental.com",
        recipient_email="john@unrelatedroofing.com",  # Corporate email from unrelated company
        industry="Dental"
    )
    res = EntityResolver.resolve_and_validate(cross_prospect)
    assert res.is_valid is False
    assert any("does not match company domain" in e for e in res.errors)


# =====================================================================
# TEST CASE G: Missing Sender Configuration -> BLOCK
# =====================================================================
def test_case_g_missing_sender_config_blocks(standard_prospect):
    invalid_sender = SenderIdentity(
        sender_name="",  # Missing name
        sender_email="invalid-email",  # Malformed email
        sender_company=""
    )
    email = ComposedEmail(
        subject="Notice for Lone Star Dental Group",
        body="Hi team, note regarding lonestardental.com for Lone Star Dental Group. Best regards.",
        word_count=42,
        variant_name="Test",
        prospect_id=standard_prospect.prospect_id,
        solution_matched="conversion_optimization"
    )
    val_res = PreSendValidator.validate_email(email, standard_prospect, invalid_sender)
    assert val_res.is_valid is False
    assert any("Sender configuration error" in e for e in val_res.errors)


# =====================================================================
# TEST CASE H: Compliance Profile Enabled -> Configured Required Footer Only
# =====================================================================
def test_case_h_compliance_profile_enabled_includes_only_configured_footer(standard_prospect, valid_sender):
    profile = ComplianceProfile(
        enabled=True,
        business_name="Agency OS",
        postal_address="123 Commercial Way, Suite 400, Austin, TX 78701",
        unsubscribe_text="Reply unsubscribe to stop receiving outreach."
    )
    solution = SolutionCatalog.match_solution(standard_prospect, [], {})
    variants = generalized_composer.compose_variants(
        prospect=standard_prospect,
        facts=[],
        solution=solution,
        sender=valid_sender,
        compliance=profile
    )
    chosen = variants[0]
    assert "Mailing Address: 123 Commercial Way, Suite 400, Austin, TX 78701" in chosen.body
    assert "Reply unsubscribe to stop receiving outreach." in chosen.body
    # Ensure no hardcoded Saudi text
    assert "Al Faisaliah" not in chosen.body
    assert "Riyadh" not in chosen.body
    assert "We contacted this public address" not in chosen.body


# =====================================================================
# TEST CASE I: Compliance Profile Disabled -> No Invented Footer
# =====================================================================
def test_case_i_compliance_profile_disabled_has_zero_footer(standard_prospect, valid_sender):
    profile = ComplianceProfile(enabled=False)
    solution = SolutionCatalog.match_solution(standard_prospect, [], {})
    variants = generalized_composer.compose_variants(
        prospect=standard_prospect,
        facts=[],
        solution=solution,
        sender=valid_sender,
        compliance=profile
    )
    chosen = variants[0]
    assert "---" not in chosen.body
    assert "Mailing Address" not in chosen.body
    assert "unsubscribe" not in chosen.body.lower()
    # Ends cleanly with sender signature
    assert chosen.body.rstrip().endswith("Agency OS")


# =====================================================================
# TEST CASE J: Different Industries -> Generalized Solution Matching
# =====================================================================
def test_case_j_different_industries_generalized_matching(valid_sender):
    industries = [
        ("Precision Automotive Care", "precisionauto.com", "Automotive", "speed", 35.0, "performance_acceleration"),
        ("Skyline Roofing Pros", "skylineroofing.com", "Roofing", "conversion", 45.0, "conversion_optimization"),
        ("Metro Commercial Cleaning", "metrocleaning.com", "Home Services", "seo", 40.0, "local_seo_schema")
    ]
    for comp_name, domain, niche, fact_cat, score_val, expected_sol in industries:
        prospect = CanonicalProspect(
            prospect_id=200,
            company_name=comp_name,
            website=domain,
            canonical_company_domain=domain,
            recipient_email=f"info@{domain}",
            industry=niche
        )
        facts = [
            ResearchFact(
                prospect_id=200,
                fact=f"Diagnostic measured {fact_cat} deficiency",
                source="audit",
                category=fact_cat,
                metric_value=score_val
            )
        ]
        solution = SolutionCatalog.match_solution(prospect, facts, {})
        assert solution.solution_key == expected_sol

        variants = generalized_composer.compose_variants(prospect, facts, solution, valid_sender)
        chosen = variants[0]
        assert comp_name in chosen.body
        assert domain in chosen.body
        # NOT forced receptionist
        assert "AI receptionist" not in chosen.body


# =====================================================================
# TEST CASE K: Length Control Applied (60–140 words target, 40–160 limits)
# =====================================================================
def test_case_k_length_control_bounds(standard_prospect, valid_sender):
    # Overly long draft fails validation
    long_body = "word " * 175
    long_email = ComposedEmail(
        subject="Test long",
        body=f"Hi team, lonestardental.com for Lone Star Dental Group. {long_body} Best, Alex Morgan Agency OS",
        word_count=185,
        variant_name="Long",
        prospect_id=standard_prospect.prospect_id,
        solution_matched="conversion_optimization"
    )
    val_res = PreSendValidator.validate_email(long_email, standard_prospect, valid_sender)
    assert val_res.is_valid is False
    assert any("exceeds maximum length" in e for e in val_res.errors)

    # Standard generated email respects word count
    solution = SolutionCatalog.match_solution(standard_prospect, [], {})
    variants = generalized_composer.compose_variants(standard_prospect, [], solution, valid_sender)
    for v in variants:
        assert 40 <= v.word_count <= 140


# =====================================================================
# ASYNC DATABASE SESSION INTEGRATION TESTS
# =====================================================================
@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# =====================================================================
# TEST CASE L: End-to-End Outreach Preparation & Staging into Database
# =====================================================================
@pytest.mark.asyncio
async def test_case_l_async_db_session_outreach_staging_success(test_db):
    # Setup business
    biz = Business(
        name="Austin Precision Dental",
        domain="austinprecisiondental.com",
        public_email="contact@austinprecisiondental.com",
        niche="Dental",
        city="Austin",
        country="US",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    test_db.add(biz)
    await test_db.commit()
    await test_db.refresh(biz)

    # Setup audit run and finding
    audit = AuditRun(
        business_id=biz.id,
        url_audited="https://austinprecisiondental.com",
        overall_health_score=48.5,
        performance_score=60.0,
        ux_conversion_score=45.0,
        seo_score=50.0
    )
    test_db.add(audit)
    await test_db.commit()
    await test_db.refresh(audit)

    finding = AuditFinding(
        audit_id=audit.id,
        category="conversion",
        finding="Appointment reservation CTA drops below the fold on mobile viewports",
        severity="medium",
        evidence="Mobile viewport shows header without booking trigger",
        url="https://austinprecisiondental.com",
        recommended_fix="Add sticky booking CTA on mobile viewports",
        estimated_business_impact="Increase mobile conversions by 15%"
    )
    test_db.add(finding)
    await test_db.commit()

    # Prepare outreach through canonical personalizer
    msg = await outreach_personalizer.prepare_outreach_for_business(test_db, biz, selected_variant=0)

    # 1. Staged in PENDING_APPROVAL
    assert msg is not None
    assert msg.status == OutreachStatus.PENDING_APPROVAL.value
    assert msg.recipient_email == "contact@austinprecisiondental.com"

    # 2. Company name and domain correctly grounded
    assert "Austin Precision Dental" in msg.body
    assert "austinprecisiondental.com" in msg.body

    # 3. Word count strictly between 40 and 160 words
    words = msg.body.split()
    assert 40 <= len(words) <= 160

    # 4. Zero leakages of hardcoded Saudi text or internal system prompts
    body_lower = msg.body.lower()
    assert "al faisaliah" not in body_lower
    assert "riyadh" not in body_lower
    assert "autonomous growth engine" not in body_lower
    assert "digital strategy advisory" not in body_lower
    assert "we contacted this public address" not in body_lower

    # 5. Pipeline stage progressed to APPROVAL
    await test_db.refresh(biz)
    assert biz.pipeline_stage == PipelineStage.APPROVAL.value


# =====================================================================
# TEST CASE M: Entity Mismatch Raises OUTREACH_VALIDATION_FAILED and Blocks DB Staging
# =====================================================================
@pytest.mark.asyncio
async def test_case_m_async_db_session_mismatch_blocks_staging(test_db):
    # Setup business with mismatched recipient email domain
    biz = Business(
        name="Summit Dental Care",
        domain="summitdental.com",
        public_email="info@unrelatedhvacpros.com",  # Domain mismatch
        niche="Dental",
        city="Denver",
        country="US",
        pipeline_stage=PipelineStage.AUDITED.value
    )
    test_db.add(biz)
    await test_db.commit()
    await test_db.refresh(biz)

    # Attempting to stage outreach must raise ValueError with OUTREACH_VALIDATION_FAILED
    with pytest.raises(ValueError) as exc_info:
        await outreach_personalizer.prepare_outreach_for_business(test_db, biz)

    assert "OUTREACH_VALIDATION_FAILED" in str(exc_info.value)
    assert "does not match company domain" in str(exc_info.value)

    # Verify no message was staged in the database
    q = select(OutreachMessage).where(OutreachMessage.business_id == biz.id)
    res = (await test_db.execute(q)).scalars().all()
    assert len(res) == 0
