# Autonomous B2B Lead-Gen & Sales Agency — Production Walkthrough

## 1. Executive Summary & Verification Highlights

The Autonomous B2B Lead-Gen & Sales Agency platform has undergone a complete frontend redesign into a **futuristic Tony Stark / JARVIS-inspired Command Center** while maintaining 100% backend, API, worker, database, payment, and test integrity:
1. **Tony Stark / JARVIS HUD Aesthetic**:
   - **Cinematic Dark Palette**: Deep space obsidian (`#02050b`) with glowing radial cyan gradients (`#00f0ff`), neon cobalt (`#0070f3`), arc-reactor emerald (`#00ff9f`), and crimson warning accents.
   - **Thin Technical Borders & Corner Accents**: Aerospace-grade HUD framing with glowing corner tick brackets and subtle 28px gridlines.
   - **Aerospace & Cybernetic Typography**: Google Fonts integration with `Orbitron` (HUD readouts & titles), `Rajdhani` (body & telemetry), and `JetBrains Mono` (hashes, currency, reference IDs).
2. **Large LIVE SYSTEM / AGENCY STATUS Panel**:
   - **Animated Arc Reactor**: Concentric dual-ring rotating vector orb with pulsating glowing plasma core.
   - **Real-Time Operational Telemetry**: Live Worker Status indicator (`ONLINE // ACTIVE`), Cadence (`60s TICK`), Tick Counter (`N TICKS`), Last Telemetry Tick timestamp, Primary Gateway (`RAZORPAY`), and Safeguard Mode (`DRY_RUN PROTECTED`).
   - **Live Mission UTC Clock**: Real-time second-by-second mission timer (`HH:MM:SS UTC`).
3. **High-Impact Tactical Data Panels**:
   - **Real-Time KPI Cards**: Pipeline Value, Won Revenue, Discovered Prospects, Qualified Leads, Outreach Transmissions, Signal Reply Rate.
   - **Market Radar**: Global market scanning matrix with empirical opportunity scores and digital deficit indicators.
   - **Target Prospect Registry**: High-density lead matrix with qualification ratings and quick audit modals.
   - **Outreach Authorization Terminal**: Evidence-grounded proposal review with 1-click transmission authorization.
   - **Signal Interception Stream**: AI reply classification with intent badges, confidence ratings, and suggested response drafts.
   - **Pipeline Kanban Radar**: Stage progression radar across all lifecycle stages.
   - **Financial Ledger**: Razorpay & Stripe transaction journal with instant checkout link generation.
   - **Scheduler & Worker Heartbeats**: Telemetry logs with latency and record counters.
4. **Mobile Responsiveness**:
   - Slide-out holographic navigation drawer.
   - Sticky bottom HUD quick navigation ribbon (`Overview`, `Queue`, `Replies`, `Deals`).
5. **100% Automated Test Health**: **51 / 51 automated tests passing green** in 32.87s.

---

## 2. JARVIS HUD Architecture & Telemetry Strip

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     JARVIS // MARK-XXVI TACTICAL HUD                        │
│                                                                             │
│   [ARC REACTOR]   AUTONOMOUS REVENUE ENGINE                                 │
│   (◉) Core Pulse  Worker: ONLINE // ACTIVE   Cadence: 60s TICK              │
│    Rotating Rings Ticks: 42 TICKS            Last Tick: 00:58:15            │
│                   Gateway: RAZORPAY PRIMARY  Mode: DRY_RUN PROTECTED        │
│                                                                             │
│   [ENGAGE AUTONOMOUS CYCLE]               MISSION TIME: 00:58:25 UTC        │
├─────────────────────────────────────────────────────────────────────────────┤
│  REAL-TIME KPI TELEMETRY                                                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ PIPELINE VAL │ │ WON REVENUE  │ │  PROSPECTS   │ │ QUALIFIED    │        │
│  │ $14,250      │ │ $2,400       │ │  128         │ │ 84 (65%)     │        │
│  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘        │
├─────────────────────────────────────────────────────────────────────────────┤
│  TACTICAL MODULES                                                           │
│  • // MARKET RADAR           • // TARGET PROSPECTS                          │
│  • // OUTREACH QUEUE         • // SIGNAL INTERCEPT (REPLIES)                │
│  • // SALES PIPELINE         • // REVENUE & DEALS (RAZORPAY)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Test Suite Verification (51 / 51 Passing Green)

