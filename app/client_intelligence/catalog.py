from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from app.client_intelligence.models import BusinessSegment


@dataclass
class ServiceCatalogItem:
    id: str
    name: str
    category: str
    description: str
    prerequisites: List[str]
    suitable_industries: List[str]  # ["*"] denotes broad universal fit
    suitable_business_sizes: List[BusinessSegment]
    required_inputs: List[str]
    implementation_complexity: str  # "Low", "Moderate", "High", "Enterprise"
    expected_business_outcomes: List[str]
    estimated_implementation_effort_days: int
    pricing_min_usd: float
    pricing_max_usd: float
    recommended_target_price_usd: float
    risks: List[str]
    contraindications: List[str]


SERVICE_CATALOG: Dict[str, ServiceCatalogItem] = {
    "SERVICE_001": ServiceCatalogItem(
        id="SERVICE_001",
        name="AI Lead Qualification",
        category="Lead Operations",
        description="Autonomous intake and 24/7 intelligent screening of inbound website/form leads to identify budget, timeline, and decision-maker status.",
        prerequisites=["Public website with active contact channel or inquiry form"],
        suitable_industries=["*"],
        suitable_business_sizes=[BusinessSegment.MICRO, BusinessSegment.SMALL, BusinessSegment.SMB, BusinessSegment.MID_MARKET],
        required_inputs=["Service catalog", "Ideal customer profile parameters", "Intake qualification criteria"],
        implementation_complexity="Moderate",
        expected_business_outcomes=[
            "Eliminates manual lead screening delays",
            "Filters low-budget or non-serviceable inquiries before staff intervention",
            "Accelerates qualified lead handoff to sales within 60 seconds"
        ],
        estimated_implementation_effort_days=5,
        pricing_min_usd=500.0,
        pricing_max_usd=1450.0,
        recommended_target_price_usd=1000.0,
        risks=["Overly aggressive filtering on edge-case client requests"],
        contraindications=["Businesses with zero inbound web or digital lead traffic"]
    ),
    "SERVICE_002": ServiceCatalogItem(
        id="SERVICE_002",
        name="AI Customer Support",
        category="Customer Support",
        description="Autonomous tier-1 inquiry resolution handling service FAQs, availability, basic pricing, and company credentials 24/7.",
        prerequisites=["Structured list of standard operational FAQs and business policies"],
        suitable_industries=["*"],
        suitable_business_sizes=[BusinessSegment.SMALL, BusinessSegment.SMB, BusinessSegment.MID_MARKET],
        required_inputs=["FAQ documentation", "Pricing boundaries", "Escalation routing rules"],
        implementation_complexity="Moderate",
        expected_business_outcomes=[
            "Provides instant response times to repetitive customer queries",
            "Recovers 10-15 staff hours weekly spent answering identical questions",
            "Maintains 24/7 responsiveness during off-hours and weekends"
        ],
        estimated_implementation_effort_days=6,
        pricing_min_usd=600.0,
        pricing_max_usd=1650.0,
        recommended_target_price_usd=1100.0,
        risks=["Hallucination on non-standard custom quotes without strict guardrails"],
        contraindications=["Companies requiring bespoke regulatory/legal contracts before any response"]
    ),
    "SERVICE_003": ServiceCatalogItem(
        id="SERVICE_003",
        name="Automated Lead Follow-up",
        category="Sales Enablement",
        description="Event-triggered multi-touch follow-up cadence ensuring zero uncontacted leads slip through the cracks after initial inquiry.",
        prerequisites=["Email or SMS delivery channel and form capture trigger"],
        suitable_industries=["*"],
        suitable_business_sizes=[BusinessSegment.MICRO, BusinessSegment.SMALL, BusinessSegment.SMB, BusinessSegment.MID_MARKET],
        required_inputs=["Approved messaging templates", "Timing intervals", "Stop-rule conditions"],
        implementation_complexity="Low",
        expected_business_outcomes=[
            "Boosts lead conversion rates by guaranteeing 3-5 persistent follow-ups",
            "Eliminates lead drop-off caused by busy field or office technicians",
            "Automatically pauses cadences the instant a prospect responds"
        ],
        estimated_implementation_effort_days=4,
        pricing_min_usd=500.0,
        pricing_max_usd=1250.0,
        recommended_target_price_usd=1000.0,
        risks=["Prospect fatigue if stop-rules fail to detect out-of-band replies"],
        contraindications=["Businesses operating strictly on immediate inbound emergency calls"]
    ),
    "SERVICE_004": ServiceCatalogItem(
        id="SERVICE_004",
        name="CRM Automation",
        category="Workflow & Integration",
        description="Automated synchronization between website inquiries, field estimates, CRM stage transitions, and pipeline records.",
        prerequisites=["Accessible CRM or structured database/sheet destination"],
        suitable_industries=["*"],
        suitable_business_sizes=[BusinessSegment.SMALL, BusinessSegment.SMB, BusinessSegment.MID_MARKET],
        required_inputs=["Field mapping schema", "Pipeline milestone definitions", "API/Webhook credentials"],
        implementation_complexity="Moderate",
        expected_business_outcomes=[
            "Eliminates error-prone manual copy-pasting between email and CRM",
            "Ensures 100% data fidelity for customer contact records",
            "Provides real-time pipeline visibility across all active leads"
        ],
        estimated_implementation_effort_days=6,
        pricing_min_usd=750.0,
        pricing_max_usd=1950.0,
        recommended_target_price_usd=1250.0,
        risks=["Schema drift if internal CRM properties change without notification"],
        contraindications=["Businesses that operate entirely on paper and refuse digital databases"]
    ),
    "SERVICE_005": ServiceCatalogItem(
        id="SERVICE_005",
        name="Invoice/AP Automation",
        category="Financial Operations",
        description="Automated invoice extraction, payment link dispatch, overdue reminder sequences, and receipt reconciliations.",
        prerequisites=["Payment gateway or accounting software destination"],
        suitable_industries=["B2B Services", "Trade Contractors", "Professional Services", "Commercial Services"],
        suitable_business_sizes=[BusinessSegment.SMB, BusinessSegment.MID_MARKET, BusinessSegment.ENTERPRISE],
        required_inputs=["Billing policy", "Invoice template", "Payment gateway credentials"],
        implementation_complexity="High",
        expected_business_outcomes=[
            "Accelerates invoice collection cycle by 40-60%",
            "Automates milestone deposit collection prior to project commencement",
            "Reclaims administrative hours spent reconciling bank receipts"
        ],
        estimated_implementation_effort_days=7,
        pricing_min_usd=850.0,
        pricing_max_usd=2400.0,
        recommended_target_price_usd=1500.0,
        risks=["Discrepancies in manual line-item dispute handling"],
        contraindications=["Cash-only businesses or pure point-of-sale retail counters"]
    ),
    "SERVICE_006": ServiceCatalogItem(
        id="SERVICE_006",
        name="Appointment Automation",
        category="Scheduling Operations",
        description="Self-service appointment booking with automated calendar conflict checks, time zone conversion, and SMS reminders.",
        prerequisites=["Google Calendar, Outlook, or booking system integration endpoint"],
        suitable_industries=["Home Services", "Roofing", "HVAC", "Plumbing", "Legal", "Medical", "Consulting"],
        suitable_business_sizes=[BusinessSegment.MICRO, BusinessSegment.SMALL, BusinessSegment.SMB],
        required_inputs=["Staff availability hours", "Buffer times", "Service duration matrices"],
        implementation_complexity="Low",
        expected_business_outcomes=[
            "Reduces appointment no-shows by up to 70% with automated reminder notifications",
            "Eliminates back-and-forth phone tag scheduling delays",
            "Allows clients to book site assessments directly 24/7"
        ],
        estimated_implementation_effort_days=4,
        pricing_min_usd=500.0,
        pricing_max_usd=1200.0,
        recommended_target_price_usd=1000.0,
        risks=["Calendar double-booking if staff maintain unlinked personal calendars"],
        contraindications=["Unscheduled walk-in businesses"]
    ),
    "SERVICE_007": ServiceCatalogItem(
        id="SERVICE_007",
        name="Business Reporting Automation",
        category="Management Intelligence",
        description="Automated weekly/monthly telemetry compiling leads, pipeline velocity, marketing channel efficiency, and revenue realization.",
        prerequisites=["Aggregatable data sources (CRM, web analytics, or billing records)"],
        suitable_industries=["*"],
        suitable_business_sizes=[BusinessSegment.SMB, BusinessSegment.MID_MARKET, BusinessSegment.ENTERPRISE],
        required_inputs=["Key KPI definitions", "Stakeholder distribution list", "Source data access"],
        implementation_complexity="Moderate",
        expected_business_outcomes=[
            "Replaces manual multi-hour spreadsheet aggregation with automated reports",
            "Provides leadership with daily/weekly pipeline health metrics",
            "Pinpoints drop-off stages in real-time before revenue leakage compounds"
        ],
        estimated_implementation_effort_days=5,
        pricing_min_usd=700.0,
        pricing_max_usd=1800.0,
        recommended_target_price_usd=1200.0,
        risks=["Data synchronization lags in legacy upstream tools"],
        contraindications=["Solopreneurs with single active client where reporting is superfluous"]
    ),
    "SERVICE_008": ServiceCatalogItem(
        id="SERVICE_008",
        name="Custom Workflow/RPA Automation",
        category="Custom Engineering",
        description="Tailored Robotic Process Automation linking legacy internal tools, PDF data scraping, or multi-step compliance documentation.",
        prerequisites=["Documented step-by-step operating procedure (SOP)"],
        suitable_industries=["Logistics", "Manufacturing", "Healthcare", "Legal", "Construction"],
        suitable_business_sizes=[BusinessSegment.SMB, BusinessSegment.MID_MARKET, BusinessSegment.ENTERPRISE],
        required_inputs=["Process video or written SOP", "Sample documents", "Target tool credentials"],
        implementation_complexity="High",
        expected_business_outcomes=[
            "Automates bespoke operational tasks saving 20+ manual hours weekly",
            "Guarantees 100% accuracy in document data transfer",
            "Unblocks scaling bottlenecks without hiring additional administrative headcount"
        ],
        estimated_implementation_effort_days=10,
        pricing_min_usd=1000.0,
        pricing_max_usd=3500.0,
        recommended_target_price_usd=2000.0,
        risks=["Brittle UI locators if legacy web application updates without notice"],
        contraindications=["Undocumented or rapidly changing ad-hoc operational processes"]
    ),
    "SERVICE_009": ServiceCatalogItem(
        id="SERVICE_009",
        name="AI Knowledge Assistant",
        category="Internal Operations",
        description="Internal AI assistant trained on business documentation, technical specs, and warranties to assist technicians and sales staff.",
        prerequisites=["Existing operational manuals, spec sheets, or warranty guidelines"],
        suitable_industries=["Contractors", "HVAC", "Manufacturing", "Solar", "Equipment Repair"],
        suitable_business_sizes=[BusinessSegment.SMALL, BusinessSegment.SMB, BusinessSegment.MID_MARKET],
        required_inputs=["PDF manuals", "Service specs", "Pricing sheets"],
        implementation_complexity="Moderate",
        expected_business_outcomes=[
            "Gives field staff instant answers to technical questions on job sites",
            "Reduces training onboarding time for new junior apprentices",
            "Prevents costly on-site estimation errors"
        ],
        estimated_implementation_effort_days=7,
        pricing_min_usd=800.0,
        pricing_max_usd=2200.0,
        recommended_target_price_usd=1400.0,
        risks=["Outdated documentation leading to obsolete part recommendations"],
        contraindications=["Businesses with no standardized service manuals or literature"]
    ),
    "SERVICE_010": ServiceCatalogItem(
        id="SERVICE_010",
        name="Integrated AI Operations System",
        category="Enterprise Transformation",
        description="Full-spectrum digital turnaround combining AI Lead Intake, Qualification, Follow-up, CRM Sync, and Performance Analytics.",
        prerequisites=["High commercial ambition and active multi-channel lead volume"],
        suitable_industries=["*"],
        suitable_business_sizes=[BusinessSegment.SMALL, BusinessSegment.SMB, BusinessSegment.MID_MARKET, BusinessSegment.ENTERPRISE],
        required_inputs=["Executive sponsorship", "Full marketing and sales workflow documentation"],
        implementation_complexity="Enterprise",
        expected_business_outcomes=[
            "End-to-end automated conversion pipeline from cold visitor to paid client",
            "Recovers 25-40 operational staff hours across sales, admin, and support",
            "Elevates client capture rate, review volume, and pipeline predictability"
        ],
        estimated_implementation_effort_days=14,
        pricing_min_usd=1500.0,
        pricing_max_usd=4500.0,
        recommended_target_price_usd=2500.0,
        risks=["Change management friction requiring clear staff onboarding"],
        contraindications=["Micro-businesses with under $50,000 annual turnover unable to support scale"]
    )
}


class ServiceCatalog:
    """Provides structured catalog queries and filtering capabilities."""

    @staticmethod
    def get_service(service_id: str) -> Optional[ServiceCatalogItem]:
        return SERVICE_CATALOG.get(service_id)

    @staticmethod
    def list_services() -> List[ServiceCatalogItem]:
        return list(SERVICE_CATALOG.values())

    @staticmethod
    def get_services_for_segment(segment: BusinessSegment) -> List[ServiceCatalogItem]:
        return [
            s for s in SERVICE_CATALOG.values()
            if segment in s.suitable_business_sizes
        ]


service_catalog = ServiceCatalog()
