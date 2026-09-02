# Autonomous B2B Lead-Gen & Sales Agency

An enterprise-grade autonomous revenue engine engineered to discover high-yield market opportunities across global countries and niches, extract and verify qualified B2B prospects, perform deep non-destructive website audits (performance, SEO, accessibility, UX/conversion, security, content), score leads transparently, recommend targeted high-margin service packages (\$450–\$1,500+), draft evidence-grounded personalized outreach sequences into an approval queue, track follow-ups and reply sentiment, maintain a CRM pipeline, and orchestrate delivery automation.

---

## Architecture Overview

```
app/
├── core/                   # Configuration, structured logging, SSRF guards, unified LLM client
│   ├── config.py           # Pydantic Settings, thresholds, rate limits, scoring weights
│   ├── logging.py          # Structured logging with run_id correlation & secret masking
│   ├── security.py         # SSRF protection, URL sanitizer, email validator
│   └── llm.py              # Multi-provider LLM adapter (NVIDIA, OpenAI, OpenRouter, Heuristics)
├── database/               # Relational persistence layer
│   ├── connection.py       # SQLAlchemy 2.0 Async engine (SQLite / PostgreSQL)
│   ├── models.py           # Relational schema (22 core entities)
│   └── seed_data.py        # Macroeconomic benchmarks & niche catalog
├── market_intelligence/    # Global opportunity scoring engine
│   ├── engine.py           # Multi-factor formula scoring country + niche combinations
│   └── models.py           # Evaluation models & comparative synthesis
├── lead_generation/        # Prospect discovery & verification
│   ├── adapters/           # Seed verified dataset, Web search, Directory index
│   ├── discovery.py        # Deduplication, domain normalization, discovery coordinator
│   └── verification.py     # DNS, HTTP reachability, and email consistency checks
├── auditing/               # Multi-vector website audit engine
│   ├── crawler.py          # Resilient fetcher with SSRF defense & timing
│   ├── performance.py      # TTFB, mobile viewport, render-blocking scripts, image formats
│   ├── seo.py              # Meta title/desc, H1 hierarchy, canonical, Schema JSON-LD
│   ├── accessibility.py    # WCAG 2.1 AA heuristics, image alt tags, form labels, buttons
│   ├── ux_conversion.py    # CTA hero visibility, click-to-call, lead forms, trust proof
│   ├── security.py         # HTTPS enforcement, HSTS, X-Frame-Options, tech fingerprint
│   ├── content.py          # Word count, thin content flags, service/location architecture
│   └── engine.py           # Master aggregator generating severity-badged findings
├── scoring/                # Transparent 0-100 commercial scoring
│   └── engine.py           # Deficit breakdown, ability to pay, contactability, Priority A-LOW
├── offers/                 # Problem-to-service mapping & commercial pricing
│   └── generator.py        # Custom packages ($450 - $1,500+) with itemized deliverables
├── outreach/               # Hyper-personalized outreach & approval gate
│   ├── personalization.py  # 3 distinct evidence-grounded message variants
│   ├── queue.py            # Approval queue (APPROVE, REJECT, EDIT, HOLD)
│   ├── sender.py           # DRY_RUN simulation adapter & live SMTP transmitter
│   └── compliance.py       # Suppression list, daily caps, opt-out footers
├── followups/              # Multi-step cadence engine
│   └── engine.py           # Day 3, 7, 14 scheduler with auto-cancellation upon reply
├── crm/                    # CRM pipeline & reply intelligence
│   ├── pipeline.py         # Stage state machine (DISCOVERED -> WON/LOST), deal values
│   └── reply_classifier.py # AI reply intent classifier (INTERESTED, MEETING, UNSUB)
├── analytics/              # Executive reporting & learning loop
│   ├── engine.py           # Real-time KPIs, conversion funnels, revenue breakdown
│   └── feedback_loop.py    # Historical performance optimizer
├── delivery/               # Post-sale delivery automation
│   ├── onboarding.py       # Client intake packet & kickoff schedule
│   └── report_generator.py # Technical diagnostic audit report in Markdown/HTML
├── orchestrator/           # Central autonomous cycle coordinator
│   └── loop.py             # 18-step idempotent daily revenue loop runner
├── api/                    # REST API & Control Dashboard
│   ├── app.py              # FastAPI application entrypoint
│   └── routes.py           # REST endpoints for leads, queue, pipeline, and reports
├── frontend/               # Web control center
│   ├── static/             # Clean dark-mode stylesheet & dynamic JavaScript client
│   └── templates/          # Jinja2 dashboard template
└── cli.py                  # Unified command-line interface
```

