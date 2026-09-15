# AGY-ONBOARD-ClientWelcome-SetupJourney-v1.0

## Description
Automates initial client intake, customer workspace initialization, setup checklist provisioning, and welcoming communication.

## Provenance & Attribution
Adapted from `awesome-n8n-templates` under **CC-BY-4.0** license.
Author: Enes Cingoz (https://github.com/enescingoz).

## Architecture
1. **Webhook Trigger**: Receives new client sign-off (`POST /webhook/client-onboard-init`).
2. **Create Onboarding Bundle**: Generates client credentials, configuration tasks, and portal links.
3. **Respond to Webhook**: Returns setup progress.

## Configuration
- `AGENCY_ONBOARDING_TOKEN`: Secret token for onboarding verification.
- `AGENCY_PORTAL_DOMAIN`: Domain where client portal is hosted.
