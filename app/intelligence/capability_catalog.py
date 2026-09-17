"""
Agency OS — Solution Capability Catalog.
Defines canonical software & automation capabilities offered by the agency,
including problem, trigger, inputs, logic, integrations, actions, human/CEO gates,
measurable outcomes, n8n workflows, demo patterns, and production implementation paths.
All capabilities are cross-industry (HVAC, Dental, Roofing, Real Estate, Home Services, Professional Services, etc.)
with zero company-specific hardcoding.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class SolutionCapability(BaseModel):
    """
    Structured definition of a commercial agency capability.
    """
    capability_id: str
    name: str
    category: str
    description: str
    problem: str = ""
    trigger: str = ""
    inputs: List[str] = Field(default_factory=list)
    logic: str = ""
    integrations: List[str] = Field(default_factory=list)
    actions: List[str] = Field(default_factory=list)
    human_ceo_gates: str = ""
    measurable_outcome: str = ""
    requirements: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    cost_profile_usd: float = 25.0
    target_price_usd: float = 1000.0
    setup_fee_usd: float = 750.0
    monthly_management_usd: float = 250.0
    complexity_level: str = "MODERATE"  # LOW, MODERATE, HIGH, ENTERPRISE
    risk_level: str = "LOW"             # LOW, MEDIUM, HIGH
    compatible_n8n_templates: List[str] = Field(default_factory=list)
    n8n_implementation_status: str = "N8N_WORKFLOW_AVAILABLE"  # AVAILABLE, N8N_WORKFLOW_REQUIRED
    demo_blueprint_type: str = "booking_flow"
    production_implementation_path: str = "DEMO -> PROPOSAL -> ADVANCE PAYMENT VERIFIED -> PRODUCTION BUILD"
    expected_outcomes: List[str] = Field(default_factory=list)
    supported_industries: List[str] = Field(
        default_factory=lambda: [
            "HVAC",
            "Dental",
            "Roofing",
            "Real Estate",
            "Home Services",
            "Professional Services",
            "Legal",
            "Healthcare"
        ]
    )


CAPABILITY_REGISTRY: List[SolutionCapability] = [
    # -------------------------------------------------------------
    # CAP-001 - CAP-006: Core Agency OS Capabilities (Preserved)
    # -------------------------------------------------------------
    SolutionCapability(
        capability_id="CAP-001-LEAD-CAPTURE",
        name="High-Conversion Intake & Qualification Flow",
        category="Lead Response",
        description="Frictionless multi-step inquiry intake with instant qualification scoring, lead routing, and immediate notification.",
        problem="Inbound website visitors bounce due to clunky forms and delayed sales team follow-up.",
        trigger="Web inquiry form submission or chat widget event.",
        inputs=["prospect_name", "email", "phone", "service_needed", "urgency", "source_url"],
        logic="Validate inputs -> compute commercial qualification score -> route high priority leads instantly -> trigger notification.",
        integrations=["Website Forms", "SMS Gateway (Twilio)", "CRM Webhook", "Internal Team Slack/Email"],
        actions=["Record prospect", "Send instant receipt SMS", "Dispatch operator priority alert"],
        human_ceo_gates="Low-scoring inquiries route to async review; high-intent leads trigger immediate operator notification.",
        measurable_outcome="Reduce lead intake latency to < 60 seconds; improve qualified conversion by 25-35%.",
        requirements=["Web intake form or chat embed", "Notification webhook/SMS", "Qualification rubric"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.code", "n8n-nodes-base.httpRequest"],
        cost_profile_usd=15.0,
        target_price_usd=850.0,
        setup_fee_usd=750.0,
        monthly_management_usd=200.0,
        complexity_level="LOW",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-SCORE-LeadQualification-CommercialFloor-v1.0"],
        demo_blueprint_type="intake_portal",
        expected_outcomes=["Reduce response latency to < 60 seconds", "Filter unqualified inquiries before manual rep review"]
    ),
    SolutionCapability(
        capability_id="CAP-002-BOOKING-AUTOMATION",
        name="24/7 Self-Serve Appointment & Dispatch Engine",
        category="Appointment Scheduling",
        description="Interactive scheduling stepper with live calendar synchronization, timezone handling, and automated reminders.",
        problem="Back-and-forth email and phone scheduling causes dropped consultations and slow booking.",
        trigger="Customer selects scheduling link or requests meeting time.",
        inputs=["customer_id", "preferred_times", "service_type", "staff_calendar_id", "timezone"],
        logic="Query live calendar openings -> validate conflicts -> hold temporary slot -> confirm booking on selection.",
        integrations=["Google Calendar / Outlook", "Cal.com / Calendly API", "Twilio SMS"],
        actions=["Create calendar event", "Send confirmation email/SMS with ICS invite", "Update CRM contact stage"],
        human_ceo_gates="Overbooking or VIP client requests flag account manager.",
        measurable_outcome="Zero scheduling latency; eliminates 100% of calendar phone-tag.",
        requirements=["Calendar integration (Google/Outlook/Cal)", "Time-slot validation", "Cancellation/rescheduling link generation"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.dateTime", "n8n-nodes-base.httpRequest"],
        cost_profile_usd=20.0,
        target_price_usd=1200.0,
        setup_fee_usd=1000.0,
        monthly_management_usd=250.0,
        complexity_level="MODERATE",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-CRM-InboundReply-IntentClassifier-v1.0"],
        demo_blueprint_type="booking_flow",
        expected_outcomes=["Eliminate phone-tag scheduling delays", "Capture after-hours high-intent bookings"]
    ),
    SolutionCapability(
        capability_id="CAP-003-PRICING-ESTIMATOR",
        name="Instant Cost & Project Estimator Widget",
        category="Website Conversion",
        description="Dynamic client-facing pricing calculator estimating project tiers in real-time, capturing contact details before estimate delivery.",
        problem="Prospective buyers leave website without inquiring because pricing is opaque.",
        trigger="User adjusts parameters on dynamic calculator.",
        inputs=["dimensions/scope_metrics", "material_tier", "zip_code", "contact_email", "contact_phone"],
        logic="Compute estimate range using formula matrix -> gate final breakdown behind email capture -> deliver itemized PDF.",
        integrations=["Frontend Calculator", "PDF Generation Service", "CRM Ingest", "Email Provider"],
        actions=["Render real-time range", "Generate branded estimate summary", "Log lead in pipeline"],
        human_ceo_gates="Estimates above $10,000 automatically flag senior sales estimator.",
        measurable_outcome="2-3x website conversion increase; pre-qualifies budget expectations.",
        requirements=["Pricing matrix / formula parameters", "Gated result email delivery", "PDF estimate generator"],
        dependencies=["n8n-nodes-base.code", "n8n-nodes-base.respondToWebhook"],
        cost_profile_usd=10.0,
        target_price_usd=1000.0,
        setup_fee_usd=850.0,
        monthly_management_usd=150.0,
        complexity_level="LOW",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-AUDIT-DomainEnrichment-DiagnosticVector-v1.0"],
        demo_blueprint_type="calculator",
        expected_outcomes=["Increase website visitor-to-lead conversion by 2-3x", "Anchor buyer price expectations early"]
    ),
    SolutionCapability(
        capability_id="CAP-004-CRM-PIPELINE-SYNC",
        name="Bi-Directional CRM & Pipeline Data Synchronizer",
        category="CRM/Data Entry",
        description="Deterministic webhook and event-driven synchronization between website forms, email replies, and CRM records.",
        problem="Customer and deal records fragmented across disparate systems requiring manual copy-pasting.",
        trigger="CRM record change or external intake webhook.",
        inputs=["source_system", "entity_type", "entity_id", "field_changes", "timestamp"],
        logic="Map normalized schema -> deduplicate entities -> idempotently update target system -> record audit log.",
        integrations=["HubSpot / Salesforce / Pipedrive", "PostgreSQL / SQLite", "Webhook Listener"],
        actions=["Sync contact/deal state", "Log audit change trace", "Alert on field schema discrepancy"],
        human_ceo_gates="Sync conflicts or duplicate company merges require operator approval.",
        measurable_outcome="Zero manual data entry; 100% pipeline visibility.",
        requirements=["CRM API access (HubSpot, Pipedrive, or Custom)", "Event deduplication", "Error queue with retries"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.httpRequest", "n8n-nodes-base.splitInBatches"],
        cost_profile_usd=30.0,
        target_price_usd=1500.0,
        setup_fee_usd=1200.0,
        monthly_management_usd=300.0,
        complexity_level="HIGH",
        risk_level="MEDIUM",
        compatible_n8n_templates=["AGY-CRM-PipelineSyncer-AuditLog-v1.0"],
        demo_blueprint_type="crm_pipeline",
        expected_outcomes=["Eliminate manual copy-paste between tools", "Ensure zero lost lead attribution"]
    ),
    SolutionCapability(
        capability_id="CAP-005-AI-CONCIERGE",
        name="AI Knowledge & Customer Service Concierge",
        category="Customer Support",
        description="Grounded conversational assistant answering service inquiries, company policies, and routing complex cases to humans.",
        problem="High volume of routine customer inquiries overwhelms frontline staff during peak and off hours.",
        trigger="Inbound customer message in chat or web portal.",
        inputs=["session_id", "customer_message", "customer_profile", "knowledge_base_context"],
        logic="Retrieve grounded FAQ/knowledge chunks -> synthesize polite, accurate response -> check confidence threshold -> escalate if low.",
        integrations=["Gemini AI / LLM Gateway", "Vector/Document Search", "Support Ticket Desk"],
        actions=["Return answer to customer", "Log conversation history", "Open ticket for human review if escalated"],
        human_ceo_gates="Low confidence (< 0.75) or legal/complaint keywords immediately route to human support lead.",
        measurable_outcome="Resolve 60%+ routine inquiries autonomously; 24/7 instant response.",
        requirements=["Service FAQs and business profile docs", "Gemini AI model integration", "Confidence threshold fallback"],
        dependencies=["n8n-nodes-base.webhook", "@n8n/n8n-nodes-langchain.agent", "n8n-nodes-base.httpRequest"],
        cost_profile_usd=40.0,
        target_price_usd=1800.0,
        setup_fee_usd=1500.0,
        monthly_management_usd=400.0,
        complexity_level="HIGH",
        risk_level="MEDIUM",
        compatible_n8n_templates=["AGY-SUPPORT-TicketTriage-AutoResponder-v1.0"],
        demo_blueprint_type="ai_chat",
        expected_outcomes=["Resolve 60%+ routine questions instantly", "24/7 brand representation"]
    ),
    SolutionCapability(
        capability_id="CAP-006-INVOICE-AP-EXTRACTOR",
        name="Automated Invoice & Document Ingestion Pipeline",
        category="Invoice/AP Processing",
        description="OCR and LLM-driven structured data extraction from PDF invoices into accounting tables with validation checks.",
        problem="Manual AP data entry from vendor invoices causes payment delays and human transposition errors.",
        trigger="New invoice PDF uploaded to inbox or cloud folder.",
        inputs=["document_binary", "vendor_id", "invoice_file_name", "timestamp"],
        logic="Extract text via OCR/PDF parser -> extract line items & totals using schema -> match PO/vendor -> validate math -> stage for payment.",
        integrations=["Document Storage (S3/Drive)", "Accounting Software (QuickBooks/Xero)", "Stripe AP"],
        actions=["Parse line items", "Stage bill in accounting system", "Alert finance on mismatch"],
        human_ceo_gates="Total variance > $0.01 or new vendor requires human controller approval.",
        measurable_outcome="Cut AP processing time by 75%; eliminate double-entry errors.",
        requirements=["Document inbox / file drop", "Structured schema definition", "Discrepancy review queue"],
        dependencies=["n8n-nodes-base.readBinaryFile", "n8n-nodes-base.httpRequest", "n8n-nodes-base.code"],
        cost_profile_usd=35.0,
        target_price_usd=1600.0,
        setup_fee_usd=1300.0,
        monthly_management_usd=300.0,
        complexity_level="HIGH",
        risk_level="MEDIUM",
        compatible_n8n_templates=["AGY-AUDIT-DomainEnrichment-DiagnosticVector-v1.0"],
        demo_blueprint_type="intake_portal",
        expected_outcomes=["Cut AP processing time by 75%", "Prevent double-entry errors"]
    ),

    # -------------------------------------------------------------
    # PRODUCTIZED AUTOMATION CAPABILITIES (AGY-AUTO-01 - 10)
    # -------------------------------------------------------------

    # 1. MISSED CALL TEXT-BACK
    SolutionCapability(
        capability_id="AGY-AUTO-MISSED-CALL-TEXTBACK",
        name="Missed Call Text-Back Automation",
        category="Lead Response",
        description="Instant automated SMS text-back to missed customer calls with caller identification, business hours detection, and opt-out suppression.",
        problem="Businesses miss 20-40% of inbound calls during peak hours or after-hours, causing high-intent prospects to call competitors immediately.",
        trigger="Inbound telephony missed call or abandoned call webhook event.",
        inputs=["caller_phone", "caller_name", "call_timestamp", "business_id", "call_duration_seconds", "is_after_hours"],
        logic=(
            "Detect missed call event -> verify caller phone -> check suppression & opt-out database "
            "-> deduplicate within 15-minute window -> select business-hours vs after-hours template "
            "-> dispatch approved SMS -> record interaction in CRM -> listen for customer reply."
        ),
        integrations=["Telephony Provider (Twilio/Telnyx)", "Agency OS Suppression Registry", "CRM Database", "Event Bus"],
        actions=["Dispatch personalized SMS text-back", "Persist call record in CallLog", "Create/update CRM contact", "Notify operator on reply"],
        human_ceo_gates="Automated hard stop on suppression/opt-out; high-frequency caller surge (> 5 calls/hour) alerts human manager.",
        measurable_outcome="Sub-30 second response to missed calls; 35-50% inquiry recovery rate; zero messages sent to suppressed numbers.",
        requirements=["Twilio/Telnyx or PBX webhook", "SMS sending phone number", "Approved SMS messaging copy", "Opt-out keyword handling"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.code", "n8n-nodes-base.if", "n8n-nodes-base.respondToWebhook"],
        cost_profile_usd=10.0,
        target_price_usd=950.0,
        setup_fee_usd=750.0,
        monthly_management_usd=200.0,
        complexity_level="LOW",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-AUTO-MissedCallTextBack-SafetyFloor-v1.0"],
        n8n_implementation_status="COMMERCIAL_READY",
        demo_blueprint_type="call_simulator",
        production_implementation_path="DEMO -> PROPOSAL -> ADVANCE PAYMENT VERIFIED -> SMS Provider Provisioning -> Staged Testing -> Production Deployment",
        expected_outcomes=["Recover 35-50% of missed inbound callers", "Sub-30s response time guaranteed", "100% compliance with carrier SMS rules"]
    ),

    # 2. REVIEW REQUEST AUTOMATION
    SolutionCapability(
        capability_id="AGY-AUTO-REVIEW-REQUEST",
        name="Customer Review Request Automation",
        category="CRM Automation",
        description="Systematic post-service review request sequence dispatched at optimal delays with duplicate suppression and explicit review platform links.",
        problem="Businesses complete great work but fail to collect customer reviews, resulting in weak search rankings and lost social proof.",
        trigger="Qualifying customer event (job completed, ticket resolved, final payment received).",
        inputs=["customer_id", "customer_name", "contact_phone", "contact_email", "job_id", "service_type", "completion_timestamp", "review_platform_url"],
        logic=(
            "Detect qualifying event -> wait configured delay (e.g. 2h - 24h) -> verify no open disputes or unresolved tickets "
            "-> check duplicate suppression (max 1 review request per customer per 90 days) -> send approved SMS/email with explicit review link "
            "-> log request -> monitor link click or feedback."
        ),
        integrations=["Job/Billing System (Stripe/ServiceTitan/Jobber)", "SMS/Email Dispatcher", "Review Platform API (Google Business / Trustpilot)", "CRM"],
        actions=["Schedule delayed message", "Send polite review invite", "Record review request event", "Halt sequence if feedback submitted"],
        human_ceo_gates="Negative rating flag (< 3 stars) or active customer complaint suppresses review request immediately and routes to CEO/manager.",
        measurable_outcome="20-35% review generation rate; zero duplicate spam requests; zero requests sent to dissatisfied customers.",
        requirements=["Qualifying completion webhook", "Explicit review platform URL (no fabricated links)", "Delay configuration", "Suppression rules"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.dateTime", "n8n-nodes-base.code", "n8n-nodes-base.respondToWebhook"],
        cost_profile_usd=12.0,
        target_price_usd=850.0,
        setup_fee_usd=650.0,
        monthly_management_usd=175.0,
        complexity_level="LOW",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-ONBOARD-ClientWelcome-SetupJourney-v1.0"],
        n8n_implementation_status="COMMERCIAL_READY",
        demo_blueprint_type="workflow_stepper",
        production_implementation_path="DEMO -> PROPOSAL -> ADVANCE PAYMENT VERIFIED -> Job System Webhook Integration -> Review Link Verification -> Production Rollout",
        expected_outcomes=["Increase monthly Google review volume by 3-5x", "Protect reputation by filtering dissatisfied clients"]
    ),

    # 3. APPOINTMENT REMINDER SYSTEM
    SolutionCapability(
        capability_id="AGY-AUTO-APPOINTMENT-REMINDER",
        name="Multi-Stage Appointment Reminder System",
        category="Appointment Automation",
        description="Automated multi-touch reminder sequences (24h, 2h, and custom) with two-way confirmation and reschedule handling.",
        problem="Customer no-shows and last-minute cancellations waste technician hours, clinic chairs, and operational capacity.",
        trigger="Appointment scheduled or updated in calendar or booking database.",
        inputs=["appointment_id", "customer_name", "customer_phone", "customer_email", "appointment_timestamp", "service_name", "location_address"],
        logic=(
            "Appointment created -> calculate reminder schedule (T-24h and T-2h) -> dispatch 24h reminder with confirmation/reschedule prompt "
            "-> process inbound reply ('C' = Confirmed, 'R' = Reschedule) -> dispatch 2h day-of reminder with directions -> update appointment status "
            "-> suppress duplicate reminders if confirmed."
        ),
        integrations=["Google Calendar / Outlook / Cal.com", "SMS Gateway (Twilio)", "CRM Database", "Operator Alert Queue"],
        actions=["Dispatch 24h SMS/Email", "Dispatch 2h SMS reminder", "Update calendar appointment status", "Notify coordinator on reschedule request"],
        human_ceo_gates="Reschedule request or cancellation triggers immediate notification to dispatch/office coordinator for rebooking.",
        measurable_outcome="Reduce appointment no-show rate by 60-80%; 100% automated status synchronization; zero duplicate reminders.",
        requirements=["Calendar/Booking system API access", "SMS sender credentials", "Two-way response webhook", "Timezone normalization"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.dateTime", "n8n-nodes-base.switch", "n8n-nodes-base.respondToWebhook"],
        cost_profile_usd=15.0,
        target_price_usd=1100.0,
        setup_fee_usd=850.0,
        monthly_management_usd=225.0,
        complexity_level="MODERATE",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-CRM-InboundReply-IntentClassifier-v1.0"],
        n8n_implementation_status="COMMERCIAL_READY",
        demo_blueprint_type="booking_flow",
        production_implementation_path="DEMO -> PROPOSAL -> ADVANCE PAYMENT VERIFIED -> Calendar OAuth Linking -> Two-way SMS Setup -> Production Deployment",
        expected_outcomes=["Reduce appointment no-shows below 5%", "Eliminate manual confirmation calling time"]
    ),

    # 4. CUSTOMER RE-ENGAGEMENT SEQUENCE
    SolutionCapability(
        capability_id="AGY-AUTO-REENGAGEMENT",
        name="Dormant Customer Re-Engagement Sequence",
        category="Sales Follow-up",
        description="Intelligent re-activation sequence for past customers and dormant leads with frequency capping, suppression, and immediate halt on response.",
        problem="Past customers and inactive leads sit idle in databases without systematic follow-up, abandoning repeat service revenue.",
        trigger="Inactivity threshold reached (e.g. 60, 90, 180 days since last interaction or service).",
        inputs=["customer_id", "customer_name", "contact_info", "last_service_date", "past_service_type", "touch_count", "lifetime_value"],
        logic=(
            "Query dormant customer segment -> check suppression list and global opt-outs -> enforce frequency cap (max 2 touches, minimum 45 days apart) "
            "-> generate personalized seasonal or check-in touch -> dispatch message -> monitor inbound responses "
            "-> IMMEDIATELY HALT sequence upon reply or opt-out -> advance pipeline."
        ),
        integrations=["CRM Database", "Email/SMS Sender", "Reply Classifier", "Suppression Registry"],
        actions=["Dispatch personalized check-in", "Log touch in interaction history", "Cancel sequence on reply", "Alert account executive on positive intent"],
        human_ceo_gates="Accounts with past LTV > $5,000 require account manager approval before sequence launch; strict opt-out compliance.",
        measurable_outcome="Reactivate 8-15% of dormant customer base; 100% compliance with maximum touch frequency caps.",
        requirements=["Dormant contact segmentation criteria", "Suppression list validation", "Touch limit cap (max 2)", "Opt-out unsubscribe mechanism"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.code", "n8n-nodes-base.if", "n8n-nodes-base.respondToWebhook"],
        cost_profile_usd=20.0,
        target_price_usd=1300.0,
        setup_fee_usd=950.0,
        monthly_management_usd=275.0,
        complexity_level="MODERATE",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-FOLLOWUP-SmartCadence-AutoCancelOnReply-v1.0"],
        n8n_implementation_status="COMMERCIAL_READY",
        demo_blueprint_type="workflow_stepper",
        production_implementation_path="DEMO -> PROPOSAL -> ADVANCE PAYMENT VERIFIED -> Customer Database Segmentation -> Copy Sign-Off -> Controlled Pilot Launch",
        expected_outcomes=["Reclaim $10k+ in dormant service revenue annually", "Zero spam complaints via strict frequency capping"]
    ),

    # 5. ESTIMATE FOLLOW-UP AUTOMATION
    SolutionCapability(
        capability_id="AGY-AUTO-ESTIMATE-FOLLOWUP",
        name="Structured Estimate & Proposal Follow-Up Sequence",
        category="Sales Follow-up",
        description="Respectful, multi-stage estimate follow-up sequence that answers customer objections, tracks proposal status, and halts immediately upon acceptance.",
        problem="High-value proposals and estimates go cold because sales representatives fail to follow up consistently after initial quote delivery.",
        trigger="Estimate or proposal created and sent to prospect.",
        inputs=["quote_id", "prospect_id", "prospect_email", "prospect_phone", "quote_amount", "service_items", "sent_timestamp", "expiration_date"],
        logic=(
            "Estimate sent event -> wait configured delay (e.g. 48 hours) -> check quote status (still PENDING?) "
            "-> if pending, dispatch non-aggressive check-in offering to answer technical questions -> wait second interval (e.g. 5 days) "
            "-> dispatch reminder highlighting upcoming expiry -> STOP immediately if quote accepted, rejected, or reply received."
        ),
        integrations=["Quoting / Invoicing Platform (Stripe/QuickBooks/Custom)", "Email/SMS Dispatcher", "Reply Intent Classifier", "CRM Pipeline"],
        actions=["Send courteous follow-up", "Log touch event in CRM", "Cancel pending touches upon reply/signature", "Alert rep on questions"],
        human_ceo_gates="Proposals above $5,000 flag sales director before final follow-up touch; negative replies auto-cancel further messages.",
        measurable_outcome="20-30% higher quote close rate; 0 spam complaints; instant cadence termination on customer response.",
        requirements=["Estimate creation webhook or status poller", "Configured business-day delay windows", "Template copy without aggressive sales pressure"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.dateTime", "n8n-nodes-base.if", "n8n-nodes-base.respondToWebhook"],
        cost_profile_usd=18.0,
        target_price_usd=1250.0,
        setup_fee_usd=900.0,
        monthly_management_usd=250.0,
        complexity_level="MODERATE",
        risk_level="LOW",
        compatible_n8n_templates=["AGY-FOLLOWUP-SmartCadence-AutoCancelOnReply-v1.0"],
        n8n_implementation_status="COMMERCIAL_READY",
        demo_blueprint_type="roi_calculator",
        production_implementation_path="DEMO -> PROPOSAL -> ADVANCE PAYMENT VERIFIED -> Invoicing Webhook Integration -> Follow-up Cadence Configuration -> Staged Rollout",
        expected_outcomes=["Increase proposal win rate by 20-30%", "Prevent deals from silently falling through cracks"]
    ),

    # 6. LEAD FOLLOW-UP SYSTEM (Reusing existing Agency OS outreach & reply infrastructure)
    SolutionCapability(
        capability_id="AGY-AUTO-LEAD-FOLLOWUP",
        name="Intelligent Inbound Lead Follow-Up System",
        category="Lead Response",
        description="Sub-minute inbound lead response and multi-stage follow-up cadence reusing existing Agency OS qualification, reply classifier, and worker.",
        problem="Inbound leads contact multiple providers; failing to follow up within minutes drastically reduces conversion probability.",
        trigger="New qualified inbound lead received via web form, marketplace, or inbound webhook.",
        inputs=["lead_id", "lead_name", "email", "phone", "requirements", "qualification_score", "source"],
        logic=(
            "Ingest lead -> verify commercial floor & qualification rubric (reusing Agency OS scoring) "
            "-> check suppression registry -> dispatch personalized first touch (< 60s) -> schedule multi-stage follow-up "
            "-> poll inbox for reply -> classify sentiment & intent -> auto-cancel pending follow-ups on reply -> alert CEO/operator."
        ),
        integrations=["Agency OS Outreach Sender", "Agency OS Reply Classifier", "Agency OS Inbox Poller", "Agency OS Persistent Worker", "SQLite/Postgres"],
        actions=["Qualify lead", "Send first-touch response", "Schedule 2-touch cadence", "Cancel cadence on reply", "Notify operator on positive intent"],
        human_ceo_gates="Interested / positive replies automatically route to operator for discovery requirements gathering; unsubscribes auto-suppressed.",
        measurable_outcome="Sub-60s first touch response; 100% automated cancellation on reply; zero duplicate touches.",
        requirements=["Existing Agency OS outreach infrastructure", "Qualification rubric", "Approved sender identity"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.code", "n8n-nodes-base.if", "n8n-nodes-base.respondToWebhook"],
        cost_profile_usd=20.0,
        target_price_usd=1400.0,
        setup_fee_usd=1000.0,
        monthly_management_usd=300.0,
        complexity_level="MODERATE",
        risk_level="LOW",
        compatible_n8n_templates=[
            "AGY-SCORE-LeadQualification-CommercialFloor-v1.0",
            "AGY-CRM-InboundReply-IntentClassifier-v1.0",
            "AGY-FOLLOWUP-SmartCadence-AutoCancelOnReply-v1.0"
        ],
        n8n_implementation_status="COMMERCIAL_READY",
        demo_blueprint_type="chat_simulator",
        production_implementation_path="REUSES_EXISTING_AGENCY_OS_CORE -> PROPOSAL -> ADVANCE PAYMENT VERIFIED -> Configure client intake webhook -> Staging verification -> Live activation",
        expected_outcomes=["Engage 100% of qualified leads in under 60 seconds", "Double sales qualified meeting booking rate"]
    ),

    # 7. SEASONAL CAMPAIGN ENGINE
    SolutionCapability(
        capability_id="AGY-AUTO-SEASONAL-CAMPAIGN",
        name="Seasonal & Lifecycle Campaign Engine",
        category="Personalized Outreach",
        description="Audience segmentation and lifecycle marketing engine with mandatory CEO approval gates, version tracking, and scheduled batch dispatch.",
        problem="Businesses miss high-margin seasonal demand spikes (e.g. spring tune-ups, year-end promotions) due to lack of structured campaign planning.",
        trigger="Seasonal calendar milestone or operator campaign trigger.",
        inputs=["campaign_id", "campaign_name", "target_niche", "segment_criteria", "offer_summary", "scheduled_dispatch_date"],
        logic=(
            "Define campaign parameters -> query eligible audience from CRM -> filter against suppression list and recent touch caps "
            "-> generate personalized copy variants -> STAGE FOR MANDATORY CEO/HUMAN APPROVAL -> upon approval, schedule batch dispatch "
            "-> track delivery, open, click, and response telemetry -> persist campaign version history."
        ),
        integrations=["CRM Audience Segmenter", "Template Personalizer", "Email/SMS Dispatcher", "Operator Approval Dashboard"],
        actions=["Stage campaign version", "Require human sign-off", "Dispatch approved batches", "Track conversion telemetry"],
        human_ceo_gates="MANDATORY CEO / Operator sign-off gate before any seasonal campaign can dispatch. Zero automated unapproved blasting.",
        measurable_outcome="15-25% seasonal revenue boost; 100% version audit trail; zero unauthorized messages.",
        requirements=["Customer database segment criteria", "Approval dashboard sign-off", "Batch throttling configuration"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.code", "n8n-nodes-base.httpRequest"],
        cost_profile_usd=25.0,
        target_price_usd=1500.0,
        setup_fee_usd=1100.0,
        monthly_management_usd=350.0,
        complexity_level="MODERATE",
        risk_level="MEDIUM",
        compatible_n8n_templates=["AGY-OUTREACH-PersonalizedDrafter-SafetyGuard-v1.0"],
        n8n_implementation_status="COMMERCIAL_READY",
        demo_blueprint_type="workflow_stepper",
        production_implementation_path="DEMO -> PROPOSAL -> ADVANCE PAYMENT VERIFIED -> Audience Segmentation Setup -> Template Approval -> Production Batching",
        expected_outcomes=["Drive 15-25% seasonal booking lift", "Complete campaign versioning and delivery audit trail"]
    ),

    # 8. COLD OUTREACH AUTOMATION (Reusing existing Agency OS cold outreach system)
    SolutionCapability(
        capability_id="AGY-AUTO-COLD-OUTREACH",
        name="Compliant B2B Cold Outreach Engine",
        category="Personalized Outreach",
        description="Evidence-grounded outbound prospecting reusing existing Agency OS research, qualification, personalized drafting, approval, and real providers.",
        problem="Cold email prospecting is often generic, poorly targeted, and risks domain reputation without strict deliverability and compliance guardrails.",
        trigger="Prospect identified and qualified above commercial floor ($500+).",
        inputs=["prospect_id", "domain", "contact_email", "audit_findings", "commercial_score", "verified_niche"],
        logic=(
            "Deep research & technical audit -> verify commercial feasibility floor ($500+) -> synthesize personalized outreach "
            "linking audit findings to concrete business value -> execute 14-point safety check (CAN-SPAM, opt-out, zero spam words) "
            "-> STAGE FOR HUMAN OR POLICY APPROVAL -> dispatch via verified provider -> poll inbox -> classify reply -> auto-cancel follow-ups."
        ),
        integrations=["Agency OS Audit Engine", "Agency OS Personalization Generator", "Sender Registry", "Inbox Poller", "Followup Engine"],
        actions=["Generate evidence draft", "Validate compliance rules", "Stage for approval", "Dispatch upon sign-off", "Auto-cancel cadence on reply"],
        human_ceo_gates="Policy approval gate (autonomous threshold or manual operator approval); unhandled replies route to human triage.",
        measurable_outcome="Sub-1% bounce rate; 0 spam trap hits; 15-25% qualified reply rate; 100% cadence cancellation on response.",
        requirements=["Existing Agency OS outreach engine", "Verified sending domain & SPF/DKIM/DMARC", "CAN-SPAM physical address & unsubscribe"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.code", "n8n-nodes-base.if", "n8n-nodes-base.respondToWebhook"],
        cost_profile_usd=30.0,
        target_price_usd=1600.0,
        setup_fee_usd=1200.0,
        monthly_management_usd=350.0,
        complexity_level="HIGH",
        risk_level="MEDIUM",
        compatible_n8n_templates=[
            "AGY-OUTREACH-PersonalizedDrafter-SafetyGuard-v1.0",
            "AGY-FOLLOWUP-SmartCadence-AutoCancelOnReply-v1.0"
        ],
        n8n_implementation_status="COMMERCIAL_READY",
        demo_blueprint_type="speed_comparator",
        production_implementation_path="REUSES_EXISTING_AGENCY_OS_CORE -> PROPOSAL -> ADVANCE PAYMENT VERIFIED -> Domain setup -> Sender warmup -> Staged outreach deployment",
        expected_outcomes=["High-conversion cold outreach without domain burn", "Zero manual copy-pasting of prospect audits"]
    ),

    # 9. AI VOICE RECEPTIONIST (Integration Capability)
    SolutionCapability(
        capability_id="AGY-AUTO-AI-RECEPTIONIST",
        name="24/7 AI Voice Receptionist System",
        category="Voice & Telephony",
        description="Conversational telephony receptionist answering inbound phone calls, answering business FAQs, qualifying caller intent, and booking appointments.",
        problem="Small and medium businesses miss hundreds of phone calls each month during service jobs, weekends, and after-hours.",
        trigger="Inbound telephone call received on business virtual/forwarded line.",
        inputs=["caller_id", "call_audio_stream", "call_timestamp", "business_knowledge_base", "calendar_availability"],
        logic=(
            "Inbound call connection -> voice telephony stream -> conversational AI agent greeting -> ground on business profile & FAQs "
            "-> qualify caller intent & service needs -> offer available appointment slots -> confirm booking -> persist audio & transcript "
            "-> dispatch SMS summary to caller -> alert on-call manager."
        ),
        integrations=["External Voice Telephony Provider (Vapi / Retell / Bland / Twilio Voice)", "Calendar API", "CRM Database", "SMS Gateway"],
        actions=["Answer phone call", "Conduct voice conversation", "Book calendar appointment", "Save call recording & transcript", "Send summary SMS"],
        human_ceo_gates="Emergency calls, angry callers, or high-value commercial inquiries immediately bridge to human operator phone line.",
        measurable_outcome="100% call answer rate in under 2 rings; 50-70% routine inquiry resolution without human intervention.",
        requirements=["Third-party telephony provider credentials (Vapi/Retell/Bland)", "SIP trunk or Twilio phone number", "Business knowledge base ingestion"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.httpRequest"],
        cost_profile_usd=60.0,
        target_price_usd=2200.0,
        setup_fee_usd=1800.0,
        monthly_management_usd=450.0,
        complexity_level="ENTERPRISE",
        risk_level="HIGH",
        compatible_n8n_templates=[],
        n8n_implementation_status="N8N_WORKFLOW_REQUIRED",
        demo_blueprint_type="call_simulator",
        production_implementation_path="INTEGRATION_REQUIRED: Requires customer-provided Vapi/Retell/Twilio credentials -> DEMO -> PROPOSAL -> ADVANCE PAYMENT -> Provisioning -> Live Call Testing",
        expected_outcomes=["Zero missed calls 24/7", "Immediate appointment booking over phone", "Clear PROTOTYPE SIMULATION demo labelling"]
    ),

    # 10. FULL BACKEND CRM SYSTEM (Custom Software Capability)
    SolutionCapability(
        capability_id="AGY-AUTO-CRM-SYSTEM",
        name="Custom Commercial CRM & Operations Management System",
        category="Custom Software",
        description="Turnkey custom operations CRM with lead pipelines, contact management, communication history, automated triggers, and executive reporting.",
        problem="Generic SaaS CRMs are either overly rigid, priced on punitive per-seat tiers, or fail to match the company's proprietary operational steps.",
        trigger="Operational business event (new lead, status change, invoice generated, appointment booked).",
        inputs=["entity_type (contact, company, deal, task, appointment)", "action (create, read, update, delete)", "operator_id", "payload"],
        logic=(
            "Custom web software architecture: modular contact & deal management -> interactive Kanban pipeline -> activity timeline "
            "-> calendar & booking synchronization -> role-based access control -> custom automation triggers -> live analytics dashboard."
        ),
        integrations=["PostgreSQL / SQLite Database", "Authentication & RBAC Service", "Email/SMS Service Providers", "Stripe Billing"],
        actions=["Persist business records", "Manage deal pipeline stages", "Log full interaction audit trail", "Render executive reporting"],
        human_ceo_gates="Production deployment requires complete discovery: DEMO -> PROPOSAL -> ADVANCE PAYMENT CONFIRMED (40%) -> PRODUCTION BUILD.",
        measurable_outcome="100% tailored fit to operational process; zero recurring per-seat license costs; consolidated single pane of glass.",
        requirements=["Database schema design", "Authentication setup", "Dedicated server or cloud hosting", "Client operational spec approval"],
        dependencies=["n8n-nodes-base.webhook", "n8n-nodes-base.httpRequest", "n8n-nodes-base.code"],
        cost_profile_usd=80.0,
        target_price_usd=3500.0,
        setup_fee_usd=2800.0,
        monthly_management_usd=500.0,
        complexity_level="ENTERPRISE",
        risk_level="MEDIUM",
        compatible_n8n_templates=["AGY-CRM-PipelineSyncer-AuditLog-v1.0"],
        n8n_implementation_status="COMMERCIAL_READY",
        demo_blueprint_type="crm_pipeline",
        production_implementation_path="DEMO PROTOTYPE -> SCOPE SPECIFICATION -> PROPOSAL -> 40% ADVANCE PAYMENT CONFIRMED -> STAGING SPRINT -> PRODUCTION DEPLOYMENT",
        expected_outcomes=["Consolidated operational system owned by the client", "Save thousands in recurring SaaS per-seat licenses"]
    ),
]


class SolutionCapabilityCatalog:
    """
    Query interface for the Solution Capability Catalog.
    """

    def __init__(self, capabilities: Optional[List[SolutionCapability]] = None):
        self._capabilities = capabilities or CAPABILITY_REGISTRY

    def list_capabilities(self) -> List[SolutionCapability]:
        return list(self._capabilities)

    ALIAS_MAP = {
        "CAP-002-CALL-RECOVERY": "AGY-AUTO-MISSED-CALL-TEXTBACK",
        "CAP-003-AI-RECEPTIONIST": "CAP-005-AI-CONCIERGE",
        "CAP-004-APPOINTMENT-AUTOMATION": "CAP-002-BOOKING-AUTOMATION",
        "CAP-005-CRM-AUTOMATION": "CAP-004-CRM-PIPELINE-SYNC",
    }

    def get_capability(self, capability_id: str) -> Optional[SolutionCapability]:
        resolved_id = self.ALIAS_MAP.get(capability_id, capability_id)
        for cap in self._capabilities:
            if cap.capability_id == resolved_id or cap.capability_id == capability_id:
                return cap
        return None

    def find_by_category(self, category: str) -> List[SolutionCapability]:
        cat_lower = category.lower()
        return [c for c in self._capabilities if cat_lower in c.category.lower()]

    def find_by_n8n_template(self, template_name: str) -> Optional[SolutionCapability]:
        for cap in self._capabilities:
            if template_name in cap.compatible_n8n_templates:
                return cap
        return None

    def find_by_industry(self, industry: str) -> List[SolutionCapability]:
        ind_lower = industry.lower()
        return [
            c for c in self._capabilities
            if any(ind_lower in ind.lower() for ind in c.supported_industries)
        ]


capability_catalog = SolutionCapabilityCatalog()

