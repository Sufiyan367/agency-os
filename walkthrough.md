# AGENCY OS — COMPREHENSIVE ARCHITECTURE & OPERATIONAL WALKTHROUGH

## 1. System Overview

Agency OS is a deterministic, evidence-grounded operating system designed to engineer revenue per qualified lead, elevate reply quality, streamline demo conversion, and enforce strict delivery discipline.

The platform has transitioned from an early automated crawler model to **Smart Revenue Engineering**: an operational architecture combining empirical research, epistemic truthfulness, isolated interactive demo generation, multi-stage commercial gates, and human-in-the-loop executive control.

### Core System Principles:
- **Evidence-Grounded**: Every outreach claim and commercial proposal is anchored in verifiable digital observations.
- **Strict Epistemic Boundaries**: Hard architectural separation between factual observations, analytical inferences, and strategic recommendations.
- **Safety First**: Automated actions stop at sensitive boundaries (outreach dispatch, payment verification, contract authorization, production deployment).
- **Zero Fabricated Claims**: No fake testimonials, simulated case studies, synthetic reviews, or artificial revenue attribution.
- **Isolated Sandboxes**: Interactive demos and staging environments operate in strict isolation without real customer side-effects.

---

## 2. Canonical Customer Journey

The complete operational lifecycle spans from geographic targeting to recursive empirical learning:

```
GLOBAL TARGETING
    │
    ▼
DISCOVERY
    │
    ▼
ENTITY VALIDATION ──▶ [Mismatch? ──▶ OUTREACH_VALIDATION_FAILED]
    │
    ▼
EMAIL VALIDATION
    │
    ▼
BUSINESS RESEARCH
    │
    ▼
PAIN / EVIDENCE DETECTION (Epistemic Observation)
    │
    ▼
COMMERCIAL FIT (Operational Prioritization)
    │
    ▼
OFFER MATCHING (Observed Pain ──▶ Capability Catalog)
    │
    ▼
PERSONALIZED OUTREACH ──▶ CEO REVIEW & APPROVAL ──▶ DISPATCH (Max 200/day)
    │
    ▼
REPLY CLASSIFICATION ──▶ Next-Best Action
    │
    ▼
DEMO_REQUESTED (Explicit Customer Request Required)
    │
    ▼
REQUIREMENTS & DEMO SPECIFICATION
    │
    ▼
DEMO GENERATION & BUILD (Isolated Sandbox)
    │
    ▼
8-GATE DEMO QA ──▶ [Pass? ──▶ PUBLIC DEMO URL]
    │
    ▼
CUSTOMER REVIEW & INTERACTION
    │
    ▼
PROPOSAL PRESENTATION
    │
    ▼
40% ADVANCE PAYMENT INITIATION ($500 Project Floor / $200 Advance)
    │
    ▼
CUSTOMER PAYMENT & UTR SUBMISSION ──▶ PAYMENT_REVIEW_REQUIRED
    │
    ▼
HUMAN OPERATOR VERIFICATION ──▶ PAYMENT_CONFIRMED
    │
    ▼
PRODUCTION_BUILD_AUTHORIZED
    │
    ▼
CUSTOMER PROJECT PROVISIONING & SPECIFICATION FREEZE
    │
    ▼
PRODUCTION BUILD (Separate Production Architecture)
    │
    ▼
10-GATE PRODUCTION QA
    │
    ▼
DEPLOYMENT & ROLLBACK READINESS
    │
    ▼
CUSTOMER HANDOVER & CREDENTIAL TRANSFER
    │
    ▼
RETENTION & EXPANSION (Human-Approved Scope Expansion)
    │
    ▼
EMPIRICAL LEARNING LOOP (Feeds Targeting, Fit, Matching, Outreach, & Efficiency)
```

---

## 3. Global Targeting

The acquisition engine enforces a strict geographic and administrative hierarchy:

$$\text{COUNTRY} \longrightarrow \text{ADMINISTRATIVE REGION} \longrightarrow \text{CITY} \longrightarrow \text{NICHE}$$

