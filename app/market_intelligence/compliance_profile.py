from typing import Dict, Any
from app.market_intelligence.models import ComplianceRisk

class ComplianceProfileManager:
    """Evaluates data privacy, regulatory scrutiny, and outbound risk per country/niche."""

    COUNTRY_RISK_MAP = {
        "US": (ComplianceRisk.LOW, "CAN-SPAM allows commercial B2B outreach with opt-out mechanism."),
        "UK": (ComplianceRisk.LOW, "PECR B2B exemption allows relevant business email outreach with opt-out."),
        "AE": (ComplianceRisk.LOW, "UAE commercial regulations permit business inquiries with clear opt-out."),
        "SA": (ComplianceRisk.MEDIUM, "Saudi PDPL requires adherence to commercial electronic communication rules."),
        "SG": (ComplianceRisk.LOW, "Spam Control Act allows verified commercial business contact."),
        "AU": (ComplianceRisk.LOW, "Spam Act 2003 permits designated commercial B2B messages with identification."),
        "CA": (ComplianceRisk.LOW, "CASL permits B2B inquiries relevant to recipient's business/role."),
        "NZ": (ComplianceRisk.LOW, "Unsolicited Electronic Messages Act permits relevant commercial B2B contact."),
        "DE": (ComplianceRisk.MEDIUM, "UWG and BDSG require strict business relevance; opt-out mandatory."),
        "FR": (ComplianceRisk.MEDIUM, "CNIL B2B guidelines permit relevant role-based email with opt-out."),
        "NL": (ComplianceRisk.LOW, "Dutch Telecommunications Act allows targeted B2B contact."),
        "JP": (ComplianceRisk.MEDIUM, "Act on Specified Commercial Transactions requires accurate identification."),
        "KR": (ComplianceRisk.MEDIUM, "KISA guidelines require explicit commercial email labeling."),
        "CN": (ComplianceRisk.HIGH, "Cross-border data security laws mandate local compliance infrastructure."),
    }

    NICHE_RISK_MAP = {
        "medical-clinics": 0.15,
        "dental": 0.10,
        "legal-services": 0.10,
        "accounting": 0.10,
        "insurance": 0.10,
    }

    def assess_risk(self, country_code: str, niche_slug: str) -> Dict[str, Any]:
        c = country_code.upper()
        if c in self.COUNTRY_RISK_MAP:
            base_risk, note = self.COUNTRY_RISK_MAP[c]
        else:
            base_risk = ComplianceRisk.UNKNOWN
            note = "Unverified jurisdiction. Strict conservative risk handling applied."

        penalty = 0.05 if base_risk == ComplianceRisk.LOW else (0.15 if base_risk == ComplianceRisk.MEDIUM else 0.30)
        niche_extra = self.NICHE_RISK_MAP.get(niche_slug, 0.0)

        total_penalty = min(0.40, penalty + niche_extra)

        return {
            "compliance_risk": base_risk.value,
            "compliance_note": note,
            "compliance_penalty": round(total_penalty, 3),
            "requires_human_approval": base_risk in (ComplianceRisk.HIGH, ComplianceRisk.UNKNOWN) or total_penalty > 0.20
        }

compliance_profile_manager = ComplianceProfileManager()
