# AGY-SCORE-LeadQualification-CommercialFloor-v1.0

## 1. What It Does
Commercial feasibility scoring enforcing strict $500 project value floor, ICP alignment metrics, commercial priority tagging (HIGH/MEDIUM/LOW), and automated lead routing. Prevents sales teams from pursuing unviable prospects below delivery margins.

## 2. Who It Is For
Agency operators, B2B sales teams, and commercial operations automating lead qualification workflows.

## 3. Use Cases
- Strict $500 budget floor enforcement on all inbound and outbound deals.
- Instant 0-100 feasibility scoring based on deal size, team headcount, and web deficit.
- Automated pipeline routing (HIGH priority to instant scheduling, LOW to archive).

## 4. Required n8n Setup
- **Minimum n8n Version**: `1.0.0` or higher
- **Node Runtime**: Node.js 18+ or n8n cloud instance
- **Execution Mode**: Production webhook listener or asynchronous queue

## 5. Required Credentials
Zero hardcoded credentials. All integrations utilize isolated n8n credential managers:
- `n8n-nodes-base.webhook`
- `n8n-nodes-base.code`
- `n8n-nodes-base.switch`
- `n8n-nodes-base.respondToWebhook`

## 6. Inputs
- `deal_value` (number): Estimated deal value in USD (e.g. 750.0).
- `traffic_score` (number): Preliminary prospect traffic score (0-100).
- `industry` (string): Business industry classification.

## 7. Outputs
- `floor_passed` (boolean): Whether deal meets or exceeds the $500 floor.
- `commercial_priority` (string): HIGH_PRIORITY, MEDIUM_PRIORITY, or BLOCKED_BELOW_FLOOR.
- `feasibility_score` (number): 0-100 calculated commercial feasibility rating.
- `requires_human_review` (boolean): Flag indicating if manual CEO review is required.

## 8. Installation
1. Open your n8n workspace console.
2. Select **Workflows** -> **Import from File...**
3. Upload `workflow.json` from this package.
4. Set execution active.

## 9. Configuration
Configure required environment parameters:
- `AGENCY_WEBHOOK_URL`: Base URL for Agency OS callbacks.
- `COMMERCIAL_FLOOR_USD`: Minimum acceptable contract value (default: $500.0).

## 10. Expected Behavior
Upon receiving a POST webhook payload, the workflow computes commercial feasibility, enforces the $500 floor, assigns priority tiers, and synchronously responds with structured routing directives.

## 11. Error Handling
- Invalid JSON payloads automatically trigger defensive validation branches.
- Missing values default to safe baseline estimates to prevent workflow halts.

## 12. License & Source Attribution
- **License**: MIT
- **Provenance**: Agency OS Core Engine (`app/scoring/commercial_scoring.py`)
- **Status**: Verified commercially distributable under permissive open-source license.

## 13. Modification Notes
- Standardized for Agency OS commercial engine deployment.
- All secrets, tokens, and hardcoded addresses removed and replaced with environmental variables.