### Administrative Layering:
Rather than forcing all jurisdictions into generic labels, the catalog dynamically adapts to sovereign regional types:
- **United States**: `State` (Texas, California, Florida, New York, etc.)
- **Canada**: `Province` (Ontario, British Columbia, Alberta, etc.)
- **United Kingdom**: `Region / Nation` (Greater London, Scotland, North West, etc.)
- **United Arab Emirates**: `Emirate` (Dubai, Abu Dhabi, Sharjah, etc.)
- **Saudi Arabia**: `Region` (Riyadh, Makkah, Eastern Province, etc.)
- **Germany**: `Bundesland` (Bavaria, North Rhine-Westphalia, Hesse, etc.)
- **Japan**: `Prefecture` (Tokyo, Osaka, Kanagawa, etc.)
- **Switzerland**: `Canton` (Zürich, Geneva, Vaud, Zug, etc.)

### Autonomous Multi-Market Acquisition Engine:
Agency OS does not require the CEO to manually select markets for daily operations. An autonomous multi-market portfolio manager (`app/market_intelligence/autonomous_market_engine.py`) continuously evaluates global market evidence and maintains a balanced, dynamic acquisition portfolio across concurrent markets (`Country × Region × City × Niche`):
- **Parallel Market Operations**: Multiple primary and secondary markets operate concurrently (e.g., US, UK, UAE, Canada, Germany, Japan, Switzerland, Australia).
- **Portfolio Allocation (Exploit vs. Explore)**:
  - **70–80% Exploitation Capacity**: Allocated to high-performing, empirically validated markets with demonstrated contactability and positive reply history.
  - **20–30% Exploration Capacity**: Allocated to under-tested or newly seeded markets to continuously discover fresh opportunities and prevent local optima.
- **Global 200 Emails/Day Cap**: The strict global ceiling of 200 emails/day is dynamically distributed across active portfolio markets according to their exploit/explore tier and priority.
- **Empirical Trend Detection Threshold**:
  - Sample size $N < 10 \longrightarrow \mathbf{INSUFFICIENT\_DATA}$ (unreliable).
  - Trend status is flagged as `INSUFFICIENT_DATA` until at least 10 prospect outcomes are observed, preventing premature exploitation or unwarranted exclusion.
- **Explainable Target Reason Codes**:
  - `HIGH_CONTACTABILITY`
  - `HIGH_AUTOMATION_FIT`
  - `POSITIVE_HISTORICAL_OUTCOMES`
  - `HIGH_PAIN_DENSITY`
  - `DATA_REFRESHED`
  - `EXPLORATION_REQUIRED`
  - `CEO_PRIORITY_OVERRIDE`
- **CEO Operational Overrides**:
  - **Pause**: Temporarily suspend discovery in a specific corridor while preserving historical data.
  - **Exclude**: Permanently exclude a specific market from autonomous selection.
  - **Force Priority**: Promote a target to active exploitation immediately with top queue priority.
  - **Emergency Stop**: Instantly suspend all autonomous acquisition globally.
- **Live Operations Telemetry Stream**: Real-time operational state is broadcast via WebSocket (`/ws/agent-activity`) with fallback REST polling, rendering live running operations counters, active portfolio states, and real-time agent event badges directly on the CEO dashboard.

### Disabled Acquisition Markets:
- **India (`IN`)**, **Pakistan (`PK`)**, and **Israel (`IL`)** are hard-coded in `HARD_EXCLUDED_COUNTRIES` and strictly **BLOCKED** from autonomous discovery, targeting, and outreach.
- Historical prospect records and entity associations from these jurisdictions remain preserved in the database for compliance and audit integrity.
- Disabled markets are strictly filtered out at the query level and cannot enter discovery, qualification, or outreach pipelines.

---

## 4. Discovery & Validation

### Pipeline Intake:
- Discovers prospect businesses matching active `P1`/`P2` target definitions (`country_code`, `region`, `city`, `niche_id`).
- Attaches persistent geographic provenance (`administrative_region`, `region_type`) to prevent drift across stages.

### Entity & Identity Validation:
Before any outreach consideration, the system executes cross-attribute identity resolution:
$$\text{Business Name} + \text{Domain} + \text{Geographic Location} + \text{Contact Details}$$
- Must resolve deterministically to the **same physical entity**.
- If any discrepancy is detected (e.g., domain belongs to a franchisee in another city, phone links to an unrelated business, name conflict):
  $$\text{State} \longrightarrow \mathbf{OUTREACH\_VALIDATION\_FAILED}$$
  Outreach generation is immediately halted and quarantined.

