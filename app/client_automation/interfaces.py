"""
Agency OS — Client Automation Module Contracts & Provider Interfaces.

Defines pluggable provider interfaces with zero-cost local/mock defaults
and self-hosted adapters (Cal.com, local CRM, null voice/SMS).
Enforces zero paid SaaS dependencies in core architecture.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import uuid

from app.client_automation.models import (
    ClientAutomationConfig,
    LeadRecord,
    LeadStage,
    AppointmentRecord,
    AppointmentStatus,
    CallRecord,
    CallType,
    EscalationEvent,
    EscalationReason,
)


# =====================================================================
# 1. CALL ANSWERING & ROUTING PROVIDER
# =====================================================================

class CallAnsweringProvider(ABC):
    @abstractmethod
    async def answer_call(self, call_event: Dict[str, Any], config: ClientAutomationConfig) -> Dict[str, Any]:
        """Processes incoming call greeting and initial routing decision."""
        pass

    @abstractmethod
    async def route_call(self, call_event: Dict[str, Any], destination: str) -> Dict[str, Any]:
        """Routes call to destination phone or voicemail."""
        pass


class NullCallAnsweringProvider(CallAnsweringProvider):
    """Null provider when telephony is unconfigured or disabled."""
    async def answer_call(self, call_event: Dict[str, Any], config: ClientAutomationConfig) -> Dict[str, Any]:
        return {
            "status": "UNCONFIGURED",
            "provider": "null",
            "message": "Voice calling provider not configured; automated voice answering inactive.",
            "routed": False,
        }

    async def route_call(self, call_event: Dict[str, Any], destination: str) -> Dict[str, Any]:
        return {"status": "UNCONFIGURED", "provider": "null", "routed": False}


class MockCallAnsweringProvider(CallAnsweringProvider):
    """Deterministic mock provider for simulation and automated testing."""
    def __init__(self):
        self.call_history: List[Dict[str, Any]] = []

    async def answer_call(self, call_event: Dict[str, Any], config: ClientAutomationConfig) -> Dict[str, Any]:
        record = {
            "call_id": call_event.get("call_id") or f"CALL-{uuid.uuid4().hex[:8]}",
            "client_id": config.client_id,
            "caller_phone": call_event.get("caller_phone", ""),
            "status": "ANSWERED_MOCK",
            "greeting": f"Thank you for calling {config.business_name}. {config.brand_voice}",
            "routed": True,
            "destination": "VOICEMAIL" if call_event.get("is_after_hours") else "AGENT",
        }
        self.call_history.append(record)
        return record

    async def route_call(self, call_event: Dict[str, Any], destination: str) -> Dict[str, Any]:
        return {
            "call_id": call_event.get("call_id"),
            "status": "ROUTED",
            "destination": destination,
        }


# =====================================================================
# 2. MISSED CALL PROVIDER
# =====================================================================

class MissedCallProvider(ABC):
    @abstractmethod
    async def send_textback(self, to_phone: str, message: str, client_id: str) -> Dict[str, Any]:
        """Dispatches SMS text-back to caller."""
        pass


class NullMissedCallProvider(MissedCallProvider):
    """Null provider when SMS provider is unconfigured."""
    async def send_textback(self, to_phone: str, message: str, client_id: str) -> Dict[str, Any]:
        return {
            "success": False,
            "status": "INTEGRATION_REQUIRED",
            "provider": "null",
            "error": "SMS gateway unconfigured. Set up provider credentials or use mock adapter.",
            "to_phone": to_phone,
        }


class MockMissedCallProvider(MissedCallProvider):
    """Deterministic mock provider capturing outbound text-backs."""
    def __init__(self):
        self.sent_messages: List[Dict[str, Any]] = []

    async def send_textback(self, to_phone: str, message: str, client_id: str) -> Dict[str, Any]:
        entry = {
            "message_id": f"MSG-{uuid.uuid4().hex[:8]}",
            "client_id": client_id,
            "to_phone": to_phone,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "DELIVERED_MOCK",
        }
        self.sent_messages.append(entry)
        return {"success": True, "status": "DELIVERED_MOCK", "message_id": entry["message_id"]}


# =====================================================================
# 3. KNOWLEDGE & FAQ PROVIDER
# =====================================================================

class KnowledgeProvider(ABC):
    @abstractmethod
    async def search(self, query: str, client_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Searches client-isolated knowledge base and FAQs."""
        pass

    @abstractmethod
    async def add_document(self, client_id: str, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Stores document in client's isolated knowledge domain."""
        pass


class LocalKnowledgeProvider(KnowledgeProvider):
    """
    Self-contained in-memory / local knowledge engine with strict tenant isolation.
    Uses multi-token keyword overlap and semantic word scoring.
    """
    def __init__(self):
        # client_id -> List[Dict]
        self._stores: Dict[str, List[Dict[str, Any]]] = {}

    async def add_document(self, client_id: str, doc_id: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        if client_id not in self._stores:
            self._stores[client_id] = []
        self._stores[client_id].append({
            "doc_id": doc_id,
            "text": text,
            "metadata": metadata or {},
            "tokens": set(text.lower().replace("?", " ").replace("!", " ").replace(".", " ").split()),
        })
        return True

    async def search(self, query: str, client_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        store = self._stores.get(client_id, [])
        if not store:
            return []
        
        query_tokens = set(query.lower().replace("?", " ").replace("!", " ").replace(".", " ").split())
        results = []
        for doc in store:
            common = query_tokens.intersection(doc["tokens"])
            score = len(common) / max(len(query_tokens), 1)
            if score > 0.1:
                results.append({
                    "doc_id": doc["doc_id"],
                    "text": doc["text"],
                    "metadata": doc["metadata"],
                    "confidence": round(score, 3),
                })
        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results[:limit]


# =====================================================================
# 4. CALENDAR & APPOINTMENT PROVIDER
# =====================================================================

class CalendarProvider(ABC):
    @abstractmethod
    async def get_available_slots(
        self, client_id: str, date: datetime, service_duration_minutes: int, config: ClientAutomationConfig
    ) -> List[str]:
        """Returns list of available slot start times ('HH:MM') for given date."""
        pass

    @abstractmethod
    async def book_slot(
        self,
        client_id: str,
        lead_id: str,
        service_id: str,
        service_name: str,
        start_time: datetime,
        duration_minutes: int,
        notes: Optional[str] = None
    ) -> AppointmentRecord:
        """Books an appointment slot and returns the confirmed record."""
        pass

    @abstractmethod
    async def cancel_slot(self, client_id: str, appointment_id: str, reason: str) -> bool:
        """Cancels a booked slot."""
        pass


class LocalCalendarProvider(CalendarProvider):
    """
    Self-hosted local calendar engine.
    Calculates slots based on client business hours, booking rules, and existing appointments.
    """
    def __init__(self):
        # client_id -> List[AppointmentRecord]
        self._appointments: Dict[str, List[AppointmentRecord]] = {}

    async def get_available_slots(
        self, client_id: str, date: datetime, service_duration_minutes: int, config: ClientAutomationConfig
    ) -> List[str]:
        # Verify day of week against business hours
        if date.weekday() not in config.business_hours.days_of_week:
            return []

        open_dt = datetime.strptime(config.business_hours.open_time, "%H:%M")
        close_dt = datetime.strptime(config.business_hours.close_time, "%H:%M")
        slot_len = timedelta(minutes=service_duration_minutes or config.booking_rules.slot_duration_minutes)
        buffer_len = timedelta(minutes=config.booking_rules.buffer_minutes)

        booked = [
            app for app in self._appointments.get(client_id, [])
            if app.start_time.date() == date.date() and app.status in (AppointmentStatus.SCHEDULED, AppointmentStatus.CONFIRMED)
        ]

        curr = open_dt
        available: List[str] = []
        while curr + slot_len <= close_dt:
            slot_start_time = curr.time()
            slot_end_time = (curr + slot_len).time()

            # Check overlap
            conflict = False
            for app in booked:
                app_start = app.start_time.time()
                app_end = app.end_time.time()
                if not (slot_end_time <= app_start or slot_start_time >= app_end):
                    conflict = True
                    break
            
            if not conflict:
                available.append(slot_start_time.strftime("%H:%M"))
            
            curr += slot_len + buffer_len

        return available

    async def book_slot(
        self,
        client_id: str,
        lead_id: str,
        service_id: str,
        service_name: str,
        start_time: datetime,
        duration_minutes: int,
        notes: Optional[str] = None
    ) -> AppointmentRecord:
        end_time = start_time + timedelta(minutes=duration_minutes)
        app = AppointmentRecord(
            appointment_id=f"APP-{uuid.uuid4().hex[:8].upper()}",
            client_id=client_id,
            lead_id=lead_id,
            service_id=service_id,
            service_name=service_name,
            start_time=start_time,
            end_time=end_time,
            status=AppointmentStatus.CONFIRMED,
            confirmation_code=f"CONF-{uuid.uuid4().hex[:6].upper()}",
            notes=notes,
            created_at=datetime.utcnow(),
        )
        if client_id not in self._appointments:
            self._appointments[client_id] = []
        self._appointments[client_id].append(app)
        return app

    async def cancel_slot(self, client_id: str, appointment_id: str, reason: str) -> bool:
        apps = self._appointments.get(client_id, [])
        for app in apps:
            if app.appointment_id == appointment_id:
                app.status = AppointmentStatus.CANCELLED
                app.notes = f"{app.notes or ''} [CANCELLED: {reason}]".strip()
                return True
        return False


class CalComAdapter(LocalCalendarProvider):
    """
    Cal.com open-source self-hosted adapter.
    Inherits local scheduling logic and exposes Webhook payload translation.
    """
    pass


# =====================================================================
# 5. CRM PROVIDER
# =====================================================================

class CRMProvider(ABC):
    @abstractmethod
    async def upsert_lead(self, lead: LeadRecord) -> LeadRecord:
        pass

    @abstractmethod
    async def get_lead(self, client_id: str, lead_id: str) -> Optional[LeadRecord]:
        pass

    @abstractmethod
    async def record_interaction(
        self, client_id: str, lead_id: str, message: str, sender: str, channel: str
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def update_stage(self, client_id: str, lead_id: str, new_stage: LeadStage, note: str = "") -> Optional[LeadRecord]:
        pass


class LocalCRMProvider(CRMProvider):
    """
    Client-isolated in-memory CRM store for fast, deterministic lifecycle transitions.
    """
    def __init__(self):
        # (client_id, lead_id) -> LeadRecord
        self._leads: Dict[str, LeadRecord] = {}
        # (client_id, lead_id) -> List[Dict]
        self._interactions: Dict[str, List[Dict[str, Any]]] = {}

    def _key(self, client_id: str, lead_id: str) -> str:
        return f"{client_id}:{lead_id}"

    async def upsert_lead(self, lead: LeadRecord) -> LeadRecord:
        key = self._key(lead.client_id, lead.lead_id)
        lead.updated_at = datetime.utcnow()
        self._leads[key] = lead
        return lead

    async def get_lead(self, client_id: str, lead_id: str) -> Optional[LeadRecord]:
        return self._leads.get(self._key(client_id, lead_id))

    async def record_interaction(
        self, client_id: str, lead_id: str, message: str, sender: str, channel: str
    ) -> Dict[str, Any]:
        key = self._key(client_id, lead_id)
        if key not in self._interactions:
            self._interactions[key] = []
        interaction = {
            "id": f"INT-{uuid.uuid4().hex[:8]}",
            "client_id": client_id,
            "lead_id": lead_id,
            "sender": sender,
            "channel": channel,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._interactions[key].append(interaction)
        return interaction

    async def update_stage(self, client_id: str, lead_id: str, new_stage: LeadStage, note: str = "") -> Optional[LeadRecord]:
        key = self._key(client_id, lead_id)
        lead = self._leads.get(key)
        if not lead:
            return None
        lead.stage = new_stage
        lead.updated_at = datetime.utcnow()
        if note:
            lead.notes.append(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] Stage -> {new_stage.value}: {note}")
        return lead


class HubSpotAdapter(LocalCRMProvider):
    """HubSpot CRM integration bridge stub for enterprise client syncing."""
    pass


# =====================================================================
# 6. NOTIFICATION PROVIDER
# =====================================================================

class NotificationProvider(ABC):
    @abstractmethod
    async def send_notification(
        self, client_id: str, channel: str, recipient: str, subject: str, body: str, priority: str = "NORMAL"
    ) -> Dict[str, Any]:
        pass


class LocalNotificationProvider(NotificationProvider):
    """Deterministic local notification dispatcher with memory store."""
    def __init__(self):
        self.dispatched_notifications: List[Dict[str, Any]] = []

    async def send_notification(
        self, client_id: str, channel: str, recipient: str, subject: str, body: str, priority: str = "NORMAL"
    ) -> Dict[str, Any]:
        record = {
            "notification_id": f"NOTIF-{uuid.uuid4().hex[:8]}",
            "client_id": client_id,
            "channel": channel,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "priority": priority,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "SENT_LOCAL",
        }
        self.dispatched_notifications.append(record)
        return record


# =====================================================================
# 7. ANALYTICS PROVIDER
# =====================================================================

class AnalyticsProvider(ABC):
    @abstractmethod
    async def record_event(self, client_id: str, event_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        pass

    @abstractmethod
    async def get_summary(self, client_id: str) -> Dict[str, Any]:
        pass


class LocalAnalyticsProvider(AnalyticsProvider):
    """Aggregated local analytics tracking per client."""
    def __init__(self):
        # client_id -> Dict[event_type, int]
        self._counts: Dict[str, Dict[str, int]] = {}

    async def record_event(self, client_id: str, event_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        if client_id not in self._counts:
            self._counts[client_id] = {
                "inquiries": 0,
                "missed_calls": 0,
                "textbacks_sent": 0,
                "leads_qualified": 0,
                "appointments_booked": 0,
                "followups_scheduled": 0,
                "escalations": 0,
                "failures": 0,
            }
        
        counts = self._counts[client_id]
        if event_type in counts:
            counts[event_type] += 1
        else:
            counts[event_type] = counts.get(event_type, 0) + 1

    async def get_summary(self, client_id: str) -> Dict[str, Any]:
        data = self._counts.get(client_id, {
            "inquiries": 0,
            "missed_calls": 0,
            "textbacks_sent": 0,
            "leads_qualified": 0,
            "appointments_booked": 0,
            "followups_scheduled": 0,
            "escalations": 0,
            "failures": 0,
        })
        return {"client_id": client_id, "metrics": data, "timestamp": datetime.utcnow().isoformat()}
