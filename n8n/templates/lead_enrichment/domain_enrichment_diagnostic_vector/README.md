# AGY-AUDIT-DomainEnrichment-DiagnosticVector-v1.0

## 1. Overview & Business Use Case
This production-grade workflow ingests a prospect's domain or website URL, crawls the homepage, and executes an automated 6-vector diagnostic audit:
1. **Security Vector**: SSL/HTTPS verification and transport security.
2. **SEO & Discoverability Vector**: HTML title tag, meta descriptions, and header structure.
3. **Mobile Responsiveness Vector**: Viewport configuration and mobile scaling indicators.
4. **Technology Stack Vector**: Detection of platforms (WordPress, Shopify, Next.js/React, Google Analytics).
5. **Conversion Architecture Vector**: Detection of direct contact CTAs (tel links, mailto links, phone regex).
6. **Overall Health Score**: Normalized 0-100 composite score with actionable findings for cold outreach personalization.

Derived directly from the verified Agency OS core audit pipeline (`app/audit/audit_service.py`).

---

## 2. Input Specification
- **Trigger**: HTTP Webhook (POST)
- **Endpoint**: `/webhook/audit-domain`
- **Content-Type**: `application/json`

### Example Payload:
```json
{
  "domain": "example.com",
  "business_name": "Example Real Estate"
}
```

---

## 3. Output Specification
- **Response**: Synchronous JSON (`application/json`)
- **Status Codes**:
  - `200 OK`: Audit executed successfully or structured unreachable fallback returned.
  - `400 Bad Request`: Missing `domain` parameter.

### Example Success Output:
```json
{
  "status": "SUCCESS",
  "domain": "example.com",
  "overall_health_score": 82,
  "audit_vectors": {
    "security": { "score": 90, "findings": ["SSL/TLS active."] },
    "seo": { "score": 75, "findings": ["Missing meta description tag."] },
    "mobile": { "score": 80, "findings": [] },
    "tech_stack": { "score": 90, "detected": ["WordPress", "Google Analytics"] },
    "conversion": { "score": 70, "findings": ["No direct contact CTA (phone/email) detected on homepage."] }
  },
  "audited_at": "2026-09-16T00:45:00.000Z"
}
```

---

## 4. Setup Instructions
1. Import `workflow.json` into your n8n workspace via **Workflows → Import from File**.
2. No third-party API credentials required (uses standard built-in HTTP Request and Code nodes).
3. Activate the workflow to enable the production webhook URL.
4. Point your lead discovery pipeline or CRM webhook to the generated n8n URL.

---

## 5. Failure Handling & Circuit Breaking
- **Domain Timeout**: The HTTP fetch node enforces a 12,000ms hard timeout.
- **Unreachable / 4xx / 5xx Sites**: If the target server refuses connection or throws an HTTP error, execution routes automatically to the `Fallback / Unreachable Handler` node.
- **Graceful Degradation**: Rather than failing the entire orchestration, a structured fallback payload (`status: "UNREACHABLE"`, `overall_health_score: 40`) is returned with explicit connectivity error details.

---

## 6. Provenance & License
- **Source Repository**: `https://github.com/Sufiyan367/agency-os` (`app/audit/audit_service.py`)
- **Source License**: `PROPRIETARY_AGENCY_OS`
- **Commercialization Status**: `COMMERCIAL_READY`
- **Reference Inspirations**: `nusquama/n8nworkflows.xyz` (Workflow #3535), `Zie619/n8n-workflows` (website-auditor).