### Email Validation:
- Multi-layer syntax, DNS MX record verification, and disposable domain filtering.
- Suppression list checking (opt-outs, legal requests, bounces). Unverified addresses never receive transmissions.

---

## 5. Research / Evidence / Audit

### Epistemic Category Separation:
To eliminate hallucination and ungrounded sales pitches, the system enforces a strict epistemic taxonomy:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                      EPISTEMIC SEPARATION SYSTEM                         │
├──────────────────┬───────────────────────────────────────────────────────┤
│ OBSERVATION      │ Empirically verified fact with direct URL/HTTP proof. │
│                  │ e.g., "Meta viewport tag missing on mobile homepage." │
├──────────────────┼───────────────────────────────────────────────────────┤
│ INFERENCE        │ Analytical deduction clearly demarcated as estimate.  │
│                  │ e.g., "Probable manual appointment intake workflow."  │
├──────────────────┼───────────────────────────────────────────────────────┤
│ RECOMMENDATION   │ Actionable capability proposed to solve friction.     │
│                  │ e.g., "Deploy automated appointment booking intake."  │
└──────────────────┴───────────────────────────────────────────────────────┘
```

### Safety Rules:
- **Observations Require Provenance**: Must include exact source URI, HTTP status, or DOM element evidence.
- **Inferences Never Stated as Facts**: Prohibited from asserting operational details without corroboration.
- **Fabrications Prohibited**: Speculative revenue estimates, headcount claims, and ROI guarantees are strictly forbidden.
- **Country Bias Prohibition**: Geographic location cannot be used as proof of ability to pay or commercial suitability.

---

## 6. Commercial Fit

Commercial Fit is an **operational prioritization score** measuring whether a business exhibits genuine procedural friction that automation can solve.

### Evaluated Operational Signals:
- **Intake Friction**: Absence of online intake forms, broken form submissions, or reliance on raw mailto links.
- **Missed Call Exposure**: Absence of interactive after-hours response mechanisms.
- **Scheduling Friction**: Phone-only booking, multi-day email tag, or missing calendar integrations.
- **Manual Data Entry**: Multi-step PDF forms, unstructured quote inquiries, or disconnected lead flows.
- **Repetitive Support Burden**: Lack of structured FAQs or self-serve status tracking for customers.
- **Visible Workflow Complexity**: High-touch service requirements requiring multi-party handoffs.

> [!IMPORTANT]
> **Commercial Fit $\neq$ Ability to Pay.**  
> A high commercial fit score indicates high operational friction where software adds value. It does **not** guarantee budget, solvency, or creditworthiness.

---

## 7. Offer Matching

The Offer Matching Engine maps observed operational bottlenecks directly to canonical agency capabilities:

$$\text{OBSERVED PAIN} \longrightarrow \text{MATCHED CAPABILITY} \longrightarrow \text{DEMO BLUEPRINT} \longrightarrow \text{PROPOSAL SCOPE}$$

### Canonical Capability Catalog:
| Observed Business Pain | Matched Canonical Capability | Demo Blueprint Reference |
| :--- | :--- | :--- |
| Unanswered after-hours calls / lost inbound calls | **Missed Call Recovery** | `blueprint_missed_call_recovery` |
| Slow form response / delayed manual triage | **Lead Capture / Qualification** | `blueprint_lead_qualification` |
| Repetitive customer inquiries / front-desk load | **AI Customer Concierge / Receptionist** | `blueprint_customer_concierge` |
| Phone tag for appointments / calendar conflicts | **Appointment Automation** | `blueprint_appointment_scheduling` |
| Manual data re-entry across CRM and billing tools | **CRM Automation** | `blueprint_crm_sync_pipeline` |

*No speculative or uncatalogued capability names are generated by the engine.*

---

## 8. Outreach & Reply Handling

### Operational Safeguards:
- **Verified Deliverability**: Transmissions permitted only to verified, deliverable business mailboxes.
- **Suppression List Compliance**: Automatic exclusion of unsubscribed recipients, complaint addresses, and competitor domains.
- **Provider Cadence Caps**: System-wide operational ceiling of **200 emails per day** across providers to preserve domain reputation.
- **No Performance Guarantees**: A 200/day volume cap is an infrastructure protection threshold, not a guarantee of replies, meetings, or deals.
- **CEO Approval Mandate**: All cold outreach drafts enter `OUTREACH_READY` and require explicit CEO authorization before dispatch.

### Inbound Reply Classification:
Inbound email responses are intercepted, threaded, and classified into deterministic categories:
- `INTERESTED`: General positive inquiry.
- `DEMO_REQUESTED`: Explicit demand to see a working prototype.
- `INFORMATION_REQUEST`: Request for pricing, portfolio, or scope details.
- `NOT_INTERESTED`: Explicit refusal $\to$ Automatic suppression list addition.
- `UNSUBSCRIBE / BOUNCE`: Immediate auto-suppression and sequence termination.

---

## 9. Next-Best Action

Every prospect advances through a discrete, deterministic state transition machine:

```
NEW_QUALIFIED ─────────────▶ AUDIT
                               │
