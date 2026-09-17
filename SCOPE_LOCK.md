# AGENCY OS — REVENUE-FIRST SCOPE LOCK
**Permanent Architectural & Operational Mandate**  
**Effective Date:** September 17, 2026  
**Operating Mode:** REVENUE EXECUTION MODE  

---

## 1. HARD SCOPE LOCK DECLARATION

From this point forward, Agency OS development priority is permanently locked to only **THREE** business-critical domains:

| Priority | Focus Domain | Core Mandate |
| :---: | :--- | :--- |
| **P0** | **PAYMENT / REVENUE CONVERSION** | Turn interested prospects into paid clients (+ floor, 40%+ advance, verified payment). |
| **P0** | **DEMO FACTORY / DEMO-TO-DEAL** | Generate high-fidelity, evidence-grounded interactive prototypes upon DEMO_REQUESTED. |
| **P0** | **LEAD ACQUISITION / QUALITY** | Maintain autonomous global discovery, deep research, auditing, and quality-first qualification. |

**Everything else is in CHANGE FREEZE / MAINTENANCE-ONLY.**  
No new microservices, Go migrations, new databases, message queues, event buses, cosmetic dashboard redesigns, or experimental features.

---

## 2. P0 DOMAIN SPECIFICATIONS

### A. PAYMENT & REVENUE CONVERSION
- **Target Funnel**: QUALIFIED LEAD → INTERESTED → DEMO_REQUESTED → DEMO_READY → PROPOSAL → PAYMENT_PENDING → PAYMENT_REVIEW_REQUIRED → PAYMENT_CONFIRMED → PRODUCTION_AUTHORIZED
- **Core Guardrails**:
  - Strict **\ USD commercial floor** (no deals or proposals below \).
  - Strict **40% minimum advance requirement** before production kickoff.
  - Mandatory **human payment verification** (CEO/operator must verify reference/funds).
  - Production builds and deliverable handovers unlock **only after verified payment**.
  - Idempotent payment processing and underpayment protection.

### B. DEMO FACTORY (DEMO-TO-DEAL CONVERSION)
- **Target Funnel**: DEMO_REQUESTED → REQUIREMENTS → DEMO SPEC → GENERATION → BUILD → QA → PUBLIC DEMO → CUSTOMER REVIEW → PROPOSAL
- **Core Guardrails**:
  - **No generic demos**: Every demo must be customer-specific, grounded in real website audit evidence.
  - **Explicit trigger only**: Demos are generated **only** upon prospect entering DEMO_REQUESTED.
  - **Sandbox isolation**: Demo sandbox and demo API tokens must never mutate production data or real business records.
  - **Fast build & automated QA**: Rapid turn-around with responsive mobile/desktop UI.

### C. LEAD ACQUISITION & LEAD QUALITY
- **Target Funnel**: GLOBAL DISCOVERY → VALIDATION → RESEARCH → AUDIT → QUALIFICATION → OFFER SELECTION → PERSONALIZED OUTREACH → REPLY DETECTION
- **Core Guardrails**:
  - **Quality > Quota**: Never dispatch low-quality leads simply to consume capacity.
  - **Global dynamic portfolio**: Dynamic countries, regions, and niches (not locked to 1 city or fixed 7-market limit).
  - **200/day global ceiling**: Absolute maximum outbound rate across all corridors.
  - **Hard exclusions**: Strictly exclude India (IN), Pakistan (PK), and Israel (IL).
  - **CEO Gate**: Every outreach draft must pass human CEO review before dispatch.

---

## 3. CANONICAL REVENUE FUNNEL & KPIS

`
DISCOVERED → VERIFIED → RESEARCHED → AUDITED → QUALIFIED (Score ≥ 55)
                                                    │
                                                    ▼
               OUTREACH (CEO Approved) → REPLIED → INTERESTED
                                                    │
                                                    ▼
               DEMO_REQUESTED → DEMO_READY → PROPOSAL → PAYMENT_CONFIRMED → PRODUCTION
`

- **Primary KPI**: Real verified payments received.
- **Secondary KPIs**: Proposals accepted, demos reviewed, positive intent replies, qualified leads.
- **Subordinate Metrics**: Raw discovery count, audit count (operational telemetry only).

---

## 4. DEFECT & TASK CLASSIFICATION

When any issue or work item is evaluated:
- **P0**: Blocks payment, demo generation, or qualified lead flow $\to$ **Immediate action**.
- **P1**: Materially harms conversion in payment, demo, or lead acquisition $\to$ **High priority**.
- **P2**: Reliability defect in payment, demo, or lead acquisition $\to$ **Scheduled fix**.
- **P3**: Minor optimization $\to$ **Deferred**.
- **P4**: Cosmetic or styling tweak $\to$ **Deferred**.

**Engineering Budget Test**:  
*"Does this directly improve Payment, Demo Conversion, or Qualified Lead Acquisition?"*  
- If **NO** $\to$ **Decline or Defer**.  
- If **YES** $\to$ **Proceed under strict regression testing**.

---

## 5. REALITY RULE
No claim of "customer acquired", "revenue generated", or "demo converted" without immutable database records and real external verification. Strict telemetry separation is enforced between:
1. TEST (Automated local fixtures / mock runs)
2. CANARY (Controlled internal dispatches to verify infrastructure)
3. REAL_EXTERNAL (Authentic prospective client commercial interactions)
