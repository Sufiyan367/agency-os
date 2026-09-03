from typing import Dict, Any, List
from pydantic import BaseModel, Field

class ServicePackage(BaseModel):
    id: str
    name: str
    price: float
    turnaround: str
    deliverables: List[str]
    ideal_for: str

class BusinessProfile(BaseModel):
    name: str
    industry: str
    location: str
    website: str
    phone: str
    email: str
    booking_url: str
    working_hours: str
    tone: str
    pricing_catalog: List[ServicePackage]
    faqs: Dict[str, str]
    escalation_rules: List[str]
    unauthorized_claims: List[str]

# Demo Business: Apex Comfort Heating & Air
DEMO_BUSINESS = BusinessProfile(
    name="Apex Comfort Heating & Air",
    industry="Residential & Commercial HVAC",
    location="Austin, Texas (Travis & Williamson Counties)",
    website="https://apexcomfortair.example.com",
    phone="+1 (512) 555-0198",
    email="service@apexcomfortair.example.com",
    booking_url="https://cal.com/apexcomfort/diagnostic",
    working_hours="Monday - Friday: 7:30 AM - 6:00 PM CST | Saturday: 8:00 AM - 1:00 PM CST",
    tone="Direct, respectful, helpful, and technically grounded. Prioritize speed-to-response without fluff.",
    pricing_catalog=[
        ServicePackage(
            id="emergency-diagnostic",
            name="Complete System Health & Diagnostic Audit",
            price=149.0,
            turnaround="Same Day (under 4 hours)",
            deliverables=[
                "24-point electrical & compressor safety check",
                "Refrigerant leak sweep & pressure test",
                "Airflow static pressure reading",
                "Immediate written diagnostic remediation plan"
            ],
            ideal_for="Units making grinding noises, blowing warm air, or failing to cycle."
        ),
        ServicePackage(
            id="efficiency-tuneup",
            name="Seasonal Precision Performance Tune-Up",
            price=389.0,
            turnaround="1 Business Day",
            deliverables=[
                "Evaporator & condenser coil deep chemical wash",
                "Blower motor amperage calibration",
                "Capacitor load verification",
                "Condensate drain line flush & anti-algae tablet treat"
            ],
            ideal_for="Systems older than 3 years showing rising electric utility bills."
        ),
        ServicePackage(
            id="iaq-smart-upgrade",
            name="Smart Climate & Clean Air Duct Sealing Package",
            price=890.0,
            turnaround="2 Business Days",
            deliverables=[
                "Ecobee/Nest Pro smart thermostat hardwire & Wi-Fi zoning",
                "Supply & return duct static pressure leak sealing",
                "MERV 13 high-velocity particulate filtration install",
                "Full operational walkthrough and smartphone control pairing"
            ],
            ideal_for="Homes with allergy concerns, uneven room cooling, or obsolete thermostats."
        )
    ],
    faqs={
        "Do you offer emergency after-hours dispatch?": "Yes, our on-call technicians respond to emergency requests 24/7 in Austin and surrounding metro areas.",
        "What brands do you service?": "We service all major brands including Trane, Carrier, Lennox, Goodman, Rheem, and Daikin.",
        "Are diagnostics credited toward repairs?": "Yes, if you proceed with approved repair work over $300, 100% of your $149 diagnostic fee is applied directly to the balance.",
        "Are your technicians licensed and insured?": "Every technician holds a Texas TDLR certification, EPA Universal Section 608 license, and full liability coverage."
    },
    escalation_rules=[
        "Lead explicitly requests a phone call with the master technician or owner.",
        "Customer reports active gas smell, electrical burning, or major water leaking from attic unit.",
        "Quote request exceeds $5,000 (full multi-zone system replacement).",
        "Lead expresses frustration, dispute, or mentions prior service warranty."
    ],
    unauthorized_claims=[
        "Never promise free complete system replacements or warranties outside written terms.",
        "Never quote fixed equipment changeout prices without on-site manual J load calculation.",
        "Never invent emergency arrival times under 45 minutes."
    ]
)

def get_demo_business() -> BusinessProfile:
    return DEMO_BUSINESS