```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-8.4.2, pluggy-1.6.0
rootdir: S:\AGENCY\BY AG
configfile: pytest.ini
plugins: anyio-4.12.1, asyncio-1.4.0
collected 51 items

tests/test_api_endpoints.py::test_api_health_and_endpoints PASSED        [  1%]
tests/test_audit_engine.py::test_performance_auditor_detects_viewport_and_images PASSED [  3%]
tests/test_audit_engine.py::test_seo_auditor_detects_missing_title_meta_schema PASSED [  5%]
tests/test_audit_engine.py::test_accessibility_auditor_detects_wcag_violations PASSED [  7%]
tests/test_audit_engine.py::test_master_audit_engine PASSED              [  9%]
tests/test_backup_and_recovery.py::test_backup_creation_and_integrity PASSED [ 11%]
tests/test_backup_and_recovery.py::test_list_backups PASSED              [ 13%]
tests/test_backup_and_recovery.py::test_restore_backup_verification PASSED [ 15%]
tests/test_cloud_auth_and_security.py::test_session_token_lifecycle PASSED [ 17%]
tests/test_cloud_auth_and_security.py::test_credential_verification PASSED [ 19%]
tests/test_cloud_auth_and_security.py::test_api_key_verification PASSED  [ 21%]
tests/test_cloud_auth_and_security.py::test_auth_login_and_logout_endpoints PASSED [ 23%]
tests/test_cloud_auth_and_security.py::test_public_health_endpoints_accessible PASSED [ 25%]
tests/test_email_providers.py::test_dry_run_provider PASSED              [ 27%]
tests/test_email_providers.py::test_email_provider_factory_safety_default PASSED [ 29%]
tests/test_email_providers.py::test_resend_provider_payload PASSED       [ 31%]
tests/test_email_providers.py::test_sendgrid_provider_payload PASSED     [ 33%]
tests/test_email_providers.py::test_mandatory_human_approval_enforcement PASSED [ 35%]
tests/test_email_providers.py::test_suppression_list_blocks_sender PASSED [ 37%]
tests/test_inbox_and_autostop.py::test_inbox_message_matching_and_interested_reply PASSED [ 39%]
tests/test_inbox_and_autostop.py::test_unsubscribe_auto_stop_and_suppression PASSED [ 41%]
tests/test_inbox_and_autostop.py::test_bounce_auto_stop_and_suppression PASSED [ 43%]
tests/test_inbox_and_autostop.py::test_process_due_followups_execution PASSED [ 45%]
tests/test_lead_deduplication.py::test_lead_discovery_and_deduplication PASSED [ 47%]
tests/test_lead_deduplication.py::test_lead_verification_checks PASSED   [ 49%]
tests/test_market_intelligence.py::test_market_intelligence_ranking_and_comparison PASSED [ 50%]
tests/test_outreach_and_approval_queue.py::test_outreach_queue_and_approval_gate PASSED [ 52%]
tests/test_outreach_and_approval_queue.py::test_compliance_suppression_prevents_outreach PASSED [ 54%]
tests/test_payments_and_onboarding.py::test_stripe_checkout_session_dry_run PASSED [ 56%]
tests/test_payments_and_onboarding.py::test_stripe_hmac_signature_verification PASSED [ 58%]
tests/test_payments_and_onboarding.py::test_payment_confirmation_and_automatic_onboarding PASSED [ 60%]
tests/test_persistent_worker.py::### Test Results
- `tests/test_phase17_voice_operations.py`: 18/18 passed
- `tests/test_voice_sales_layer.py`: 10/10 passed

---

# Phase 18 — Step 2: Provider Connectivity Preflight & Safety Verification

## Overview
Phase 18 Step 2 performs a non-destructive, strictly read-only preflight of the Email, Payment, and Voice provider infrastructure. It rigorously verifies provider configuration, public DNS health, credential validation, cryptographic HMAC webhook authentication, failure injection safety nets, and executes an isolated end-to-end simulation where all records are marked `SIMULATION/TEST` with zero live side-effects and zero revenue.

## Verifications & Safety Guarantees

### 1. Provider Connectivity & Preflight Status
- **Email (Resend)**:
  - Provider: Resend (`re_...` key format verified, non-empty, non-logged).
  - Sender Domain: `agencygrowth.co` (`contact@agencygrowth.co`, Reply-To: `support@agencygrowth.co`).
  - Public DNS: SPF (`v=spf1 include:resend.com ~all`) and DMARC (`v=DMARC1; p=none...`) present. DKIM CNAME records pending DNS registrar addition before live outbound sending can be unblocked.
  - Live Sending Status: `BLOCKED` until DKIM verified; `EMAIL_DRY_RUN=True` actively enforced.
- **Payment (Razorpay)**:
  - Provider: Razorpay Test Mode (`rzp_test_...` key ID, secret, and webhook secret verified).
  - Webhook Security: Cryptographic HMAC-SHA256 signature verification validated against live forged signatures (HTTP 400 rejection).
  - Commercial Safeguards: Strict \$500.00 commercial floor enforced; sub-\$500 payments rejected with `ValueError`; duplicate webhook replays safely detected and ignored with `DUPLICATE_IGNORED`.
  - Live Payment Status: `DISABLED` (`PAYMENTS_ENABLED=False`, `PAYMENT_DRY_RUN=True`).
- **Voice (Twilio / Bland AI / Dry-Run)**:
  - Active Mode: `VOICE_DRY_RUN=True` with `DryRunVoiceProvider`.
  - 15-State Conversation Machine: Validated transitions from initial pitch to negotiation, proposal, payment handoff, or opt-out.
  - Compliance: Immediate suppression on opt-out; automatic human escalation on legal, GDPR/privacy, hostility, and payment disputes.
  - Live Voice Status: `DISABLED`.

### 2. Mocked Internal End-to-End Flow (`SIMULATION/TEST`)
- Executed full 11-step autonomous cycle in complete test isolation:
  `Prospect -> Evidence -> Factual Audit -> Service Match -> $1,000+ Offer -> Auto-Approval -> Dry-Run Outreach -> Mock Inbound Reply -> Voice Call -> Price Negotiation -> Proposal -> Webhook Payment Event -> Verification -> Customer/Project Onboarding`.
- Verified Invariant: Deal progressed to `PROPOSAL` upon verbal agreement; deal was **never** marked `WON` prematurely until verified HMAC webhook payment confirmation.

### 3. Failure Injection Test Suite (`tests/test_phase18_provider_preflight.py`)
- **Email Failures**: Suppressed recipient blocked (`ValueError`), duplicate send prohibited (`ValueError`), live send without credentials rejected (`ValueError`).
- **Payment Failures**: Forged signature rejected (HTTP 400), underpayment below \$500 floor rejected (`ValueError`), duplicate webhook replay idempotent.
- **Voice Failures**: Legal/privacy/dispute triggers human escalation, low confidence triggers operator escalation, verbal opt-out triggers immediate number suppression and cancels future attempts.
- **Safety Invariants**: Asserted `RESEARCH_ONLY=True`, `EMAIL_DRY_RUN=True`, `PAYMENTS_ENABLED=False`, `PAYMENT_DRY_RUN=True`, `VOICE_DRY_RUN=True`.

## Test Results
- `tests/test_phase18_provider_preflight.py`: 11/11 passed
- `tests/test_phase16_setup_wizard.py`: 14/14 passed
- `tests/test_phase17_voice_operations.py`: 18/18 passed
- **Full Project Regression Suite**: 512/512 passed (0 failures, 0 regressions)

---

# Agency OS — Payment System Production Implementation Walkthrough

## 1. Actual Implemented Lifecycle Flow

The production payment path enforces a strict, multi-stage commercial gate:

$$\text{PROPOSAL} \longrightarrow \text{PAYMENT\_PENDING} \longrightarrow \text{CUSTOMER PAYMENT} \longrightarrow \text{PAYMENT\_REVIEW\_REQUIRED} \longrightarrow \text{HUMAN\_OPERATOR\_VERIFICATION} \longrightarrow \text{PAYMENT\_CONFIRMED} \longrightarrow \text{40\% ADVANCE VALIDATION} \longrightarrow \text{PRODUCTION\_BUILD\_AUTHORIZED} \longrightarrow \text{DELIVERY WORKFLOW}$$

```
[Proposal Approved]
       │
       ▼