AUDITED ───────────────────▶ OPPORTUNITY_ANALYSIS
                               │
OPPORTUNITY_IDENTIFIED ────▶ PERSONALIZE
                               │
OUTREACH_READY ────────────▶ CEO_REVIEW
                               │ (CEO Approves)
OUTREACH_SENT ─────────────▶ WAIT_FOR_REPLY
                               │ (Reply Received)
REPLY_RECEIVED ────────────▶ CEO_NOTIFICATION / PREPARE_RESPONSE
                               │
DEMO_REQUESTED ────────────▶ DEMO_FACTORY
                               │ (8-Gate QA Passes)
DEMO_READY ────────────────▶ PROPOSAL
                               │ (Customer Accepts)
PROPOSAL_ACCEPTED ─────────▶ PAYMENT
                               │ (UTR Verified by Operator)
PAYMENT_CONFIRMED ─────────▶ PRODUCTION
                               │ (10-Gate QA Passes)
DELIVERY_COMPLETE ─────────▶ EXPANSION_ANALYSIS
```

---

## 10. Demo Factory

The Demo Factory constructs tailored, interactive web prototypes designed to prove capability before commercial closing:

$$\text{DEMO\_REQUESTED} \longrightarrow \text{REQUIREMENTS} \longrightarrow \text{DEMO\_SPEC} \longrightarrow \text{BUILD} \longrightarrow \text{8-GATE QA} \longrightarrow \text{PUBLIC DEMO}$$

### Operational Invariants:
1. **Explicit Request Required**: An `INTERESTED` reply does **NOT** trigger demo construction. An explicit `DEMO_REQUESTED` intent is required.
2. **Total Sandbox Isolation**: Demos are sandboxed interactive environments. They use mock dispatchers, simulated notifications, and isolated test databases. Demos **never** trigger real-world customer actions (no real SMS sent to end clients, no real dispatch, no live CRM mutation).
3. **8-Gate Quality Assurance**:
   - Gate 1: Blueprint Structural Integrity
   - Gate 2: Niche Alignment & Metadata Validity
   - Gate 3: UI Rendering & Responsiveness
   - Gate 4: Interactive Sandbox Execution
   - Gate 5: Epistemic Brand Grounding (No Fake Proof)
   - Gate 6: Sandbox Containment (Zero Real-World Calls)
   - Gate 7: Asset Delivery & HTTPS Availability
   - Gate 8: Lead Attribution & Logging
4. **Public URL Authorization**: A public preview URL (`/demo/{slug}`) is generated **only after** all 8 gates pass green.
5. **Sandbox $\neq$ Production**: The demo prototype is a sales-enablement artifact, not production software.

---

## 11. Proposal & Payment

### Manual Google Pay UPI Architecture:
- **Active Beneficiary VPA**: `mrsufiyansurve@okaxis`
- **Beneficiary Name**: `Sufiyan Surve / Agency OS`
- **Direct UPI Protocol**: `upi://pay?pa=mrsufiyansurve@okaxis&pn=Sufiyan%20Surve&am=<advance>&cu=USD&tr=<reference>&tn=Invoice%20<reference>`
- **No Standalone Webhooks**: Standalone UPI transfers do **NOT** provide automated banking callbacks. Verification is performed exclusively via operator reconciliation against banking inward ledgers.
- **Standby Card Gateways**: Stripe and Razorpay integrations exist in code but remain in **`PAYMENT_PROVIDER_CONFIGURATION_REQUIRED`** standby mode until production merchant credentials are configured.

