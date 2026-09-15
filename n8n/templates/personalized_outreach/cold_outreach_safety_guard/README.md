# AGY-OUTREACH-PersonalizedDrafter-SafetyGuard-v1.0

## 1. Overview & Business Use Case
Generic mass-blast outreach burns domain reputation and generates zero pipeline. This workflow automates high-conversion, personalized B2B outreach while enforcing strict safety gates:
- **Evidence-Grounded Personalization**: Directly incorporates specific audit findings (e.g. missing mobile optimization, absent conversion CTAs) into the opening observation.
- **Strict Compliance Verification**: Verifies presence of a valid opt-out mechanism (`unsubscribe`) and physical commercial postal address before approving the draft.
- **Safety / Approval Gating**: Outputs `approval_state: "AWAITING_CEO_APPROVAL"` and `can_send_live: false` by default, preventing unvetted automated email blasts.

Derived directly from the Agency OS Outreach Generator (`app/outreach/generator.py`).

---

## 2. Input Specification
- **Trigger**: HTTP Webhook (POST)
- **Endpoint**: `/webhook/draft-outreach`
- **Content-Type**: `application/json`

### Example Payload:
```json
{
  "domain": "peakpropertygroup.com",
  "business_name": "Peak Property Group",
  "contact_email": "hello@peakpropertygroup.com",
  "audit_findings": ["No direct contact CTA (phone/email) detected on homepage."],
  "offered_service": "AI Receptionist + Missed-Call Recovery System"
}
```

---

## 3. Output Specification
- **Response**: Synchronous JSON (`application/json`)
- **Status Codes**:
  - `200 OK`: Outreach draft synthesized with compliance audit.

### Example Success Output:
```json
{
  "status": "DRAFT_READY",
  "domain": "peakpropertygroup.com",
  "recipient_email": "hello@peakpropertygroup.com",
  "subject": "Quick observation regarding Peak Property Group",
  "body_text": "Hi Peak Property Group Team,\n\nWhile reviewing peakpropertygroup.com today, I noted that no direct contact cta (phone/email) detected on homepage..\n\nWe help commercial firms install an AI Receptionist + Missed-Call Recovery System that resolves these issues and recaptures lost prospect inquiries automatically.\n\nWould you be open to a brief 10-minute discovery call this Thursday to explore if this fits your current priorities?\n\nBest regards,\nAgency OS Client Solutions Team\n\n---\nAgency OS Services, 100 Congress Ave, Suite 2000, Austin, TX 78701, USA\nTo opt out, reply with 'unsubscribe'.",
  "compliance": {
    "can_spam_compliant": true,
    "has_unsubscribe": true,
    "has_physical_address": true
  },
  "approval_state": "AWAITING_CEO_APPROVAL",
  "can_send_live": false,
  "drafted_at": "2026-09-16T00:45:00.000Z"
}
```

---

## 4. Setup Instructions
1. Import `workflow.json` into n8n via **Workflows → Import from File**.
2. Configure your organization's physical postal address in the Code node parameters.
3. Connect downstream nodes (e.g. approval dashboard webhook, Slack approval notification, or CRM draft queue).

---

## 5. Provenance & License
- **Source Repository**: `https://github.com/Sufiyan367/agency-os` (`app/outreach/generator.py`)
- **Source License**: `PROPRIETARY_AGENCY_OS`
- **Commercialization Status**: `COMMERCIAL_READY`
- **Reference Inspirations**: `enescingoz/awesome-n8n-templates` (`personalized-email-generation.json`).