[Payment Requested] ───────► Status: PAYMENT_PENDING
       │
       ▼
[Customer Transacts via UPI]
       │
       ▼
[Customer Submits UTR] ─────► Status: PAYMENT_REVIEW_REQUIRED (Production STILL LOCKED)
       │
       ▼
[Operator Verifies Bank UTR] ─► Status: PAYMENT_CONFIRMED (HUMAN_OPERATOR_VERIFICATION)
       │
       ▼
[Commercial Gate Check] ────► 40% Advance Floor Validated (>= $200 on >= $500 total)
       │
       ▼
[Production Initialized] ───► Customer & Project Provisioned -> Delivery Workflow Active
```

---

## 2. Customer Payment Portal

The system provides a dedicated customer payment interface accessible via:
- `GET /pay/{reference}`
- `GET /payment/{reference}`

The route dynamically resolves payments by numeric `payment_id`, unique remittance reference code (`OS-REM-...`), gateway order ID, or linked proposal reference.

### Portal Capabilities:
- **Transparent Milestone Pricing**:
  - **Total Contract Value**: Minimum commercial floor of **$500.00 USD**.
  - **40% Milestone Advance**: **$200.00 USD** minimum on the $500 floor, required to unlock production.
  - **60% Handover Balance**: Due strictly upon final staging verification and sign-off.
- **Dynamic Status Badges**:
  - `PAYMENT CONFIRMED — PRODUCTION AUTHORIZED` (Emerald Green)
  - `PAYMENT REVIEW REQUIRED — UNDER RECONCILIATION` (Amber Warning)
  - `PAYMENT PENDING — 40% ADVANCE DUE` (Sky Blue)
- **Currency & Remittance Disclaimers**: Discloses that all services are contracted in USD, with Indian UPI/IMPS transfers settled via standard remittance exchange rates.

---

## 3. Manual UPI Remittance Architecture

- **Beneficiary VPA**: `mrsufiyansurve@okaxis`
- **Beneficiary Name**: `Sufiyan Surve / Agency OS`
- **Direct UPI Link**: `upi://pay?pa=mrsufiyansurve@okaxis&pn=Sufiyan%20Surve&am=<advance>&cu=USD&tr=<reference>&tn=Invoice%20<reference>`
- **Reference / UTR Submission**:
  - Interactive web form submits to `POST /pay/{reference}/submit-reference`
  - REST API endpoint: `POST /api/payments/{id}/submit-reference`