### Commercial Floors & Milestone Structure:
- **Contract Minimum Floor**: **$500.00 USD** minimum total project value.
- **Required Milestone Advance**: **40% Advance** ($200.00 USD minimum on $500 floor) required before engineering authorization.
- **Handover Balance**: **60% Balance** due upon completion of production QA and before production deployment.

### Payment Verification Lifecycle:
$$\text{PROPOSAL} \longrightarrow \text{PAYMENT\_PENDING} \longrightarrow \text{CUSTOMER PAYS} \longrightarrow \text{UTR SUBMITTED} \longrightarrow \text{PAYMENT\_REVIEW\_REQUIRED} \longrightarrow \text{OPERATOR VERIFIES} \longrightarrow \text{PAYMENT\_CONFIRMED}$$

- **Customer Reference Submission**: Submitting a bank UTR updates the status to `PAYMENT_REVIEW_REQUIRED`. Production remains **STRICTLY LOCKED**.
- **Human Verification Requirement**: Operator verifies inward funds in the bank ledger and submits confirmation via `POST /api/payments/{id}/confirm`.
- **Anti-Fraud Controls**: Untrusted sources (`screenshot`, `customer_claim`, `ai_inference`) are rejected with `PermissionError`. Underpayment below the 40% floor is rejected with `ValueError`. Duplicate UTRs trigger replay rejections.

---

## 12. Production Authorization

The Commercial Gate (`operator_learning_engine.enforce_commercial_gate`) controls access to engineering execution:

$$\text{PAYMENT\_CONFIRMED} \longrightarrow \text{Commercial Gate Verification} \longrightarrow \text{PRODUCTION\_BUILD\_AUTHORIZED}$$

### Authorization Criteria:
1. `payment_status == "PAYMENT_CONFIRMED"`
2. `verification_method == "HUMAN_OPERATOR_VERIFICATION"`
3. `amount_paid >= total_amount * 0.40`
4. Total contract value meets or exceeds the **$500.00 USD** commercial floor.

### Project Provisioning:
Upon gate passage:
- `Customer` record updated to `ONBOARDED`.
- `ProductionProject` instantiated with discrete delivery milestones.
- **Specification Freeze**: Deliverable requirements are locked to prevent scope creep.
- Comprehensive audit event recorded in `DealAuditTrail`.

---

## 13. Production Build & QA

Production builds are executed as bespoke, dedicated applications separate from the Demo Factory sandbox.

### 10-Gate Production QA Matrix:
Before deployment authorization, production software must clear 10 non-negotiable verification gates:
1. **Contract Specification Compliance**: All contracted deliverables implemented.
2. **Real Infrastructure Integration**: Live third-party APIs (CRMs, SMS, Email, Calendars) connected with production credentials.
3. **Security & Data Sanitization**: Strict input validation, credential encryption, and zero hardcoded secrets.
4. **Data Isolation & Tenant Security**: Customer data partitioned with strict database tenancy.
5. **Error Recovery & Circuit Breaking**: Graceful degradation on upstream API failure.
6. **Performance & Latency**: Sub-second execution on critical workflow paths.
7. **Responsive UI & Cross-Device Ergonomics**: Validated on mobile, tablet, and desktop viewports.
8. **Logging & Operational Observability**: Structured telemetry and error logging.
9. **Rollback Readiness**: Automated rollback scripts and database migration reversibility verified.
10. **Operator Pre-Delivery Review**: Human engineer inspection and delivery sign-off.

---

## 14. Deployment & Handover

### Deployment Workflow:
1. Staging deployment to isolated tenant namespace.
2. Smoke testing of production webhooks and triggers.
3. DNS configuration, SSL provisioning, and uptime monitoring activation.
4. Production promotion.

### Customer Handover:
- Transfer of administrative credentials and integration keys.
- Delivery of operating documentation, API schemas, and maintenance guides.
- Acceptance sign-off by customer representative.
- Collection of remaining 60% handover balance.

