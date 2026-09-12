# Checkpoint 01: Orange Auto Outreach State Inconsistency Investigation

**Timestamp:** 2026-09-13T01:55:00+05:30  
**Target Entity:** Orange Auto (Business ID: 30, Outreach Message ID: 12)  
**Production Git Commit SHA:** `369229660e6e24419a551bbd046126a6d1bc3aa2`  
**Local Resolved Git Commit SHA:** `f34a725e47546689ae8e4b58bf744c3dbf5089f5`  
**Production Host:** Azure Standard_B1ms (`20.197.26.215`)

---

## 1. Executive Summary & Problem Statement

In the production database (`/opt/agency/data/agency.db`), `outreach_messages.id = 12` exhibited an apparent state contradiction:
- **`status`:** `'PENDING_APPROVAL'`
- **`approved_at`:** `'2026-09-10 19:17:25.298532'`
- **`sent_at`:** `NULL`

Simultaneously, `pipeline_events` contained Event #65 for `business_id = 30`:
- **`from_stage`:** `'QUALIFIED'`
- **`to_stage`:** `'APPROVAL'`
- **`note`:** `'Outreach draft approved by human operator.'`
- **`created_at`:** `'2026-09-10 19:17:25.309258'`

Yet the dashboard header reported the outreach status as `PENDING_APPROVAL`, while the lead timeline history showed the approval note.

---

## 2. Code Path Tracing & Root Cause Analysis

### Trace Step A: Writing `approved_at` and Event #65
In `app/outreach/queue.py:20-42` (`OutreachApprovalQueue.approve_message`):
```python
msg.status = OutreachStatus.APPROVED.value
msg.approved_at = datetime.utcnow()
# ...
event = PipelineEvent(
    business_id=biz.id,
    from_stage=PipelineStage.QUALIFIED.value,
    to_stage=PipelineStage.APPROVAL.value,
    note="Outreach draft approved by human operator.",
)
db.add(event)
```
On `2026-09-10 19:17:25`, Message #12 was legitimately approved via `approve_message()`, which wrote `approved_at` and Event #65.

### Trace Step B: Reverting Status to `PENDING_APPROVAL` Without Clearing `approved_at`
In `app/outreach/personalization.py:182-208` (`prepare_outreach_for_business`):
When re-evaluating or staging outreach drafts for an existing lead:
```python
existing_q = select(OutreachMessage).where(
    OutreachMessage.business_id == business.id,
    OutreachMessage.status.in_([
        OutreachStatus.PENDING_APPROVAL.value,
        OutreachStatus.APPROVED.value,
    ]),
)
msg = db.execute(existing_q).scalars().first()
if msg:
    target_status = (
        OutreachStatus.APPROVED.value if auto_approve
        else OutreachStatus.PENDING_APPROVAL.value
    )
    msg.subject = subject
    msg.body = body
    msg.status = target_status
    # BUG: approved_at was never reset to None when target_status was PENDING_APPROVAL!
    # BUG: No compensating pipeline event was emitted to record the reset.
```
When `stage_orange_canary.py` regenerated the draft with `auto_approve=False`:
1. `msg.status` was updated to `PENDING_APPROVAL`.
2. `msg.approved_at` retained its timestamp (`2026-09-10 19:17:25.298532`).
3. No resetting pipeline event was generated.
4. `OutreachApprovalQueue` lacked an atomic `reset_to_pending` method.

---

## 3. Files Inspected

1. `app/outreach/queue.py`: Inspected approval/rejection lifecycle methods; confirmed atomic handling was absent for state regressions/resets.
2. `app/outreach/personalization.py`: Inspected `prepare_outreach_for_business` and `generate_outreach_copy`; identified non-atomic state updates and unsupported ROI claims.
3. `app/api/routes.py`: Inspected `GET /api/leads/{id}` and approval endpoints; observed timeline reconciliation gap when historical approval event existed alongside a pending draft.
4. `app/database/models.py`: Inspected `OutreachMessage` and `PipelineEvent` schemas. Confirmed exact columns:
   - `outreach_messages`: `id, business_id, offer_id, recipient_email, subject, body, variant_name, status, sequence_step, confidence, compliance_notes, approved_at, sent_at, created_at, provider, provider_message_id, reply_to, evidence_used, campaign_id`.
   - **Confirmed:** No `approved_by` column exists.