- **Automated Webhook Architecture Stance**:
  - **Explicit Invariant**: Standalone UPI does **NOT** provide an automated provider webhook in this implementation.
  - The manual UPI payment method does not have direct bank API callback hooks; settlement reconciliation is performed exclusively via operator bank verification.

---

## 4. Verification & Status Progression

- **Customer Submission Never Confirms Payment**:
  - A client submitting a transaction reference or bank UTR updates the record to `PAYMENT_REVIEW_REQUIRED`.
  - Customer submission does **NOT** confirm the payment, does **NOT** transition status to `PAYMENT_CONFIRMED`, and does **NOT** unlock production.
- **Human Operator Verification**:
  - The finance operator inspects the actual bank inward remittance ledger.
  - Operator executes `POST /api/payments/{id}/confirm` with the verified bank UTR, operator username, and confirmed amount.
  - Only upon successful operator verification is the record transitioned to `PAYMENT_CONFIRMED` (`verification_method = "HUMAN_OPERATOR_VERIFICATION"`).

---

## 5. Anti-Fraud & Commercial Safeguards

1. **Untrusted Source Rejection**:
   - Verification attempts citing untrusted sources (`screenshot`, `customer_message`, `manual_claim`, `unverified`, `ai_inference`) are strictly rejected with `PermissionError`.