---

## Core Business Principles & Safety Guards

1. **Quality Over Spam**: Does NOT send bulk generic email blasts. Optimizes for high-intent, evidence-backed opportunities.
2. **Human Approval Gate**: Every outbound outreach message is drafted into a `PENDING_APPROVAL` queue. Only explicit human approval (`APPROVE`) triggers dispatch.
3. **Safe by Default (`DRY_RUN=True`)**: Outreach is simulated safely by default. Delivery events are logged without contacting external SMTP mail servers.
4. **Anti-SSRF Protection**: Prevents attacks against loopback (`127.0.0.1`), private networks (`10.0.0.0/8`, `192.168.0.0/16`, `172.16.0.0/12`), link-local metadata services (`169.254.169.254`), or non-HTTP schemes.
5. **Deduplication & Idempotency**: Normalizes root domains and prevents duplicate database records across runs.

---

## Quickstart & Installation

### 1. Requirements
- Python 3.11+
- Virtualenv or system Python

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize Database
```bash
python -m app.cli init
```

### 4. Run End-to-End Acceptance Test
Demonstrates all 11 stages of the autonomous revenue machine:
```bash
python -m app.cli demo-e2e
```

### 5. Launch Web Control Center
```bash
python -m app.cli serve --host 0.0.0.0 --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser to access:
- Executive Revenue Dashboard
- International Market Opportunity Matrix
- Verified Prospect Leads Table & Detail Inspector
- Human Approval Outreach Queue
- CRM Pipeline Kanban Board
- One-Click Autonomous Cycle Runner (`⚡ Run Autonomous Cycle`)

---

## CLI Command Suite

| Command | Purpose |
| :--- | :--- |
| `python -m app.cli init` | Initializes database schema and seeds benchmark data |
| `python -m app.cli discover-markets` | Scans and ranks country + niche combinations |
| `python -m app.cli run-loop` | Executes the full 18-step autonomous cycle end-to-end |
| `python -m app.cli serve` | Runs the FastAPI control dashboard server |
| `python -m app.cli demo-e2e` | Runs comprehensive 11-step end-to-end acceptance demo |

---

## Running Automated Tests

Run the full automated pytest suite (17 passed tests covering security, auditing, deduplication, scoring, offers, outreach queue, and CRM replies):
```bash
pytest -v
```

---

## Database Schema (22 Relational Entities)

- `countries`: Macroeconomic data, GDP/capita, business density, regulatory risk.
- `niches`: Commercial sectors, average deal size, digital weakness index.
- `market_opportunities`: Multi-factor evaluated country + niche opportunities.
- `businesses`: Discovered and verified prospect companies.
- `contacts`: Public business email, phone, and title information.
- `audit_runs`: Performance, SEO, A11y, UX, Security, Content scores.
- `audit_findings`: Specific diagnostic findings with severity, evidence, fix, and impact.
- `lead_scores`: 0-100 commercial opportunity score, Priority A-LOW, and rationale.
- `offers`: Tailored service recommendations ($450-$1,500+) and deliverables.
- `outreach_messages`: Human-approval queue holding personalized outreach drafts.
- `outreach_events`: Audit trail of simulated and live email transmissions.
- `followup_sequences`: Day 3, 7, 14 follow-up cadence records.
- `replies`: Incoming email replies classified by AI with sentiment/intent.
- `pipeline_events`: Complete audit trail of stage transitions.
- `customers`: Won client accounts converted upon contract closure.
- `projects`: Delivery automation projects with task checklists and QA reviews.
- `payments`: Confirmed invoices and revenue receipts.
- `suppression_list`: Permanent opt-out / unsubscribe and bounce registry.
- `system_runs`: Observability logs tracking duration, job status, and processed records.
- `agent_tasks`: Internal background orchestration tasks.
