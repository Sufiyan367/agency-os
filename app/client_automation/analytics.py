"""
Agency OS — Client Automation Analytics Engine.

Computes real, uninflated metrics directly from canonical ClientBrain state
and recorded automation events:
- Inquiries received
- Missed calls processed
- Text-backs dispatched
- Leads qualified
- Appointments booked
- Follow-ups queued
- Human escalations triggered
- Automation failures / suppressed calls

Strictly adheres to the zero-fabrication invariant.
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Dict, Any, List

from app.client_automation.brain import shared_brain_manager
from app.client_automation.models import LeadStage, AppointmentStatus, CallType

logger = logging.getLogger("agency.client_automation.analytics")


class ClientAnalyticsEngine:
    """
    Computes deterministic operational and conversion metrics for client automation tenants.
    """

    @classmethod
    def get_client_dashboard_metrics(cls, client_id: str) -> Dict[str, Any]:
        """
        Gathers live metrics strictly from the client's brain data structures.
        """
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            return {
                "client_id": client_id,
                "error": "Client not registered",
                "inquiries": 0,
                "missed_calls": 0,
                "textbacks_dispatched": 0,
                "qualified_leads": 0,
                "appointments_booked": 0,
                "active_appointments": 0,
                "human_escalations": 0,
                "suppressed_calls": 0,
                "followups_pending": 0,
                "conversion_rate_lead_to_booked": 0.0,
            }

        leads = brain.list_leads()
        appointments = brain.list_appointments()
        call_logs = brain.list_call_logs()
        escalations = brain.list_escalations()

        total_inquiries = len(leads)
        missed_calls = sum(1 for c in call_logs if c.call_type == CallType.MISSED)
        textbacks_dispatched = sum(1 for c in call_logs if c.textback_sent)
        suppressed_calls = sum(1 for c in call_logs if "SUPPRESSED" in c.disposition)

        qualified_leads = sum(1 for l in leads if l.stage not in (LeadStage.INQUIRY, LeadStage.LOST) or l.score >= 60.0)
        appointments_booked = len(appointments)
        active_appointments = sum(1 for a in appointments if a.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED))

        followups_pending = sum(1 for l in leads if l.stage == LeadStage.FOLLOWUP_DUE)
        escalations_count = len(escalations)

        # Conversion rate
        conv_rate = (appointments_booked / total_inquiries * 100.0) if total_inquiries > 0 else 0.0

        return {
            "client_id": client_id,
            "business_name": brain.config.business_name,
            "timestamp": datetime.utcnow().isoformat(),
            "inquiries": total_inquiries,
            "missed_calls": missed_calls,
            "textbacks_dispatched": textbacks_dispatched,
            "suppressed_calls": suppressed_calls,
            "qualified_leads": qualified_leads,
            "appointments_booked": appointments_booked,
            "active_appointments": active_appointments,
            "human_escalations": escalations_count,
            "followups_pending": followups_pending,
            "conversion_rate_lead_to_booked": round(conv_rate, 1),
            "telemetry_source": "canonical_client_brain",
        }


client_analytics_engine = ClientAnalyticsEngine()
