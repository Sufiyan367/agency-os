# Checkpoint 04: Generic Reusable Demo Factory & Client-Facing Renderer Architecture

**Timestamp:** 2026-09-13T04:00:00+05:30  
**Phase:** Phase 19 Refactoring & Generalization  
**Service Status:** `agency.service` is `active (running)`  
**Health Check:** `HEALTHY`  
**Production Invariants:**
- `AUTH_ENABLED=true` on production daemon (unmodified).
- `/opt/agency/data/agency.db` completely untouched (0 emails sent, 0 live mutations).
- Orange Auto canary (ID: 12, Business: 30) strictly preserved: `status = PENDING_APPROVAL`, `approved_at = NULL`, `sent_at = NULL`.
- Daily outbound capacity: 1/1 remaining (`sent_today = 0`).

---

## 1. Executive Summary

Agency OS previously generated demo packages containing hardcoded branching logic tailored specifically around a single canary prospect (Orange Auto) and a single service model (AI Receptionist voice calls).

Per system directive: **Orange Auto is only the first production canary used to validate the pipeline, NOT the product architecture.**

We have refactored the demonstration subsystem into a universal, generic, data-driven **Demo Factory** (`app/delivery/demo_factory.py`) and universal client-facing **Demo Renderer** (`app/delivery/demo_renderer.py`). The system now features:
1. **Clean Separation of Concerns**: Internal operational metrics (scores, raw audit deficiencies, internal database IDs, pipeline stages, file paths) are completely decoupled from client-safe presentation artifacts.
2. **Universal Data-Driven Renderer**: A single, responsive Tailwind CSS frontend that contains zero hardcoded business names and zero niche branching logic.
3. **Data-Driven Interactive Demonstrations**: Automatically mounts appropriate interactive modules based on the service:
   - `CALL_SIMULATOR`: Audio playback, dialogue transcript, interactive controls, SMS & calendar dispatch indicators.
   - `CHAT_SIMULATOR`: 24/7 conversational lead qualification, quick-replies, instant lead triage.
   - `SPEED_COMPARATOR`: Interactive before/after latency toggle, TTFB metrics, LCP, and edge caching verification.
   - `WORKFLOW_STEPPER`: Multi-stage operational automation pipeline with inspectable data payloads.
   - `ROI_CALCULATOR`: Dynamic volume sliders computing hours saved and revenue recovered.
4. **Public Prospect Route (`GET /demo/{business-slug}`)**: Directly accessible by prospective clients without requiring operator session cookies or dashboard authentication, protected by CSP, `X-Frame-Options: SAMEORIGIN`, and automated secret scrubbing.
5. **Multi-Niche Verification**: 100% verified across Automotive, Roofing, Dental, and HVAC/Clean Energy fixtures through the exact same demo factory and renderer without code changes.

---

## 2. Architecture & Data Flow

```
Agency OS Intelligence Layer (Catalog, Matcher, Requirements Engine, Audits)
    │
    ▼
Demo Factory (`app/delivery/demo_factory.py`)
    │  • Extracts verified business facts (Name, Domain, City, Country, Services)
    │  • Derives safe opportunity framing (No fabricated claims, no raw deficit dumps)
    │  • Maps catalog service & capabilities (Lead Qual, Voice, Speed, CRM, AP, Scheduling)
    │  • Selects interactive scenario type (Call, Chat, Speed, Workflow, ROI)
    │  • Builds client-safe configuration (`ClientSafeDemoConfig`)
    │
    ▼
Demo Configuration & JSON Spec (`data/artifacts/demos/{demo_id}_spec.json`)
    │
    ▼
Generic Demo Renderer (`app/delivery/demo_renderer.py`)
    │  • 100% data-driven, universal Tailwind HTML/JS renderer
    │  • Zero hardcoded business names, zero hardcoded niche logic
    │  • Dynamically mounts scenario-specific interactive component
    │
    ▼
Deterministic QA Engine (`app/delivery/demo_qa.py`)
    │  • Validates 8+ quality gates (Identity, Pricing Floor, Placeholders, Structure,
    │    Requirements, Deterministic Checksum, and Zero Internal Data Leakage)
    │
    ▼
Delivery Endpoints (`app/api/routes.py`)
    ├── Public Prospect Landing: `GET /demo/{business-slug}`
    └── Internal Operator Preview: `GET /api/leads/{lead_id}/demo` & `/preview`
```

---

## 3. Key Components Implemented

### 3.1 Client-Safe Demo Schema (`app/delivery/demo_models.py`)
- `BusinessIdentity`: `business_name`, `domain`, `slug`, `niche`, `city`, `country`, `phone`, `verified_facts`.
- `OpportunitySummary`: `headline`, `subheadline`, `diplomatic_observations`, `projected_impact`.
- `SolutionSpecification`: `service_id`, `service_title`, `service_category`, `scope_deliverables`, `specifications`, `turnaround_days`, `total_price_usd`, `advance_amount_usd`.
- `InteractiveScenario`: `scenario_type`, `title`, `description`, `scenario_badge`, `payload`.
- `ClientSafeDemoConfig`: Encapsulates complete client demonstration state with SHA-256 build checksum.