5. `app/auditing/content.py`: Inspected `ContentAuditor`; checked for hardcoded assumptions and template leaks.
6. `app/frontend/static/app.js`: Inspected dashboard lead detail view and timeline rendering.

---

## 4. Files Changed in Resolution Commit (`f34a725`)

1. `app/outreach/queue.py`:
   - Added `reset_to_pending(message_id, reason)` to atomically set `status = PENDING_APPROVAL`, set `approved_at = None`, and insert a `PipelineEvent` documenting the state reset.
2. `app/outreach/personalization.py`:
   - Updated `prepare_outreach_for_business`: When `target_status == OutreachStatus.PENDING_APPROVAL.value`, explicitly set `msg.approved_at = None`.
   - Replaced speculative `"15–30% lost commercial pipeline"` copy with empirical or observational phrasing when `evidence_count == 0`.
3. `app/api/routes.py`:
   - Dynamic timeline reconciliation in `GET /api/leads/{id}`: when the active message is in `PENDING_APPROVAL`, historic approval events are annotated/contextualized so the operator sees the true current approval requirement.
4. `app/auditing/content.py`:
   - Removed hardcoded Austin geographic / niche test leaks (`/service-areas/north-austin`) from general audit rules.
5. `app/frontend/static/app.js`:
   - Clarified UI display between Macro Lead Score (firmographic qualification) and Micro Service Match Fit.
6. `tests/test_orange_auto_readiness_audit.py`:
   - Created comprehensive regression suite covering all 6 audit facets.

---

## 5. Tests Added & Exact Results

Test suite: `tests/test_orange_auto_readiness_audit.py`
- Command: `pytest tests/test_orange_auto_readiness_audit.py -v`
- Execution Result: **6 passed in 6.95s** (100% pass rate)

| Test Name | Result | Verification Focus |
|:---|:---:|:---|
| `test_state_consistency_pending_approval_clears_approved_at` | **PASSED** | Asserts `prepare_outreach_for_business` and `reset_to_pending` clear `approved_at = None` |
| `test_content_auditor_no_geographic_or_niche_leaks` | **PASSED** | Asserts Dubai automotive repair copy has no Dallas/Austin leaks |
| `test_empirical_evidence_safeguards_hypothesis_language` | **PASSED** | Asserts observational/hypothetical framing when empirical count = 0 |
| `test_no_unsupported_roi_claims` | **PASSED** | Asserts absence of unbacked "15-30%" or quantified claims |
| `test_commercial_score_vs_match_fit_distinction` | **PASSED** | Asserts distinct semantic fields for lead scoring vs service fit |
| `test_orange_auto_canary_remains_pending_approval` | **PASSED** | Asserts Orange Auto canary record is strictly `PENDING_APPROVAL` with zero sends |

---

## 6. Current Production State on VPS (`20.197.26.215`)

- **Git Commit:** `369229660e6e24419a551bbd046126a6d1bc3aa2` (clean tree)
- **Service:** `agency.service` is `active (running)`
- **Database Path:** `/opt/agency/data/agency.db` (SQLite WAL)
- **Message #12 Status:** `PENDING_APPROVAL`
- **Message #12 `approved_at`:** `2026-09-10 19:17:25.298532` (Pending reconciliation deploy)
- **Message #12 `sent_at`:** `NULL` (No email sent)
- **Safety Gate:** ActiveOutreachLock + MAX_OUTREACH_PER_DAY=1 + GMAIL_DAILY_CAPACITY=1 active.

---

## 7. Next Safe Step

1. **Deploy Code Update to VPS:** Pull commit `f34a725` to `/opt/agency` on the VPS.
2. **Execute Database State Reconciliation:** Run an atomic reconciliation script on `/opt/agency/data/agency.db` under the `agency` service user to clear the stale `approved_at` timestamp on `outreach_messages.id = 12` (`UPDATE outreach_messages SET approved_at = NULL WHERE id = 12 AND status = 'PENDING_APPROVAL';`) and insert a reconciling `PipelineEvent`.
3. **Restart Service & Verify:** Restart `agency.service` and verify `systemctl status agency.service` and endpoint health.
4. **Final Gate:** Orange Auto #12 remains strictly `PENDING_APPROVAL` awaiting explicit manual human operator authorization.