2. **Underpayment Rejection**:
   - Verifying an amount below the required milestone advance is rejected with `ValueError("Underpayment rejected")`.
3. **Duplicate Transaction Reference Rejection**:
   - Replay protection blocks duplicate transaction references across verified payments with `ValueError("Fraud detected")`.
4. **Webhook Replay Protection & Idempotency**:
   - Duplicate webhook deliveries are guarded by `PaymentWebhookEvent(provider, event_id)` with database-level uniqueness constraints, returning `DUPLICATE_IGNORED`.
   - Repeated operator confirmation calls return `ALREADY_CONFIRMED` idempotently without duplicate project provisioning.
5. **Cryptographic Webhook Verification**:
   - HMAC-SHA256 signature verification enforced for automated providers (Stripe / Razorpay) where credentials exist.

---

## 6. Commercial Gate Boundary

The commercial gate (`operator_learning_engine.enforce_commercial_gate`) acts as an immutable boundary between deal closing and engineering execution:
- **Minimum Project Floor**: $500.00 USD minimum total contract value.
- **Required Advance**: Minimum 40% advance milestone ($200.00 USD on $500 floor).
- **Lock State**: Unpaid, pending, review-required, or underpaid projects remain strictly locked (`CommercialGateViolation`).
- **Unlock State**: Production builds are unlocked **only** when verified payments meet or exceed the required advance milestone.

---

## 7. Production Flow Execution

Once verified:
$$\text{PAYMENT\_CONFIRMED} \longrightarrow \text{Commercial Gate Passes} \longrightarrow \text{Production Project Initialized} \longrightarrow \text{Delivery Pipeline Active}$$

- `Customer` record updated to `ONBOARDED`.
- `Project` provisioned with active delivery milestones (`IN_PROGRESS`).
- `ProductionProject` instantiated via `ProductionPipeline.initialize_production_project`.
- Full audit event logged to `DealAuditTrail`.

---

## 8. Automated Card Gateway Status