### 3.2 Universal Client-Facing Demo Renderer (`app/delivery/demo_renderer.py`)
- Universal responsive HTML5/Tailwind layout.
- Renders:
  - Header with business branding, service title, fixed pricing, and turnaround timeframe.
  - Executive Opportunity Overview (Verified Baseline Facts & Diplomatic Observations).
  - Dynamic Interactive Demonstration Module (`CALL_SIMULATOR`, `CHAT_SIMULATOR`, `SPEED_COMPARATOR`, `WORKFLOW_STEPPER`, or `ROI_CALCULATOR`).
  - Itemized Technical Specifications & Staging Verification table.
  - Turnkey Scope Deliverables with checkmarks.
  - Commercial Authorization Card with fixed fee, 40% milestone deposit, and completion balance.
  - Verification footer with deterministic build checksum.

### 3.3 Demo Factory Refactoring (`app/delivery/demo_factory.py`)
- Replaced monolithic hardcoded receptionist branching with generic data-driven builder:
  - `build_client_safe_demo_config(business, packet, offer, audit)`
  - Grounding on verified business facts only (zero unsupported claims).
  - Diplomatic opportunity framing (zero fabricated problems).
  - Automatic scenario selection driven by matched service keywords.
  - Outputs `{demo_id}.html` and client-safe `{demo_id}_spec.json`.
  - Indexes demo slug in `Artifact.metadata_json["slug"]`.

### 3.4 Quality Assurance Engine Hardening (`app/delivery/demo_qa.py`)
- Preserves all 8 deterministic QA gates:
  1. `FILE_EXISTENCE_HTML`
  2. `FILE_EXISTENCE_SPEC`
  3. `IDENTITY_INTEGRITY`
  4. `COMMERCIAL_ALIGNMENT`
  5. `ZERO_PLACEHOLDERS` (enhanced to verify zero internal data leakage)
  6. `STRUCTURAL_VALIDITY`
  7. `REQUIREMENTS_COVERAGE`
  8. `DETERMINISTIC_CHECKSUM`
- Added standalone method `verify_zero_internal_leakage(html)` asserting:
  - No server filesystem paths (`C:\`, `/opt/agency/`).
  - No internal database foreign keys (`business_id: 12`).
  - No internal pipeline stages (`PENDING_APPROVAL`, `QUALIFIED_REPLY`).
  - No sensitive API keys or tokens.

### 3.5 Public Prospect Endpoint (`app/api/routes.py` & `app/api/app.py`)
- Added `GET /demo/{business_slug}`:
  - Look up demo artifact by slug or matching business name/domain.
  - Serves sanitized, security-hardened client demo HTML.
  - Configured auth middleware in `app/api/app.py` to allow public access without login cookies.
  - CSP and framing headers configured (`X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, allowing Tailwind CDN).

---

## 4. Verification & Multi-Niche Test Results

### 4.1 Multi-Niche Generic Test Suite (`tests/test_generic_demo_factory.py`)
Tested 4 distinct commercial niches through the exact same demo factory and renderer:
1. **Automotive Repair** (`Orange Auto Dubai` fixture) -> `CALL_SIMULATOR` (Voice / After-Hours Booking).
2. **Roofing Contractor** (`Apex Roofing Systems` fixture) -> `CHAT_SIMULATOR` (AI Lead Qualification & Scope Intake).
3. **Dental Practice** (`Beacon Dental Care` fixture) -> `WORKFLOW_STEPPER` (Appointment Scheduling & CRM Automation).
4. **Commercial HVAC / Clean Energy** (`Horizon Energy` fixture) -> `SPEED_COMPARATOR` (Web Speed & Conversion Turnaround).

**Results:**
- `test_multi_niche_rendering_through_same_factory`: **PASSED** (all 4 niches passed all 8 QA gates, zero leakage, public endpoint served HTTP 200).
- `test_public_demo_endpoint_404_on_unknown_slug`: **PASSED** (HTTP 404 cleanly returned).
- `test_zero_raw_audit_deficiency_leakage_in_client_demo`: **PASSED** (no internal IDs, scores, or server paths leaked).

### 4.2 Operator Dashboard Demo QA Suite (`tests/test_dashboard_demo_qa_view.py`)
All 8 existing operator dashboard demo tests were executed and passed with 100% backward compatibility:
- `test_lead_demo_api_missing_demo`: **PASSED**
- `test_lead_demo_api_with_valid_demo_and_8_qa_gates`: **PASSED**
- `test_demo_preview_endpoint_serves_html_and_security_headers`: **PASSED**
- `test_demo_preview_scrubs_secrets`: **PASSED**
- `test_no_filesystem_paths_leaked_in_qa_check_details`: **PASSED**
- `test_qa_failure_representation`: **PASSED**
- `test_get_lead_detail_includes_demo_and_proposal`: **PASSED**
- `test_demo_preview_404_handling`: **PASSED**

### 4.3 Full Repository Pytest Regression Run
```
============================== 653 passed, 28 warnings in 900.13s (0:15:00) ==============================
```
- Total tests: **653**
- Passed: **653 (100%)**
- Failed: **0**
- Errors: **0**

---

## 5. Production Invariants & Safety Audit
- **Outreach Message #12**: Unconditionally preserved in `PENDING_APPROVAL` with `sent_at = NULL`.
- **Live Outreach Dispatch**: 0 live emails sent.
- **Production Database**: `/opt/agency/data/agency.db` remained completely isolated and untouched.
- **Production Daemon**: `agency.service` running active and healthy.