> [!NOTE]
> **Zero False Delivery Claim**: The platform records production delivery completion **only when physical evidence exists**. No fabricated client completions are permitted in system metrics.

---

## 15. Retention / Expansion

Post-delivery client relationships are governed by the Retention & Expansion Engine:

$$\text{DELIVERY\_COMPLETE} \longrightarrow \text{EXPANSION\_ANALYSIS} \longrightarrow \text{GAP IDENTIFICATION} \longrightarrow \text{CEO APPROVAL} \longrightarrow \text{PROPOSAL}$$

### Operational Protocol:
- Analyzes deployed workflows to identify natural expansion opportunities (e.g., initial deployment automated missed calls; expansion opportunity exists for post-service review collection).
- Formulates expansion recommendations based on observed usage.
- **Human Approval Gate**: Expansion proposals are never sent automatically. The CEO must explicitly review, adjust, and approve any outreach to existing clients.
- **Anti-Spam Invariant**: Zero autonomous follow-up spam sent to active paying customers.

---

## 16. Learning Loop

The platform aggregates performance traces across all lifecycle dimensions:

$$\text{TARGET} \to \text{COUNTRY} \to \text{CITY} \to \text{NICHE} \to \text{PAIN} \to \text{OFFER} \to \text{VARIANT} \to \text{REPLY} \to \text{DEMO} \to \text{PAYMENT} \to \text{DELIVERY}$$

### Feedback Loops:
- **Targeting**: Deprioritizes low-yield city/niche segments; promotes high-conversion combinations.
- **Commercial Fit**: Calibrates friction signal weighting based on verified closed deals.
- **Offer Matching**: Identifies highest-converting capability mappings per vertical.
- **Outreach**: Refines email framing variants based on verified positive reply rates.
- **Delivery Efficiency**: Feeds delivery timing data into future project scope estimates.

### Statistical Safety Safeguard:
$$\text{Sample Size } (N) < 10 \longrightarrow \mathbf{NOT\_ENOUGH\_DATA}$$
- The learning engine refuses to declare segment winners, recommend niche abandonment, or bias outreach models on small sample sizes ($N < 10$).
- Prevents premature algorithmic over-fitting on early variance.

---

## 17. Revenue Attribution

The financial accounting subsystem enforces strict epistemic separation between pipeline expectations and realized earnings:

$$\mathbf{PIPELINE\_VALUE} \neq \mathbf{COLLECTED\_REVENUE}$$

### Absolute Invariants:
1. **Pipeline Value**: Reflects the estimated gross value of leads in qualification, audit, outreach, and proposal stages.
2. **Collected Revenue**: Reflects **only** transactions with `payment_status == "PAYMENT_CONFIRMED"` verified by bank ledger reconciliation.
3. **Excluded from Revenue**:
   - Sent proposals
   - Projected contract values
   - Issued payment requests (`PAYMENT_PENDING`)
   - Unverified customer reference submissions (`PAYMENT_REVIEW_REQUIRED`)
   - Simulated, dry-run, or test sandbox transactions
4. Any financial metric displayed on the dashboard or reported by telemetry must adhere strictly to this distinction.

---

## 18. Safety / Human Gates

Agency OS enforces an explicit division of authority between algorithmic execution and executive control:

```
┌──────────────────────────────────────┬──────────────────────────────────────┐
│       AUTOMATED SYSTEM LAYER         │          EXECUTIVE / CEO GATE        │
├──────────────────────────────────────┼──────────────────────────────────────┤
│ • Geographic target ingestion        │ • Outreach dispatch authorization    │
│ • Prospect discovery & deduplication │ • Live sales conversations & calls   │
│ • Technical audit & evidence parsing │ • Custom price & scope negotiation   │
│ • Commercial fit scoring             │ • Commercial exception approvals     │
│ • Capability catalog offer matching  │ • Bank UTR verification & reconcile  │
│ • Draft personalization generation   │ • Client onboarding approvals        │
│ • Inbound reply classification       │ • Unusual production build decisions │
│ • Demo sandbox generation & 8-gate QA│ • Client expansion offer approval    │
│ • Proposal document preparation      │                                      │
│ • Commercial gate enforcement        │                                      │
│ • Production project provisioning    │                                      │
│ • 10-gate production QA execution    │                                      │
│ • Learning trace telemetry capture   │                                      │
└──────────────────────────────────────┴──────────────────────────────────────┘
```