- **Stripe & Razorpay Integration Status**:
  - Implementation-ready adapter classes exist (`StripePaymentProvider`, `RealRazorpayPaymentProvider`).
  - Both gateways remain **`PAYMENT_PROVIDER_CONFIGURATION_REQUIRED`** until live production credentials (`STRIPE_SECRET_KEY`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`) are explicitly configured in the environment.
  - The customer payment page displays a dedicated status pill:
    `PAYMENT_PROVIDER_CONFIGURATION_REQUIRED: Card processor is in standby mode. Please use Direct Google Pay UPI or Bank Remittance below.`

---

## 9. ZERO FAKE SUCCESS Mandate

The implementation strictly maintains honest commercial boundaries:
- **Customer claim $\neq$ Payment confirmation**: A customer stating they transferred funds or submitting a reference leaves the gate locked.
- **Screenshot $\neq$ Payment confirmation**: Image uploads or payment receipts are not accepted as automated verification.
- **Frontend button $\neq$ Payment confirmation**: Clicking authorize or submit buttons triggers review, never automatic completion.
- **Test payment $\neq$ Real payment**: Mock runs and dry-run sessions are segregated and excluded from commercial delivery unlocking.
- **Implementation $\neq$ Live provider**: Having code for a provider does not mean live payment processing is active without credentials.

---

## 10. Verification Evidence

The payment subsystem was verified using focused, non-destructive test suites:

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-8.4.2, pluggy-1.6.0
rootdir: S:\AGENCY\BY AG, configfile: pytest.ini
collected 33 items

tests/test_payment_production_gate_e2e.py::test_commercial_gate_blocks_unpaid_and_underpaid PASSED [  3%]
tests/test_payment_production_gate_e2e.py::test_customer_reference_submission_does_not_unlock_production PASSED [  6%]
tests/test_payment_production_gate_e2e.py::test_untrusted_source_rejection PASSED [  9%]
tests/test_payment_production_gate_e2e.py::test_operator_verification_unlocks_commercial_gate PASSED [ 12%]
tests/test_payment_production_gate_e2e.py::test_customer_facing_payment_page_renders_and_handles_submit PASSED [ 15%]
tests/test_google_pay_manual_flow.py::test_google_pay_manual_provider_properties PASSED [ 18%]
tests/test_google_pay_manual_flow.py::test_generate_payment_instructions_fields PASSED [ 21%]
tests/test_google_pay_manual_flow.py::test_operator_confirm_payment_flow_and_delivery_unlock PASSED [ 24%]
tests/test_google_pay_manual_flow.py::test_confirm_manual_payment_idempotency PASSED [ 27%]
tests/test_google_pay_manual_flow.py::test_confirm_manual_payment_validations PASSED [ 30%]
tests/test_google_pay_manual_flow.py::test_payment_api_confirm_and_instructions_endpoints PASSED [ 33%]
tests/test_payment_strategy_lifecycle.py::test_payment_provider_abstraction_and_gpay_properties PASSED [ 36%]
tests/test_payment_strategy_lifecycle.py::test_5_stage_payment_lifecycle_google_pay_end_to_end PASSED [ 39%]
tests/test_payment_strategy_lifecycle.py::test_payment_api_endpoints_and_untrusted_rejections PASSED [ 42%]
tests/test_deal_closing_and_payments.py::test_commercial_threshold_minimum_service_value PASSED [ 45%]
tests/test_deal_closing_and_payments.py::test_proposal_approval_gate PASSED [ 48%]
tests/test_deal_closing_and_payments.py::test_payment_order_creation_does_not_mark_paid PASSED [ 51%]
tests/test_deal_closing_and_payments.py::test_cryptographic_webhook_verification_and_tamper_rejection PASSED [ 54%]
tests/test_deal_closing_and_payments.py::test_failed_payment_webhook_transitions_to_failed PASSED [ 57%]
tests/test_deal_closing_and_payments.py::test_advance_payment_and_remaining_balance_calculation PASSED [ 60%]
tests/test_deal_closing_and_payments.py::test_webhook_idempotency_prevents_duplicate_revenue PASSED [ 63%]
tests/test_deal_closing_and_payments.py::test_dry_run_revenue_isolation PASSED [ 66%]
tests/test_deal_closing_and_payments.py::test_human_takeover_blocks_automated_actions PASSED [ 69%]
tests/test_deal_closing_and_payments.py::test_complete_audit_trail_recorded PASSED [ 72%]
tests/test_deal_closing_and_payments.py::test_rest_api_proposal_and_deal_lifecycle PASSED [ 75%]
tests/test_real_intelligence_cycle.py::test_multi_niche_autonomous_intelligence_cycle PASSED [ 78%]
tests/test_real_intelligence_cycle.py::test_failure_categorization_and_bounded_self_correction PASSED [ 81%]
tests/test_real_intelligence_cycle.py::test_failure_pattern_learning_persistence PASSED [ 84%]
tests/test_real_intelligence_cycle.py::test_commercial_advance_payment_gate_enforcement PASSED [ 87%]
tests/test_real_intelligence_cycle.py::test_real_controlled_demo_factory_execution PASSED [ 90%]
tests/test_payments_and_onboarding.py::test_stripe_checkout_session_dry_run PASSED [ 93%]
tests/test_payments_and_onboarding.py::test_stripe_hmac_signature_verification PASSED [ 96%]
tests/test_payments_and_onboarding.py::test_payment_confirmation_and_automatic_onboarding PASSED [100%]

============================= 33 passed in 15.68s =============================
```

---

## 11. Production Status Matrix

| Subsystem / Capability | Production Status | Operational Description |
| :--- | :--- | :--- |
| **Payment Models & Tables** | **IMPLEMENTED** | SQLite/SQLAlchemy schemas for `Payment`, `DealAuditTrail`, and `PaymentWebhookEvent`. |
| **Customer Payment Portal** | **IMPLEMENTED** | `GET /pay/{ref}` and `GET /payment/{ref}` HTML rendering with pricing cards and UPI links. |
| **Reference Submission Form** | **IMPLEMENTED** | `POST /pay/{ref}/submit-reference` and `/api/payments/{id}/submit-reference`. |
| **Operator Verification API** | **IMPLEMENTED** | `POST /api/payments/{id}/confirm` enforcing bank UTR verification and idempotency. |
| **Commercial Gate** | **IMPLEMENTED** | Enforces $500 floor and 40% advance milestone before delivery unlocking. |
| **Automated Test Suite** | **TESTED** | 33/33 payment, commercial gate, and onboarding tests verified passing. |
| **Manual Google Pay UPI** | **CONFIGURED** | VPA `mrsufiyansurve@okaxis` active for customer remittance with unique reference codes. |
| **Automated Card Gateways** | **BLOCKED** | Stripe and Razorpay remain `PAYMENT_PROVIDER_CONFIGURATION_REQUIRED` until live credentials are set. |
| **Live Customer Revenue** | **NONE** | No real external customer payments have been processed; system is in pre-revenue state. |

---

# Agency OS — Global Acquisition Targeting System Walkthrough

## 1. Canonical Targeting Hierarchy
The global acquisition system implements the canonical hierarchy:
$$\text{COUNTRY} \longrightarrow \text{ADMINISTRATIVE REGION} \longrightarrow \text{CITY} \longrightarrow \text{NICHE} \longrightarrow \text{BUSINESS} \longrightarrow \text{RESEARCH} \longrightarrow \text{AUDIT} \longrightarrow \text{QUALIFICATION}$$

- **Country-Specific Administrative Abstraction**: Avoids forcing every jurisdiction into "State". Uses `region_type` metadata:
  - United States $\to$ `State` (Texas, Florida, California, etc.)
  - Canada $\to$ `Province` (Ontario, British Columbia, Alberta, etc.)
  - United Kingdom $\to$ `Region / Nation` (Greater London, North West, Scotland, etc.)
  - United Arab Emirates $\to$ `Emirate` (Dubai, Abu Dhabi, Sharjah, etc.)
  - Saudi Arabia $\to$ `Region` (Riyadh Region, Makkah Region, Eastern Province, etc.)
  - Germany $\to$ `Bundesland` (North Rhine-Westphalia, Bavaria, Hesse, etc.)
  - Japan $\to$ `Prefecture` (Tokyo, Osaka, Kanagawa, etc.)
  - Switzerland $\to$ `Canton` (Zürich, Geneva, Vaud, Zug, Basel-Stadt)
  - India $\to$ `State` (Maharashtra, Karnataka, Telangana, Tamil Nadu, etc.)

## 2. Reusable Global Catalogues
- **Global Countries (`app/acquisition/targeting_catalog.py`)**: 41 initially supported countries complete with ISO codes, currencies, region types, and structured city clusters.
- **Canonical Niches**: 32 canonical niches with uppercase canonical IDs (`HVAC`, `PLUMBING`, `ROOFING`, `DENTAL`, `REAL_ESTATE`, `MEDICAL_CLINICS`, `LEGAL_SERVICES`, etc.).
- **Alias Normalization**: Normalized mappings ensure aliases resolve to standard canonical IDs (e.g., "Air Conditioning", "AC Repair", "Heating & Cooling" $\to$ `HVAC`; "Realty", "Realtor" $\to$ `REAL_ESTATE`; "Doctor Clinic", "Medical Center" $\to$ `MEDICAL_CLINICS`).
- **Country $\to$ Niche Relevance Matrix**: Strict mappings associate commercially viable niches with each supported country.

## 3. Database Safety & Prospect Provenance
- **`TargetDefinition` Model (`app/database/models.py`)**:
  - Columns: `country_code`, `country_name`, `region`, `region_type`, `city`, `niche_id`, `niche_name`, `enabled`, `status` (`ACTIVE`, `PAUSED`, `DISABLED`), `priority` (`P1`, `P2`, `P3`).
  - Unique Constraint: `UniqueConstraint("country_code", "region", "city", "niche_id")` strictly blocks duplicate target definitions.
- **`Business` Model Provenance**:
  - Fields `administrative_region` and `region_type` ensure that every discovered prospect preserves full canonical provenance without identity or location mismatch across pipeline stages.

## 4. Targeting Engine & Discovery Integration
- **`TargetingManager` (`app/acquisition/targeting_manager.py`)**:
  - Priority Queue Generation: Orders active targets by `P1 > P2 > P3` and creation order.
  - Automatic Seed Initialization: Seeds canonical initial targets (US/Texas/Houston/HVAC, US/Florida/Miami/Dental, AE/Dubai/Dubai/Real Estate, SA/Eastern Province/Dammam/HVAC, UK/Greater London/London/Real Estate, IN/Maharashtra/Pune/Dental) on first launch.
  - Real Aggregate Summary: Calculates actual database and catalog metrics (zero fake metrics).
- **Discovery Engine**: `GlobalProspectPool.discover_from_active_targets` and `RealProspectDiscoveryEngine` consume active targets, respecting priority, skipping paused/disabled targets, and attaching provenance to all discovered entities.

## 5. Dashboard UI & Cascading Controls
- Located in the personal dashboard under **Growth $\to$ Acquisition (`#view-global-acquisition`)**:
  - **Global Acquisition Summary KPI Cards**: Real counts for Total Countries (41), Active Regions, Active Cities, Active Niches, Active Targets, and P1 Targets.
  - **Top Active Targets Banner**: Live badges showing priority combinations.
  - **Cascading Filter Form**: Selecting Country updates Region type label and filters Regions; selecting Region filters Cities; selecting Country filters Niches.
  - **Active Targets Table**: Displays configured targets with priority badges, status badges, and action controls (`ENABLE`, `PAUSE`, `REMOVE`).

## 6. Verification Evidence
All 15 focused targeting tests passed cleanly:
```text
tests/test_global_targeting_hierarchy.py::test_country_catalog_loads_all_41 PASSED
tests/test_global_targeting_hierarchy.py::test_region_mapping_types PASSED
tests/test_global_targeting_hierarchy.py::test_city_mapping_clusters PASSED
tests/test_global_targeting_hierarchy.py::test_canonical_niche_catalog_and_aliases PASSED
tests/test_global_targeting_hierarchy.py::test_country_to_region_filtering PASSED
tests/test_global_targeting_hierarchy.py::test_region_to_city_filtering PASSED
tests/test_global_targeting_hierarchy.py::test_country_niche_association PASSED
tests/test_global_targeting_hierarchy.py::test_duplicate_target_prevention PASSED
tests/test_global_targeting_hierarchy.py::test_target_status_transitions PASSED
tests/test_global_targeting_hierarchy.py::test_priority_ordering PASSED
tests/test_global_targeting_hierarchy.py::test_targeting_api_endpoints PASSED
tests/test_global_targeting_hierarchy.py::test_discovery_consumes_active_targets_and_skips_disabled PASSED
tests/test_global_targeting_hierarchy.py::test_prospect_provenance_retention PASSED
tests/test_global_targeting_hierarchy.py::test_hierarchy_validation_rejections PASSED
tests/test_global_targeting_hierarchy.py::test_existing_acquisition_pipeline_compatibility PASSED
============================= 15 passed in 14.57s =============================
```


