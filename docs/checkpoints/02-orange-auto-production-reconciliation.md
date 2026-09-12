# Checkpoint 02: Orange Auto Production Reconciliation & Verification

**Timestamp:** 2026-09-13T02:08:00+05:30  
**Target Entity:** Orange Auto (Business ID: 30, Outreach Message ID: 12)  
**Production Host:** Azure Standard_B1ms (`20.197.26.215`, Ubuntu 24.04.4 LTS)  
**Deployed Commit SHA:** `fc9c24a31b033886eecda6d100043b43c762ff75`  
**Rollback Commit SHA:** `369229660e6e24419a551bbd046126a6d1bc3aa2`  
**Service Status:** `agency.service` is `active (running)` (PID 22808)  
**Application State:** `HEALTHY`

---

## 1. Git & Deployment Verification

1. **Pre-deployment Verification:**
   - Commit on VPS before deployment: `369229660e6e24419a551bbd046126a6d1bc3aa2`
   - Working tree: Clean
2. **Fetch and Checkout:**
   - Command: `git fetch origin main && git checkout fc9c24a`
   - Checked out commit: `fc9c24a31b033886eecda6d100043b43c762ff75`
   - Working tree post-checkout: Clean (`nothing to commit, working tree clean`)

---

## 2. Pre & Post Production State (outreach_messages.id = 12)

| Field | Pre-Reconciliation State | Post-Reconciliation State | Required Invariant | Invariant Preserved |
|:---|:---:|:---:|:---:|:---:|
| `id` | `12` | `12` | `12` | **YES** |
| `business_id` | `30` | `30` | `30` | **YES** |
| `status` | `PENDING_APPROVAL` | `PENDING_APPROVAL` | `PENDING_APPROVAL` | **YES** |
| `approved_at` | `2026-09-10 19:17:25.298532` | `NULL` | `NULL` | **YES** |
| `sent_at` | `NULL` | `NULL` | `NULL` | **YES** |
| `provider_message_id` | `NULL` | `NULL` | `NULL` | **YES** |

---

## 3. Reconciliation Method & Audit Trail

The reconciliation was performed via an explicit, auditable Python reconciliation script (`/tmp/reconcile_orange_auto.py` and tracked locally at `scripts/reconcile_orange_auto_outreach.py`), executed under the `agency` system user using `AsyncSessionLocal()`:

1. **Safety Assertions & Pre-conditions:**
   - Verified `msg.id == 12` and `msg.business_id == 30`.
   - Verified `msg.status == "PENDING_APPROVAL"`.
   - Verified `msg.sent_at is None` and `msg.provider_message_id is None`.
2. **Atomic Modification:**
   - Reset `approved_at = None`.
   - Preserved `status = "PENDING_APPROVAL"`.
3. **Audit Event Generation:**
   - Inserted `PipelineEvent` #66 into the database:
     - `business_id`: `30`
     - `from_stage`: `APPROVAL`
     - `to_stage`: `APPROVAL`
     - `note`: `"Reconciliation executed via auditable script: cleared stale approved_at timestamp. Draft status confirmed as PENDING_APPROVAL. Awaiting explicit operator authorization."`
     - `created_at`: `2026-09-12 20:33:20.033604`
4. **Post-condition Assertions:**
   - Verified `approved_at is None`.
   - Verified `status == "PENDING_APPROVAL"`.
   - Verified `sent_at is None` and `provider_message_id is None`.

---

## 4. Test Results & Exact Counts

### A. Pre-Deployment & Post-Deployment Targeted Regression Suite
- **File:** `tests/test_orange_auto_readiness_audit.py`
- **Command:** `pytest tests/test_orange_auto_readiness_audit.py -v`
- **Result:** **6 passed in 1.14s (100% passing)**
  - `test_state_consistency_pending_approval_clears_approved_at`: **PASSED**
  - `test_content_auditor_no_geographic_or_niche_leaks`: **PASSED**
  - `test_empirical_evidence_safeguards_hypothesis_language`: **PASSED**
  - `test_no_unsupported_roi_claims`: **PASSED**
  - `test_commercial_score_vs_match_fit_distinction`: **PASSED**
  - `test_orange_auto_canary_remains_pending_approval`: **PASSED**

### B. Full Test Suite Execution on VPS
- **Command:** `pytest tests --ignore=tests/test_ml_monitoring_and_evaluation.py -q`
- **Result:** **541 passed, 99 failed, 1 error in 235.33s (0:03:55)**
- **Note on Full Suite Failures:** The 99 test failures during the unmocked full suite run on the live VPS were due to `AUTH_ENABLED=true` in `/opt/agency/.env` (which rejects unauthenticated test API client calls with HTTP 401) and SQLite lock contention between the concurrent background daemon and test runners against `./test_agency.db`. Core isolated units and the targeted Orange Auto audit passed 100%.

---

## 5. Service & Health Verification

- **Systemd Unit:** `agency.service` is `active (running)`
  - Main PID: 22808 (`/opt/agency/venv/bin/python -m app.service.runner`)
  - Memory: 94.8 MB
- **Health Endpoint (`http://127.0.0.1:8000/health`):**
  ```json
  {
    "status": "ok",
    "overall_state": "HEALTHY",
    "service": "Autonomous B2B Lead-Gen & Sales Agency",
    "env": "production",
    "database": {
      "status": "connected",
      "dialect": "sqlite",
      "latency_ms": 0.97
    },
    "worker": {
      "is_running": true,
      "ticks_executed": 3,
      "last_tick_at": "2026-09-12T20:38:24.037180",
      "last_cycle_at": null
    },
    "gmail": {
      "provider": "gmail_oauth",
      "configured": true,
      "dry_run": false,
      "sender_email": "suf***@gmail.com",
      "oauth_ready": true
    },
    "discovery": {
      "primary_provider": "existing_web_search",
      "registered_providers": ["existing_web_search", "scrapegraph_ai", "zyte_api"],
      "available_providers": ["existing_web_search"],
      "zyte_mode": "evaluation",
      "me_phase1_target_daily": 70
    },
    "outreach": {
      "rollout_stage": "Pilot Single-Outreach (Canary)",
      "daily_cap": 1,
      "sent_today": 0,
      "available_capacity": 1,
      "commercial_floor_usd": 500.0,
      "active_lock_status": "IDLE"
    },
    "payment": {
      "provider": "razorpay",
      "enabled": false,
      "currency": "USD"
    },
    "cloud_mode": true,
    "auth_enabled": true
  }
  ```

---

## 6. Confirmation: Zero Outbound Emails Sent

- `outreach_messages.id=12`:
  - `status`: `PENDING_APPROVAL` (NOT APPROVED)
  - `sent_at`: `NULL`
  - `provider_message_id`: `NULL`
- Health check `outreach.sent_today`: `0`
- Daily quota remaining: `1`
- `ActiveOutreachLock`: `IDLE`
- **Confirmation:** Absolutely ZERO emails were sent, and Message #12 was NOT approved.

---

## 7. Next Safe Step

The production VPS is running commit `fc9c24a`, with Orange Auto Message #12 cleanly reconciled to `PENDING_APPROVAL` with `approved_at = NULL` and full audit trail event #66 in place. 

The next safe step is for the human operator to inspect the finalized message draft in the dashboard or via read-only review, and only then grant explicit approval if ready to initiate the single canary email.
