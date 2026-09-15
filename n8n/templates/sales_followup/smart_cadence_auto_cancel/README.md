# AGY-FOLLOWUP-SmartCadence-AutoCancelOnReply-v1.0

## 1. Overview & Business Use Case
Uncontrolled follow-up spam damages sender reputation and alienates leads. This workflow provides an autonomous, respectful, and deliverability-safe follow-up engine:
- **Max 2 Follow-Ups (3 Touches Total)**: Enforces hard circuit breaker after touch #3 to avoid spam triggers.
- **Business-Day Cadence Spacing**: Step 1 at +3 business days, Step 2 at +4 business days.
- **Instant Auto-Cancellation on Inbound Reply**: If an inbound reply or unsubscribe request is detected, the workflow immediately cancels future follow-ups (`status: "CANCELLED"`), guaranteeing no prospect receives robotic follow-ups after replying.

Derived directly from the Agency OS Follow-up Engine (`app/outreach/followups.py`).

---

## 2. Input Specification
- **Trigger**: HTTP Webhook (POST)
- **Endpoint**: `/webhook/evaluate-followup`
- **Content-Type**: `application/json`

### Example Payload:
```json
{
  "recipient_email": "sarah@apexrealty.com",
  "current_step": 0,
  "has_replied": false,
  "is_unsubscribed": false,
  "last_sent_at": "2026-09-12T10:00:00.000Z"
}
```

---

## 3. Output Specification
- **Response**: Synchronous JSON (`application/json`)
- **Status Codes**:
  - `200 OK`: Evaluated successfully.

### Example Scheduled Output:
```json
{
  "status": "SCHEDULED",
  "recipient_email": "sarah@apexrealty.com",
  "next_step": 1,
  "delay_business_days": 3,
  "template_key": "followup_step_1",
  "should_send": true,
  "scheduled_at": "2026-09-16T00:45:00.000Z"
}
```

### Example Cancelled Output (Reply Detected):
```json
{
  "status": "CANCELLED",
  "recipient_email": "sarah@apexrealty.com",
  "reason": "Inbound reply already received.",
  "next_step": null,
  "should_send": false,
  "evaluated_at": "2026-09-16T00:45:00.000Z"
}
```

---

## 4. Setup Instructions
1. Import `workflow.json` into n8n via **Workflows → Import from File**.
2. Connect your outreach scheduler or cron trigger to evaluate pending candidates.
3. Wire the `true` output of `Should Send Follow-Up?` to your email dispatch adapter (Titan/SMTP/Gmail).

---

## 5. Provenance & License
- **Source Repository**: `https://github.com/Sufiyan367/agency-os` (`app/outreach/followups.py`)
- **Source License**: `PROPRIETARY_AGENCY_OS`
- **Commercialization Status**: `COMMERCIAL_READY`
- **Reference Inspirations**: `Zie619/n8n-workflows` (`sales-cadence-scheduler`).
