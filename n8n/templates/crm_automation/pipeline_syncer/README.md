# AGY-CRM-PipelineSyncer-AuditLog-v1.0

## Description
Synchronizes Agency OS 10-stage lifecycle transitions to external client CRM records (HubSpot, Salesforce, Pipedrive) with immutable audit events.

## Architecture
1. **Webhook Trigger**: Receives structured lifecycle transitions (`POST /webhook/crm-sync-event`).
2. **Normalize CRM Event**: Formats company names, validates IDs, and calculates normalized values.
3. **Respond to Webhook**: Returns sync confirmation and audit timestamp.

## Configuration
- `AGENCY_CRM_API_KEY`: API Key for external CRM instance.
- `AGENCY_WEBHOOK_SECRET`: HMAC authentication secret.
