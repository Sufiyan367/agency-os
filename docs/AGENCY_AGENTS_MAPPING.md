# Agency Agents Mapping: Local-First AI Lead Recovery & Outreach

This document details how reference architectures, agent roles, and prompt methodologies from the [`agency-agents`](https://github.com/msitarzewski/agency-agents) repository are conceptually reused, adapted, or intentionally excluded for our local-first B2B lead recovery and outreach automation system.

---

## 1. System Vision & Product Scope

Our core product is a **reliable, production-minded local automation system** built for small US service businesses (e.g., HVAC, plumbing, dental, legal, auto repair). 

The target workflow:
```
Business Discovery / Input
   ↓
Business Data Ingestion (Context, Services, Pricing, Rules)
   ↓
Website & Technical Audit (Performance, SEO, A11y, Mobile, Security)
   ↓
AI Qualification & Scoring (HOT / WARM / COLD / INVALID)
   ↓
Personalized Outreach Message Generation (Evidence-Based Icebreakers)
   ↓
Follow-Up Scheduling & Time-Compressed Engine
   ↓
Owner Notification & Human Takeover Safeguards
   ↓
Lead Status Tracking & Complete Event Audit Trail
```

To guarantee reliability, we enforce **strict separation of concerns**:
- **Deterministic Business Rules Override AI Guesses**: AI never invents pricing, services, guarantees, or working hours.
- **Provider Abstraction**: System depends on `BaseAIProvider` and `BaseMessageProvider` with zero vendor lock-in and a zero-cost local `MockProvider`.
- **Audit Trails**: Every qualification, outreach draft, message status, follow-up transition, and human takeover event is persistently logged.

---

## 2. Agent Mapping & Adaptation Table

Out of the 80+ agents in `agency-agents`, only 4 core specialized capabilities are required for this MVP. All bloat (enterprise SDR hierarchies, webscraping crawlers, social media publishers) is omitted.

| Source Agent in `agency-agents` | Adapted MVP Component | Conceptual Reusable Elements | System Adaptation & Customization |
| :--- | :--- | :--- | :--- |
| **`sales/sales-outbound-strategist`** | `LeadQualificationAgent` (`app/agents/qualifier.py`) | • Signal-based qualification hierarchy (Tier 1 direct intent, Tier 2 operational need, Tier 3 technographic).<br>• Speed-to-signal urgency.<br>• Rejection of generic "spray-and-pray" outreach in favor of evidence-backed relevance. | • Transformed from a conversational prompt into a **structured Pydantic evaluator** returning `lead_score` (0-100), `qualification` (`HOT`/`WARM`/`COLD`/`INVALID`), `pain_points`, `recommended_service`, and `reasoning`.<br>• Calibrated specifically for local SMB diagnostic signals (e.g. broken mobile viewport, missing SSL, failing speed score). |
| **`sales/sales-offer-lead-gen-strategist`** | `OfferStrategist` (`app/agents/offer.py`) | • Value Equation: $\frac{\text{Dream Outcome} \times \text{Perceived Likelihood}}{\text{Time Delay} \times \text{Effort \& Sacrifice}}$.<br>• Diagnostic Lead Magnet principle: give a standalone valuable diagnostic before pitching. | • Constrained to deterministic business pricing tables ($450–$1,200).<br>• Directly maps detected technical audit weaknesses (e.g., poor mobile LCP, zero schema markup) to concrete remediation packages. |
| **`marketing/marketing-email-strategist`** | `PersonalizedOutreachWriter` (`app/agents/outreach.py`) | • High-converting cold outreach structure (Observation $\rightarrow$ Problem $\rightarrow$ Evidence $\rightarrow$ Low-friction CTA).<br>• Strict avoidance of corporate jargon and spam triggers.<br>• Multi-step follow-up cadence design. | • Injects **System Rules + Business Context + Lead Audit Findings** in an isolated prompt envelope to prevent prompt injection.<br>• Generates plain-text, high-deliverability copy with booking CTAs.<br>• Integrated into a configurable follow-up sequence with auto-stop on reply or opt-out. |
| **`support/support-support-responder`** & **`support/support-analytics-reporter`** | `EscalationNotifier` & `LeadLifecycleTracker` (`app/agents/escalation.py`) | • Intent and sentiment classification on inbound replies.<br>• Rapid escalation triggers for human intervention.<br>• Lifecycle event accounting and funnel tracking. | • Dispatches instant local mock/console notifications to the business owner when a lead is `HOT`, requests a human, or books.<br>• Manages the **Human Takeover / Pause Automation** switch that immediately freezes all automated outbound actions. |

---

## 3. Explicitly Excluded Components from `agency-agents`

To avoid over-engineering and dependency overhead, the following categories were reviewed and intentionally excluded:

1. **Enterprise SDR & Pipeline Hierarchies (`sales-coach`, `sales-pipeline-analyst`, `sales-deal-strategist`)**:
   - *Reason*: Overkill for a local small-business lead recovery tool. SMB owners need automated booking and recovery, not multi-tier enterprise pipeline analytics.
2. **Social Media & Content Engines (`marketing-douyin`, `marketing-twitter`, `marketing-bilibili`)**:
   - *Reason*: Irrelevant to direct B2B cold outreach and inbound lead recovery.
3. **Complex Multi-Agent Orchestration Frameworks (e.g., CrewAI, AutoGen, LangGraph heavy graphs)**:
   - *Reason*: Add non-deterministic failure modes, latency, and dependency bloat. We use a deterministic, modular Python pipeline with simple async orchestration.
4. **Third-Party Paid APIs & Webhooks in MVP**:
   - *Reason*: Local development must run 100% free of charge via `MockAIProvider` and `MockMessageProvider`.

---

## 4. Architectural Boundaries

```
┌────────────────────────────────────────────────────────┐
│                   FASTAPI APPLICATION                  │
├──────────────────────────┬─────────────────────────────┤
│      API & DASHBOARD     │     PERSISTENT WORKER       │
│  • Leads & Audit Views   │  • Lead Qualification Queue │
│  • Outreach Approval     │  • Follow-Up Scheduler      │
│  • Human Takeover Switch │  • Auto-Stop Detector       │
└────────────┬─────────────┴──────────────┬──────────────┘
             │                            │
             ▼                            ▼
┌────────────────────────────────────────────────────────┐
│                 MODULAR SERVICE LAYER                  │
│  • LeadService             • AuditService              │
│  • QualificationService    • OutreachService           │
│  • FollowUpEngine          • NotificationService       │
└────────────┬────────────────────────────┬──────────────┘
             │                            │
             ▼                            ▼
┌──────────────────────────┐ ┌───────────────────────────┐
│     AI ABSTRACTION       │ │   MESSAGING ABSTRACTION   │
│  • BaseAIProvider        │ │  • BaseMessageProvider    │
│  • MockAIProvider (Free) │ │  • MockMessageProvider    │
│  • GeminiProvider (Opt)  │ │  • (Future: Twilio/Email) │
└────────────┬─────────────┘ └────────────┬──────────────┘
             │                            │
             └─────────────┬──────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│             POSTGRESQL / SQLITE STORAGE                │
│  • businesses              • leads                     │
│  • audits                  • outreach_messages         │
│  • followups               • lead_events               │
└────────────────────────────────────────────────────────┘
```

---

## 5. Summary of Phase 1 Decisions

1. **Local-First & Zero-Cost**: The system runs entirely locally on Python 3.11 with SQLite / local PostgreSQL. Mock mode is the default so testing incurs zero API fees.
2. **Safety & Compliance**: Email/SMS sending remains strictly mocked (`EMAIL_DRY_RUN=true`). Mandatory human sign-off on first contact is preserved.
3. **Modular Extensibility**: Swapping `MockAIProvider` for `GeminiProvider`, or `MockMessageProvider` for real providers in the future requires changing only the configured provider class, leaving all business and qualification logic untouched.
