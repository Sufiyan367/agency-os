# AGY-CRM-InboundReply-IntentClassifier-v1.0

## 1. Overview & Business Use Case
When cold email outreach generates responses, fast and accurate classification is essential:
- **Instant Intent Categorization**:
  - `POSITIVE`: Lead expresses interest or requests details.
  - `OBJECTION`: Pricing, timing, or existing vendor concerns.
  - `QUESTION`: Queries about capabilities or operational scope.
  - `NOT_INTERESTED`: Clear declination.
  - `UNSUBSCRIBE`: Opt-out / suppression request.
- **Critical Requirement #6 Protection (Requirements First)**:
  - Positively interested leads **do NOT** trigger unprompted demo generation.
  - Instead, the workflow flags `action_required: "NOTIFY_CEO_REQUIREMENTS_GATHERING"` and populates a tailored response aimed at securing a 10-minute discovery call to gather concrete client requirements.
- **Automated Follow-Up Cancellation**:
  - Instantly signals `auto_cancel_followups: true` so no automated sequence emails are mistakenly dispatched to an active conversation.

Derived directly from the Agency OS CRM Reply Classifier (`app/crm/reply_classifier.py`).

---

## 2. Input Specification
- **Trigger**: HTTP Webhook (POST)
- **Endpoint**: `/webhook/classify-reply`
- **Content-Type**: `application/json`

### Example Payload:
```json
{
  "sender_email": "john@targetbusiness.com",
  "business_id": 204,
  "message_body": "Hi there, this looks interesting. How much does your service cost, and can we schedule a quick call?"
}
```

---

## 3. Output Specification
- **Response**: Synchronous JSON (`application/json`)
- **Status Codes**:
  - `200 OK`: Classified successfully.
  - `400 Bad Request`: Missing `message_body`.

### Example Success Output:
```json
{
  "status": "PROCESSED",
  "business_id": 204,
  "sender_email": "john@targetbusiness.com",
  "intent": "POSITIVE",
  "action_required": "NOTIFY_CEO_REQUIREMENTS_GATHERING",
  "auto_cancel_followups": true,
  "demo_generation_held": true,
  "suggested_response": "Glad to connect! To ensure we prepare the exact right solution for your team, could you share your primary goals or let us know a convenient time for a brief 10-minute discovery call?",
  "classified_at": "2026-09-16T00:45:00.000Z"
}
```

---

## 4. Setup Instructions
1. Import `workflow.json` into n8n via **Workflows → Import from File**.
2. Connect your incoming email parser (e.g. Gmail Webhook, Mailgun Inbound, Titan IMAP poller) to the trigger.
3. Wire the `POSITIVE` branch to your CEO alerting channel (Slack, Telegram, or CRM task).
4. Wire the `UNSUBSCRIBE` branch to your global suppression list.

---

## 5. Provenance & License
- **Source Repository**: `https://github.com/Sufiyan367/agency-os` (`app/crm/reply_classifier.py`)
- **Source License**: `PROPRIETARY_AGENCY_OS`
- **Commercialization Status**: `COMMERCIAL_READY`
- **Reference Inspirations**: `Zie619/n8n-workflows` (`email-classifier`), `enescingoz/awesome-n8n-templates` (`email-triage.json`).
