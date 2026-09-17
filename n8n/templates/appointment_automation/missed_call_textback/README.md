# AGY-AUTO-MissedCallTextBack-SafetyFloor-v1.0

## 1. What It Does
Instant automated SMS text-back to missed inbound customer calls with caller identification, business hours vs after-hours detection, strict suppression/opt-out checking, and CRM interaction logging. Prevents lead leakage by engaging callers in under 30 seconds.

## 2. Who It Is For
Commercial service businesses (HVAC, Dental, Roofing, Legal, Real Estate, Home Services, Professional Services) that receive inbound telephone inquiries and need 24/7 lead capture.

## 3. Use Cases
- Immediate text-back to callers when staff are on other calls during peak hours.
- Automated after-hours emergency or next-day booking links dispatched to evening callers.
- Hard-stop suppression preventing messages to numbers that have previously opted out.
- CRM activity logging for every missed inbound attempt.

## 4. Required n8n Setup
- **Minimum n8n Version**: `1.0.0` or higher
- **Node Runtime**: Node.js 18+ or standard n8n container
- **Execution Mode**: Production webhook listener with synchronous or asynchronous response

## 5. Required Credentials
Zero hardcoded secrets. All integrations utilize environment variables and isolated credential managers:
- `n8n-nodes-base.webhook`
- `n8n-nodes-base.code`
- `n8n-nodes-base.if`
- `n8n-nodes-base.respondToWebhook`

## 6. Inputs
- `caller_phone` (string, required): Phone number of incoming caller (e.g. `+15550192834`).
- `caller_name` (string, optional): Resolved contact name if caller is known in CRM.
- `is_after_hours` (boolean, optional): Flag indicating whether call was received outside business hours.
- `suppressed` (boolean, optional): Pre-checked suppression or opt-out status flag.
- `call_duration_seconds` (number, optional): Duration of the missed/abandoned ring.

## 7. Outputs
- `status` (string): `PROCESSED` or `SUPPRESSED`.
- `caller_phone` (string): Caller phone number.
- `textback_dispatched` (boolean): `true` if approved text-back message was queued/dispatched.
- `suppression_blocked` (boolean): `true` if contact was suppressed or opted out.
- `delivery_status` (string): `DISPATCHED_TO_GATEWAY` or error indicator.
- `message_preview` (string): Approved SMS body dispatched.
- `crm_logged` (boolean): Interaction persistence confirmation.

## 8. Installation
1. Open your n8n workspace console.
2. Select **Workflows** -> **Import from File...**
3. Select `workflow.json` from this package.
4. Save and activate the workflow.

## 9. Configuration
Configure required environment parameters in your n8n runtime:
- `AGENCY_WEBHOOK_URL`: Base URL for Agency OS scheduling and webhook callbacks.
- `AGENCY_NOTIFICATION_EMAIL`: Operator notification address for delivery exceptions.

## 10. Expected Behavior
Upon receiving an inbound missed call POST event, the workflow verifies suppression and opt-out lists. If clean, it selects the business-hours or after-hours copy, formats the message, logs the event, and responds synchronously with structured JSON telemetry.

## 11. Error Handling
- Callers without phone numbers or marked as opted out are routed to the suppression block branch (`textback_dispatched: false`).
- Malformed inputs fallback safely to baseline defaults without stopping the workflow engine.

## 12. License & Source Attribution
- **License**: MIT
- **Provenance**: Agency OS Core (`app/automations/missed_call_service.py`)
- **Status**: Verified commercially ready for client deployment.

## 13. Modification Notes
- Packaged under Agency OS Automation Governance.
- Zero hardcoded API keys or client-specific numbers.
- Fully parameter-driven for any industry niche.
