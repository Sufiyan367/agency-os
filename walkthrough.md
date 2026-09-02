# Autonomous B2B Lead-Gen & Sales Agency — Production Walkthrough

## 1. Executive Summary & Verification Highlights

The Autonomous B2B Lead-Gen & Sales Agency platform has replaced its production payment layer with **Razorpay as the Primary Payment Provider** while preserving Stripe as an optional secondary provider:
1. **Razorpay Primary Gateway**:
   - **Payment Links**: Native integration with Razorpay Payment Links REST API (`https://api.razorpay.com/v1/payment_links`) supporting customized amounts (in subunits), descriptions, customer contact information, and reminder triggers.
   - **Cryptographic Webhook Verification**: Constant-time HMAC-SHA256 signature verification via `X-Razorpay-Signature`.
   - **Automated Webhook Endpoint**: Dedicated `POST /api/webhooks/razorpay` endpoint processing `payment_link.paid`, `payment.captured`, and `order.paid` events.
   - **Idempotency**: Strict reference ID checking prevents duplicate records or re-onboarding on retried webhook events.
   - **CRM WON Progression & Delivery**: Immediately advances `Business.pipeline_stage` to `PipelineStage.WON`, provisions `Customer` and `Project` records, and compiles Onboarding Packets.
2. **Preserved Stripe Optionality**: `StripePaymentProvider` remains fully functional and accessible by setting `PAYMENT_PROVIDER=stripe`.
3. **Unified Gateway Abstraction**: `get_active_payment_provider()` provides a seamless interface (`create_payment_link`, `verify_webhook_signature`, `fetch_completed_payments`) used uniformly across the API, Persistent Worker, and CLI.
4. **100% Automated Test Health**: **51 / 51 automated tests passing green** in 31.46s.

---

## 2. Razorpay Production Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          RAZORPAY PAYMENT LAYER                             │
│                                                                             │
│  1. Operator / Lead Action                                                 │
│     ┌────────────────────────┐         ┌─────────────────────────────────┐  │
│     │ CLI: checkout <biz_id> │         │ Web Control Center: "Pay Now"   │  │
│     └───────────┬────────────┘         └────────────────┬────────────────┘  │
│                 │                                       │                   │
│                 └───────────────────┬───────────────────┘                   │
│                                     │                                       │
│  2. Link Generation                 ▼                                       │
│     ┌────────────────────────────────────────────────────────────────────┐  │
│     │ RazorpayPaymentProvider.create_payment_link()                      │  │
│     │  - Live API: POST https://api.razorpay.com/v1/payment_links        │  │
│     │  - Dry Run: https://rzp.io/i/plink_test_{uuid}                     │  │
│     │  - Subunit currency conversion (USD Cents / INR Paise)             │  │
│     └───────────────────────────────┬────────────────────────────────────┘  │
│                                     │                                       │
│  3. Customer Payment                ▼                                       │
│     ┌────────────────────────────────────────────────────────────────────┐  │
│     │ Customer Completes Payment on Razorpay Hosted Page                 │  │
│     └───────────────────────────────┬────────────────────────────────────┘  │
│                                     │                                       │
│  4. Webhook Dispatch                ▼                                       │
│     ┌────────────────────────────────────────────────────────────────────┐  │
│     │ POST /api/webhooks/razorpay                                        │  │
│     │  - Header: X-Razorpay-Signature                                    │  │
│     │  - HMAC-SHA256(webhook_secret, raw_payload) verification           │  │
│     │  - Event: payment_link.paid / payment.captured                     │  │
│     └───────────────────────────────┬────────────────────────────────────┘  │
│                                     │                                       │
│  5. CRM WON Transition & Delivery   ▼                                       │
│     ┌────────────────────────────────────────────────────────────────────┐  │
│     │ PaymentService.confirm_payment_and_onboard()                       │  │
│     │  - Idempotency Check (Payment.reference_id)                        │  │
│     │  - Business.pipeline_stage -> WON                                  │  │
│     │  - Customer & Project Provisioning                                 │  │
│     │  - Onboarding Intake Packet & Delivery Audit Generation            │  │
│     └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Test Suite Verification (51 / 51 Passing)

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
tests/test_persistent_worker.py::test_persistent_worker_tick_execution PASSED [ 62%]
tests/test_persistent_worker.py::test_persistent_worker_automatic_payment_detection PASSED [ 64%]
tests/test_persistent_worker.py::test_persistent_worker_error_recovery PASSED [ 66%]
tests/test_persistent_worker.py::test_persistent_worker_status PASSED    [ 68%]
tests/test_razorpay_provider.py::test_razorpay_payment_link_generation_dry_run PASSED [ 70%]
tests/test_razorpay_provider.py::test_razorpay_webhook_signature_verification PASSED [ 72%]
tests/test_razorpay_provider.py::test_razorpay_webhook_payment_link_paid_advances_to_won_and_onboards PASSED [ 74%]
tests/test_razorpay_provider.py::test_razorpay_webhook_idempotency_avoids_duplicate_onboarding PASSED [ 76%]
tests/test_razorpay_provider.py::test_get_active_payment_provider_default_and_toggle PASSED [ 78%]
tests/test_reply_intelligence_and_crm.py::test_reply_classification_and_pipeline_advancement PASSED [ 80%]
tests/test_reply_intelligence_and_crm.py::test_unsubscribe_reply_adds_to_suppression PASSED [ 82%]
tests/test_scoring_and_offers.py::test_scoring_and_offer_generation PASSED [ 84%]
tests/test_security_ssrf.py::test_ssrf_disallows_loopback_and_internal_ips PASSED [ 86%]
tests/test_security_ssrf.py::test_ssrf_allows_public_domains PASSED      [ 88%]
tests/test_security_ssrf.py::test_domain_normalization PASSED            [ 90%]
tests/test_security_ssrf.py::test_email_validation PASSED                [ 92%]
tests/test_windows_service.py::test_windows_service_status_installed_and_running PASSED [ 94%]
tests/test_windows_service.py::test_windows_service_status_not_installed PASSED [ 96%]
tests/test_windows_service.py::test_windows_service_install_mocked PASSED [ 98%]
tests/test_windows_service.py::test_windows_service_uninstall_mocked PASSED [100%]

======================= 51 passed, 1 warning in 31.46s ========================
```

---

## 4. Configuration Reference (`.env`)

```ini
# Payment Provider Selection
PAYMENT_PROVIDER=razorpay            # 'razorpay' (default), 'stripe', 'dry_run'
PAYMENTS_ENABLED=false               # Set 'true' for live API calls

# Razorpay Credentials (Primary)
RAZORPAY_KEY_ID=rzp_live_xxxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxx
RAZORPAY_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxx
RAZORPAY_CURRENCY=USD                # USD, INR, etc.

# Stripe Credentials (Optional Secondary)
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxx
```