> [!WARNING]
> **No Autonomous Closing**: The software does **not** autonomously negotiate contracts, sign legal agreements, or verify incoming funds. Commercial transactions require human executive confirmation.

---

## 19. Test Evidence

The platform's behavioral correctness is verified by automated test suites spanning all architecture layers:

### Smart Revenue Engineering Suite:
- **Suite**: `tests/test_smart_revenue_engineering.py`
- **Test Count**: **10 / 10 Passing Green** (11.93s)
- **Verified Capabilities**:
  - `test_opportunity_generation_truthful`: Truthful opportunity generation without hallucinated ROI.
  - `test_evidence_attribution_and_epistemics`: Strict observation vs inference separation.
  - `test_identity_consistency_and_validation`: Entity mismatch rejection (`OUTREACH_VALIDATION_FAILED`).
  - `test_offer_matching_canonical_capabilities`: Canonical capability mapping.
  - `test_next_best_action_canonical_lifecycle`: State progression transitions.
  - `test_empirical_learning_loop_insufficient_data`: Enforces $N < 10$ safeguard.
  - `test_empirical_learning_loop_sufficient_data`: Validates optimization when statistical threshold is met.
  - `test_delivery_efficiency_tracker`: Delivery duration and repair cycle tracking.
  - `test_retention_and_expansion_engine`: Human-gated expansion analysis.
  - `test_revenue_attribution_collected_vs_pipeline`: Strictly segregates pipeline value from collected revenue.

### Demo Factory, Payments & Delivery Verification:
- **Focused Pipeline Suite**: **65 Tests Passing Green** across:
  - `tests/test_demo_factory_pipeline.py`: Automated demo generation and 8-gate QA.
  - `tests/test_payment_production_gate_e2e.py`: End-to-end commercial gate locking and unlocking.
  - `tests/test_google_pay_manual_flow.py`: Manual UPI reference handling and operator verification.
  - `tests/test_payment_strategy_lifecycle.py`: 5-stage payment lifecycle and anti-fraud rejections.
  - `tests/test_deal_closing_and_payments.py`: $500 floor, 40% advance, and idempotent accounting.
  - `tests/test_global_targeting_hierarchy.py`: 41-country catalog and disabled market exclusion.
  - `tests/test_public_business_website.py`: Public website boundary and contact intake.

*Note: Automated tests prove software behavior, contract enforcement, and state transitions. They do not represent real-world customer acquisition, customer satisfaction, or external commercial success.*

---

## 20. Current System Status

Every major platform subsystem is categorized by its actual operational readiness:

| Subsystem / Capability | Operational Status | Technical Description |
| :--- | :--- | :--- |
| **Global Targeting Engine** | **IMPLEMENTED & VERIFIED** | 41-country catalog, priority queues, and canonical niche normalization active. |
| **Disabled Markets Safety** | **IMPLEMENTED & VERIFIED** | India, Pakistan, and Israel strictly excluded from active outbound acquisition. |
| **Entity & Identity Resolver** | **IMPLEMENTED & VERIFIED** | Cross-attribute validation rejects inconsistent prospects (`OUTREACH_VALIDATION_FAILED`). |
| **Research & Evidence Engine** | **IMPLEMENTED & VERIFIED** | 3-tier epistemic separation enforced; zero fabricated ROI claims. |
| **Commercial Fit Engine** | **IMPLEMENTED & VERIFIED** | Evaluates procedural friction signals as an operational prioritization metric. |
| **Offer Matching Engine** | **IMPLEMENTED & VERIFIED** | Strictly constrained to canonical capability catalog and blueprint mappings. |
| **Outreach Safeguards** | **IMPLEMENTED & VERIFIED** | 200/day provider cap, suppression lists, bounce handling, and CEO approval gate. |
| **Reply Classifier & NBA** | **IMPLEMENTED & VERIFIED** | Deterministic state progression across the canonical customer journey. |
| **Demo Factory & 8-Gate QA** | **IMPLEMENTED & VERIFIED** | Isolated sandbox generation; public URLs authorized only upon full QA pass. |
| **Manual Google Pay UPI** | **CONFIGURED & TESTED** | VPA `mrsufiyansurve@okaxis` configured for customer remittances. |
| **Operator Reconciliation** | **IMPLEMENTED & TESTED** | Human verification endpoint (`POST /api/payments/{id}/confirm`) unlocks gate. |
| **Commercial Gate ($500 / 40%)** | **IMPLEMENTED & TESTED** | $500 minimum floor and 40% advance milestone enforced before production. |
| **Automated Card Gateways** | **BLOCKED (STANDBY)** | Stripe & Razorpay adapters ready; blocked awaiting live production credentials. |
| **10-Gate Production QA** | **IMPLEMENTED & TESTED** | Rigorous pre-delivery gate matrix for production applications. |
| **Delivery Efficiency Tracker** | **IMPLEMENTED & TESTED** | Logs delivery duration, first-pass QA success, and repair cycles. |
| **Retention & Expansion Engine** | **IMPLEMENTED & TESTED** | Identifies post-delivery opportunities requiring explicit CEO authorization. |
| **Empirical Learning Loop** | **IMPLEMENTED & TESTED** | Full performance trace aggregation with $N < 10$ statistical guard. |
| **Revenue Accounting** | **IMPLEMENTED & VERIFIED** | Strict segregation between pipeline value and collected revenue. |
| **Sent Outreach History** | **IMPLEMENTED & VERIFIED** | Canonical Sent API (`/api/outreach/sent`), Subtab UI, detail inspector, and realtime SSE cache invalidation. |
| **Live Customer Revenue** | **NONE** | Pre-revenue state; no external customer transactions have settled. |
| **Autonomous Business Closing** | **DISALLOWED** | Human executive oversight required for all commercial and contractual decisions. |

---

## 21. Sent Outreach History Architecture & Forensic Verification

### Forensic Audit of Historical & Live Sends
An end-to-end database trace of all records in `outreach_messages` with `status = 'SENT'` revealed an exact count of **42 sent records**, classified deterministically:

1. **Real External Prospects (8 Records)**:
   - Recipient domains: Real estate and professional services firms in Ireland (`.ie`) and the UK (`.com`).
   - Transmission Rail: Live Titan SMTP (`provider='titan'`, provider message IDs present).
   - Dispatch Timestamps: September 15–16, 2026.
2. **Canary / Internal Verification (1 Record)**:
   - Message ID #72 sent on September 17, 2026 to `hello@automatedagencyos.tech` (`Agency OS Verification Lab`) via Titan SMTP.
3. **Historical / Early Development Scaffolding (33 Records)**:
   - Message IDs 1–34 (excluding #12 which failed delivery), dispatched during pre-September 15 scaffolding runs (`provider=None`).

### Canonical API Architecture
Two canonical endpoints provide operator-only access to sent history:
- `GET /api/outreach/sent`: Supports category filtering (`real_external` [default], `canary`, `historical_test`, `all`), search query across 7 fields (business, domain, recipient, country, city, niche, subject), pagination (`page`, `page_size`), category counters, linked CRM reply state, and follow-up status.
- `GET /api/outreach/sent/{message_id}`: Detailed inspection modal endpoint returning full email body, recipient, approved/sent timestamps, delivery provider headers, compliance notes, linked reply snippet/classification, and follow-up sequence cadence.

### Operator UI & Realtime Integration
- **Subtabs in Approval Queue**: View 4 now provides `#subtab-btn-pending` ("Pending Approval") and `#subtab-btn-sent` ("Sent History") with reactive count badges.
- **Filter Pills & Search**: Operators can switch between "Real External (8)", "Canary (1)", "Historical / Dev (33)", and "All Sent (42)" or execute instant text searches.
- **Inspector Modal**: Clicking any sent row opens `#sent-detail-modal` showing the full message, transmission headers, and reply timeline.
- **Realtime Cache Invalidation**: The Event Projection Map registers `'sentHistory'` under `OUTREACH_SENT`, auto-refreshing the sent history table whenever new emails are dispatched without requiring page reloads.

