"""
Agency OS — Delivery Efficiency Tracker.
Tracks and optimizes execution across the software engineering pipeline:
- Requirements count & component reuse
- Workflow template utilization
- Implementation and deployment duration
- QA failures, fix attempts, and recovery rates
- Identifies reusable delivery patterns across niche clusters
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class DeliveryCycleMetric(BaseModel):
    project_id: str
    niche: str
    workflow_template: str
    components_used: List[str]
    implementation_duration_seconds: int
    qa_passed_first_try: bool
    qa_repair_attempts: int
    deployment_duration_seconds: int
    is_pattern_reusable: bool = True
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class DeliveryEfficiencyTracker:
    """
    Maintains telemetry on delivery velocity and identifies reusable workflow patterns.
    """

    _delivery_log: List[DeliveryCycleMetric] = []

    # Reusable delivery blueprints across primary niches
    REUSABLE_PATTERNS = {
        "HVAC": {
            "template": "hvac_emergency_intake_v1",
            "reusable_components": ["IntakeForm", "EmergencyTriageNode", "TwilioSMSDispatcher", "CalendarSync"],
            "avg_implementation_minutes": 12
        },
        "Dental": {
            "template": "dental_patient_triage_v1",
            "reusable_components": ["PatientIntakeStepper", "SlotReservationNode", "HIPAALogScrubber"],
            "avg_implementation_minutes": 15
        },
        "Roofing": {
            "template": "roofing_inspection_flow_v1",
            "reusable_components": ["DamageAssessmentStep", "PhotoUploadNode", "EstimatorDispatch"],
            "avg_implementation_minutes": 10
        },
        "Automotive": {
            "template": "auto_repair_booking_v1",
            "reusable_components": ["VehicleIntakeNode", "ServiceAdvisorQueue", "InstantSMSConfirm"],
            "avg_implementation_minutes": 8
        }
    }

    @classmethod
    def record_delivery_cycle(cls, metric: DeliveryCycleMetric) -> None:
        cls._delivery_log.append(metric)

    @classmethod
    def get_efficiency_summary(cls) -> Dict[str, Any]:
        """
        Aggregates delivery cycle metrics across all completed projects.
        """
        n = len(cls._delivery_log)
        if n == 0:
            return {
                "total_completed_projects": 0,
                "first_try_qa_pass_rate": "NOT ENOUGH DATA",
                "avg_implementation_seconds": 0,
                "reusable_patterns_catalog": cls.REUSABLE_PATTERNS
            }

        first_try_passes = sum(1 for m in cls._delivery_log if m.qa_passed_first_try)
        avg_impl = sum(m.implementation_duration_seconds for m in cls._delivery_log) / n

        return {
            "total_completed_projects": n,
            "first_try_qa_pass_rate": round((first_try_passes / n) * 100, 1),
            "avg_implementation_seconds": round(avg_impl, 1),
            "reusable_patterns_catalog": cls.REUSABLE_PATTERNS
        }


delivery_efficiency_tracker = DeliveryEfficiencyTracker()
