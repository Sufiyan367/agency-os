# AGY-SUPPORT-TicketTriage-AutoResponder-v1.0

## Description
Autonomous triage engine that classifies customer support requests, tags severity levels, and escalates high-priority incidents to the operator.

## Architecture
1. **Webhook Trigger**: Ingests support inquiries (`POST /webhook/support-inbound-ticket`).
2. **Evaluate & Triage Ticket**: Categorizes incident urgency and determines operator escalation routing.
3. **Respond to Webhook**: Returns triage telemetry.

## Configuration
- `AGENCY_SUPPORT_WEBHOOK_SECRET`: Webhook verification secret.
