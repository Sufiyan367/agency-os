from typing import Dict, Any
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.models import Customer, Project, Business, Offer

class OnboardingAutomation:
    """
    Automates post-sale client onboarding, kickoff document generation,
    and intake questionnaire packaging.
    """

    async def generate_onboarding_packet(self, session: AsyncSession, customer_id: int) -> Dict[str, Any]:
        cust = await session.get(Customer, customer_id)
        if not cust:
            raise ValueError(f"Customer {customer_id} not found.")

        biz = await session.get(Business, cust.business_id)
        offer_q = select(Offer).where(Offer.business_id == cust.business_id)
        offer = (await session.execute(offer_q)).scalars().first()

        intake_checklist = [
            {"item": "Domain Registrar / DNS Access (Cloudflare, GoDaddy, Namecheap)", "required": True},
            {"item": "Hosting / CMS Administrator Access (WordPress, Webflow, Shopify)", "required": True},
            {"item": "Google Search Console & Google Business Profile User Access", "required": False},
            {"item": "Brand Assets: High-Resolution Vector Logo (.svg / .png)", "required": True},
            {"item": "Target Geographic Zip Codes / Service Areas List", "required": True}
        ]

        kickoff_agenda = [
            "Day 1: Technical Access Verification & Staging Environment Setup",
            "Day 2-3: Core Web Vitals & Asset Optimization Deployment",
            "Day 4-5: Mobile Conversion Header & Above-The-Fold CTA Implementation",
            "Day 6: LocalBusiness Schema Injection & Structured Data Validation",
            "Day 7: QA Testing, Cross-Browser Review, and Client Live Handoff"
        ]

        packet = {
            "customer_id": cust.id,
            "company_name": cust.company_name,
            "contract_amount": cust.contract_amount,
            "service_package": offer.title if offer else "Website Turnaround",
            "kickoff_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "intake_checklist": intake_checklist,
            "kickoff_agenda": kickoff_agenda,
            "status": "ONBOARDING_PACKET_READY"
        }

        cust.onboarding_status = "ONBOARDING_COMPLETED"
        await session.commit()
        return packet

onboarding_automation = OnboardingAutomation()
