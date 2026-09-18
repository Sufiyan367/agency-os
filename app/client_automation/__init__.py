"""
Agency OS — Client Automation Foundation Package.

Provides isolated, configurable multi-tenant client automation modules:
- Configuration profiles & tenancy isolation
- Canonical Shared Brain
- Pluggable provider contracts (Null/Mock/Local/Cal.com/HubSpot)
- Missed-call text-back automation
- Grounded FAQ & Knowledge retrieval
- Rule-based client lead qualification
- CRM lifecycle state machine
- Supervised client orchestrator
- Deterministic analytics
"""

from app.client_automation.models import (
    ClientAutomationConfig,
    BusinessHours,
    ServiceItem,
    FAQItem,
    BookingRules,
    CancellationPolicy,
    EscalationRules,
    QualificationRule,
    LeadRecord,
    LeadStage,
    AppointmentRecord,
    AppointmentStatus,
    CallRecord,
    CallType,
    EscalationEvent,
    EscalationReason,
    AutomationModule,
)
from app.client_automation.brain import (
    ClientBrain,
    SharedBrainManager,
    shared_brain_manager,
    TenantIsolationError,
)
from app.client_automation.interfaces import (
    CallAnsweringProvider,
    NullCallAnsweringProvider,
    MockCallAnsweringProvider,
    MissedCallProvider,
    NullMissedCallProvider,
    MockMissedCallProvider,
    KnowledgeProvider,
    LocalKnowledgeProvider,
    CalendarProvider,
    LocalCalendarProvider,
    CalComAdapter,
    CRMProvider,
    LocalCRMProvider,
    HubSpotAdapter,
    NotificationProvider,
    LocalNotificationProvider,
    AnalyticsProvider,
    LocalAnalyticsProvider,
)
from app.client_automation.missed_call import (
    MissedCallAutomationService,
    missed_call_automation,
)
from app.client_automation.appointments import (
    AppointmentAutomationService,
    appointment_automation,
)
from app.client_automation.knowledge import (
    KnowledgeEngine,
    knowledge_engine,
)
from app.client_automation.qualification import (
    ClientLeadQualifier,
    client_lead_qualifier,
    QualificationResult,
)
from app.client_automation.crm import (
    ClientCRMStateMachine,
    client_crm_state_machine,
    InvalidStageTransitionError,
)
from app.client_automation.orchestrator import (
    SupervisedClientOrchestrator,
    supervised_client_orchestrator,
)
from app.client_automation.analytics import (
    ClientAnalyticsEngine,
    client_analytics_engine,
)

__all__ = [
    "ClientAutomationConfig",
    "BusinessHours",
    "ServiceItem",
    "FAQItem",
    "BookingRules",
    "CancellationPolicy",
    "EscalationRules",
    "QualificationRule",
    "LeadRecord",
    "LeadStage",
    "AppointmentRecord",
    "AppointmentStatus",
    "CallRecord",
    "CallType",
    "EscalationEvent",
    "EscalationReason",
    "AutomationModule",
    "ClientBrain",
    "SharedBrainManager",
    "shared_brain_manager",
    "TenantIsolationError",
    "CallAnsweringProvider",
    "NullCallAnsweringProvider",
    "MockCallAnsweringProvider",
    "MissedCallProvider",
    "NullMissedCallProvider",
    "MockMissedCallProvider",
    "KnowledgeProvider",
    "LocalKnowledgeProvider",
    "CalendarProvider",
    "LocalCalendarProvider",
    "CalComAdapter",
    "CRMProvider",
    "LocalCRMProvider",
    "HubSpotAdapter",
    "NotificationProvider",
    "LocalNotificationProvider",
    "AnalyticsProvider",
    "LocalAnalyticsProvider",
    "MissedCallAutomationService",
    "missed_call_automation",
    "AppointmentAutomationService",
    "appointment_automation",
    "KnowledgeEngine",
    "knowledge_engine",
    "ClientLeadQualifier",
    "client_lead_qualifier",
    "QualificationResult",
    "ClientCRMStateMachine",
    "client_crm_state_machine",
    "InvalidStageTransitionError",
    "SupervisedClientOrchestrator",
    "supervised_client_orchestrator",
    "ClientAnalyticsEngine",
    "client_analytics_engine",
]
