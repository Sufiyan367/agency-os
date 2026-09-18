"""
Agency OS — Client Automation Shared Brain.

Acts as the canonical, authoritative store for:
1. Static / business knowledge (services, pricing, hours, policies, FAQs, escalation rules)
2. Live CRM state (leads, conversations, appointments, call logs, escalations)

Enforces strict tenant isolation: zero cross-client bleeding.
Agency OS remains the system of record; n8n and agents observe and act.
"""

from __future__ import annotations
import copy
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from app.client_automation.models import (
    ClientAutomationConfig,
    LeadRecord,
    LeadStage,
    AppointmentRecord,
    CallRecord,
    EscalationEvent,
    FAQItem,
    ServiceItem,
)

logger = logging.getLogger("agency.client_automation.brain")


class TenantIsolationError(Exception):
    """Raised when an operation attempts to violate client isolation boundaries."""
    pass


class ClientBrain:
    """
    In-memory canonical shared brain per client, maintaining isolated
    knowledge graphs, live pipeline state, and audit logs.
    """

    def __init__(self, client_id: str, config: ClientAutomationConfig):
        self.client_id = client_id
        self.config = config
        
        # Knowledge Base: doc_id -> Dict
        self._knowledge_docs: Dict[str, Dict[str, Any]] = {}
        # Seed knowledge from config FAQs and Services
        self._seed_from_config(config)

        # Live State
        self._leads: Dict[str, LeadRecord] = {}
        self._appointments: Dict[str, AppointmentRecord] = {}
        self._call_logs: Dict[str, CallRecord] = {}
        self._escalations: List[EscalationEvent] = []
        self._conversation_history: Dict[str, List[Dict[str, Any]]] = {}  # lead_id -> messages

    def _seed_from_config(self, config: ClientAutomationConfig):
        """Populates initial knowledge base from configuration."""
        for faq in config.faqs:
            self._knowledge_docs[f"faq_{faq.faq_id}"] = {
                "id": faq.faq_id,
                "title": faq.question,
                "content": faq.answer,
                "category": faq.category,
                "keywords": faq.keywords,
                "created_at": datetime.utcnow().isoformat(),
            }
        for srv in config.services:
            self._knowledge_docs[f"srv_{srv.service_id}"] = {
                "id": srv.service_id,
                "title": srv.name,
                "content": f"{srv.name}: {srv.description}. Price: ${srv.price:.2f} ({srv.duration_minutes} mins).",
                "category": "service",
                "keywords": [srv.name.lower(), "pricing", "cost", "duration"],
                "created_at": datetime.utcnow().isoformat(),
            }

    # -------------------------------------------------------------
    # KNOWLEDGE OPERATIONS
    # -------------------------------------------------------------

    def add_knowledge_doc(self, doc_id: str, title: str, content: str, category: str = "custom", keywords: Optional[List[str]] = None):
        self._knowledge_docs[doc_id] = {
            "id": doc_id,
            "title": title,
            "content": content,
            "category": category,
            "keywords": keywords or [],
            "created_at": datetime.utcnow().isoformat(),
        }

    def get_all_knowledge(self) -> List[Dict[str, Any]]:
        return list(self._knowledge_docs.values())

    def search_knowledge(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        query_words = set(query.lower().replace("?", " ").replace("!", " ").replace(".", " ").split())
        scored: List[Dict[str, Any]] = []

        for doc in self._knowledge_docs.values():
            text_to_match = f"{doc['title']} {doc['content']} {' '.join(doc['keywords'])}".lower()
            doc_words = set(text_to_match.split())
            common = query_words.intersection(doc_words)
            if common:
                score = len(common) / max(len(query_words), 1)
                scored.append({
                    "id": doc["id"],
                    "title": doc["title"],
                    "content": doc["content"],
                    "score": round(score, 3),
                    "category": doc["category"],
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    # -------------------------------------------------------------
    # LIVE STATE OPERATIONS (LEADS, APPOINTMENTS, CALLS, CONVERSATIONS)
    # -------------------------------------------------------------

    def upsert_lead(self, lead: LeadRecord) -> LeadRecord:
        if lead.client_id != self.client_id:
            raise TenantIsolationError(f"Cannot save lead for client '{lead.client_id}' into brain '{self.client_id}'")
        lead.updated_at = datetime.utcnow()
        self._leads[lead.lead_id] = lead
        return lead

    def get_lead(self, lead_id: str) -> Optional[LeadRecord]:
        return self._leads.get(lead_id)

    def list_leads(self, stage: Optional[LeadStage] = None) -> List[LeadRecord]:
        if stage:
            return [l for l in self._leads.values() if l.stage == stage]
        return list(self._leads.values())

    def save_appointment(self, app: AppointmentRecord) -> AppointmentRecord:
        if app.client_id != self.client_id:
            raise TenantIsolationError(f"Cannot save appointment for client '{app.client_id}' into brain '{self.client_id}'")
        self._appointments[app.appointment_id] = app
        return app

    def list_appointments(self) -> List[AppointmentRecord]:
        return list(self._appointments.values())

    def save_call_log(self, call: CallRecord) -> CallRecord:
        if call.client_id != self.client_id:
            raise TenantIsolationError(f"Cannot save call log for client '{call.client_id}' into brain '{self.client_id}'")
        self._call_logs[call.call_id] = call
        return call

    def list_call_logs(self) -> List[CallRecord]:
        return list(self._call_logs.values())

    def record_escalation(self, esc: EscalationEvent) -> EscalationEvent:
        if esc.client_id != self.client_id:
            raise TenantIsolationError(f"Cannot record escalation for client '{esc.client_id}' into brain '{self.client_id}'")
        self._escalations.append(esc)
        return esc

    def list_escalations(self) -> List[EscalationEvent]:
        return list(self._escalations)

    def record_message(self, lead_id: str, sender: str, channel: str, text: str) -> Dict[str, Any]:
        if lead_id not in self._conversation_history:
            self._conversation_history[lead_id] = []
        msg = {
            "sender": sender,
            "channel": channel,
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._conversation_history[lead_id].append(msg)
        return msg

    def get_conversation_history(self, lead_id: str) -> List[Dict[str, Any]]:
        return list(self._conversation_history.get(lead_id, []))

    def export_snapshot(self) -> Dict[str, Any]:
        """Provides a safe read-only snapshot for external telemetry / n8n observation."""
        return {
            "client_id": self.client_id,
            "business_name": self.config.business_name,
            "active_leads_count": len(self._leads),
            "appointments_count": len(self._appointments),
            "call_logs_count": len(self._call_logs),
            "escalations_count": len(self._escalations),
            "knowledge_docs_count": len(self._knowledge_docs),
            "snapshot_timestamp": datetime.utcnow().isoformat(),
        }


class SharedBrainManager:
    """
    Singleton registry managing all isolated ClientBrain instances.
    Enforces strict client multi-tenancy.
    """

    def __init__(self):
        self._brains: Dict[str, ClientBrain] = {}

    def register_client(self, config: ClientAutomationConfig) -> ClientBrain:
        brain = ClientBrain(client_id=config.client_id, config=config)
        self._brains[config.client_id] = brain
        logger.info(f"[SharedBrainManager] Registered client '{config.client_id}' ({config.business_name}).")
        return brain

    def get_brain(self, client_id: str) -> Optional[ClientBrain]:
        return self._brains.get(client_id)

    def get_or_create_brain(self, config: ClientAutomationConfig) -> ClientBrain:
        if config.client_id in self._brains:
            return self._brains[config.client_id]
        return self.register_client(config)

    def list_clients(self) -> List[str]:
        return list(self._brains.keys())

    def clear(self):
        """Clears registry (used in test isolation)."""
        self._brains.clear()


# Global manager singleton
shared_brain_manager = SharedBrainManager()
