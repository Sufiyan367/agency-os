# FIRST PAYMENT BLOCKERS & RESOLUTION PLAN

**Milestone**: First Genuine Client Payment ($\ge \$500.00$ USD)  
**Strategy**: Eliminate Operational Friction | Automate Routine Tasks | Reserve Human Control Strictly for Financial Sign-off  
**Baseline**: 289 Tests Passing | Zero Safety Regressions

---

## 1. Concrete Blockers Preventing Real First-Client Transaction

| ID | Blocker Category | Root Cause in Current Code | Production Impact | Required Solution |
| :--- | :--- | :--- | :--- | :--- |
| **BLK-1** | **Contactability Filtering** | `LeadVerificationEngine.verify_lead()` marks leads `VERIFIED` even when `public_email` is `None`. | Pipeline wastes cycles on uncontactable businesses; `prepare_outreach_for_business()` raises `ValueError`. | Filter out prospects without verified emails before queuing for outreach (`public_email.isnot(None)`). |
| **BLK-2** | **No Controlled Live Send Path** | `get_email_provider()` forces `DryRunEmailProvider` unconditionally whenever `EMAIL_DRY_RUN=True`. | Even when owner authorizes an email to a real prospect, the system only simulates dispatch. | Add a controlled `force_live` / `send_live` option on the approval endpoint `/api/queue/{id}/approve` that uses the configured live provider (Resend/SMTP) when credentials are provided, while keeping default batch operations safe. |
| **BLK-3** | **Unautomated Objection & Proposal Drafting** | When an inbound reply arrives with intent `INTERESTED` or `PRICE_REQUEST`, `reply_classifier` updates stage to `QUALIFIED_REPLY`, but does NOT draft a tailored commercial proposal or checkout link. | Owner must manually leave the dashboard, calculate contract terms, create proposal, generate checkout session, and write email response. | System autonomously drafts the commercial proposal ($\ge \$500$), creates the payment link, and drafts the email response referencing the audit findings, queuing it for 1-click owner sign-off. |
| **BLK-4** | **Single-Click Proposal & Payment Dispatch** | The dashboard has no 1-click button to authorize sending the drafted proposal and payment link to the prospect. | Friction in closing the deal; delay between interested reply and receiving invoice link. | Provide `/api/proposals/{id}/send-to-client` endpoint and dashboard button to approve and dispatch the proposal email + checkout link in a single click. |
| **BLK-5** | **Live Credentials Presence (Environmental)** | `.env` has placeholder credentials for email sending (`RESEND_API_KEY`, `SMTP_HOST`) and payment gateway (`STRIPE_SECRET_KEY`, `RAZORPAY_KEY_ID`). | External APIs reject requests with 401 Unauthorized; payment sessions fall back to `mock=true`. | Provide a clear credential validator that detects configured providers and safely switches from simulation to live network transmission when authorized. |

---

## 2. Exact Files / Modules That Need Modification

To resolve BLK-1 through BLK-4 without breaking existing tests:

1. **`app/lead_generation/service.py` & `app/agents/prospect_agent.py`**:
   - Ensure only prospects with verified `public_email` are promoted to `OUTREACH_READY`.
2. **`app/outreach/sender.py`**:
   - Support a controlled live sending pathway (`send_approved_message(..., force_live=True)`) that dispatches via live Resend/SMTP when explicitly requested and credentials exist.
3. **`app/crm/reply_classifier.py`**:
   - In `process_incoming_reply()`, when reply intent is `INTERESTED`, `PRICE_REQUEST`, or `MEETING_REQUEST`:
     - Autonomously generate a commercial `Proposal` record ($\ge \$500.00$).
     - Autonomously generate a checkout session / payment link via active payment provider.
     - Autonomously draft a high-converting objection/value response embedding the payment link and audit deliverables.
4. **`app/api/routes.py`**:
   - Enhance `/api/queue/{message_id}/approve` to accept `send_live: bool = False`.
   - Add `/api/proposals/{proposal_id}/send-to-client` to allow single-click owner authorization to dispatch proposal + payment link.
5. **`app/payments/provider.py`**:
   - Enhance `create_checkout_session` to report clearly when operating in live mode vs simulation.

---

## 3. Minimal Implementation Plan

### Step 1: Lead Contactability Guard
- Update prospect queries to require `public_email.isnot(None)` for outreach qualification.
- Verify tests pass.

### Step 2: Controlled Live Outreach Dispatcher
- Enhance `OutreachSenderAdapter.send_approved_message(session, message_id, force_live=False)`:
  - If `force_live=True`: Resolve live provider (Resend or SMTP). Verify credentials exist. If missing, return clean blocker error rather than crashing.
  - Enforce CAN-SPAM footer, daily limits, suppression check, and $500 floor.
- Expose `send_live` flag on `/api/queue/{message_id}/approve`.

### Step 3: Autonomous Commercial Proposal & Objection Drafter
- Extend `reply_classifier.process_incoming_reply()`:
  - For `INTERESTED` / `PRICE_REQUEST` replies:
    - Auto-create commercial proposal ($\ge \$500$).
    - Auto-generate Stripe/Razorpay payment link.
    - Compose tailored response addressing prospect concerns with link to payment.
    - Queue in dashboard for 1-click human authorization.

### Step 4: Single-Click Proposal & Payment Dispatch Endpoint
- Implement `POST /api/proposals/{proposal_id}/send-to-client` in `routes.py`:
  - Validates proposal $\ge \$500$.
  - Requires operator authorization.
  - Sends email with payment link to prospect.
  - Advances stage to `PROPOSAL_SENT`.

### Step 5: Verification & Regression Testing
- Add targeted unit/integration tests for:
  - Controlled live dispatch validation.
  - Autonomous proposal + payment link generation upon interested reply.
  - Webhook idempotency and automatic `WON` transition.
- Execute full 289-test suite to guarantee zero regressions.
