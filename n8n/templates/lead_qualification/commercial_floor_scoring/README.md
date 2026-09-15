# AGY-SCORE-LeadQualification-CommercialFloor-v1.0

## 1. Overview & Business Use Case
Agency efficiency collapses when sales teams spend time pursuing deals below operational delivery margins. This workflow enforces an automated commercial qualification policy:
- **Strict $500 Commercial Floor**: Immediately disqualifies prospects with budget expectations below $500.
- **ICP Fit Scoring (0-100)**: Evaluates diagnostic health deficit, team size capacity, and deal value potential.
- **Automated Routing & Priority Tagging**:
  - `HIGH` (Score >= 80): Immediate priority outreach queue.
  - `MEDIUM` (Score 60-79): Standard batch outreach cadence.
  - `LOW` / `REJECTED`: Nurture or auto-archive without wasting sales capacity.

Derived directly from the Agency OS Commercial Scoring Engine (`app/scoring/commercial_scoring.py`).

---

## 2. Input Specification
- **Trigger**: HTTP Webhook (POST)
- **Endpoint**: `/webhook/qualify-lead`
- **Content-Type**: `application/json`

### Example Payload:
```json
{
  "domain": "acmebrokerage.com",
  "estimated_budget_usd": 1500,
  "team_size": 12,
  "overall_health_score": 55
}
```

---

## 3. Output Specification
- **Response**: Synchronous JSON (`application/json`)
- **Status Codes**:
  - `200 OK`: Lead scored and routing decision generated.

### Example Qualified Output:
```json
{
  "status": "QUALIFIED",
  "domain": "acmebrokerage.com",
  "qualification_score": 85,
  "priority_tier": "HIGH",
  "estimated_budget_usd": 1500,
  "route": "immediate_outreach",
  "qualified_at": "2026-09-16T00:45:00.000Z"
}
```

### Example Disqualified Output ($500 Floor Violation):
```json
{
  "status": "DISQUALIFIED",
  "reason": "Budget $300 is below the strict $500 commercial floor.",
  "domain": "lowtierlead.com",
  "qualification_score": 0,
  "priority_tier": "REJECTED",
  "route": "archive"
}
```

---

## 4. Setup Instructions
1. Import `workflow.json` into n8n via **Workflows → Import from File**.
2. Customize the `COMMERCIAL_FLOOR_USD` constant inside the Code node if your agency price floor is higher (e.g., $1,000 or $2,500).
3. Connect downstream nodes (e.g. CRM insert, Slack notification, or Outreach sequencer) to the corresponding output branches of the **Route by Priority Tier** switch node.

---

## 5. Failure Handling
- Safe default fallbacks apply if `estimated_budget_usd` or `team_size` are omitted.
- Missing values degrade gracefully without throwing uncaught exceptions.

---

## 6. Provenance & License
- **Source Repository**: `https://github.com/Sufiyan367/agency-os` (`app/scoring/commercial_scoring.py`)
- **Source License**: `PROPRIETARY_AGENCY_OS`
- **Commercialization Status**: `COMMERCIAL_READY`
- **Reference Inspirations**: `enescingoz/awesome-n8n-templates` (`lead-scoring.json`).
