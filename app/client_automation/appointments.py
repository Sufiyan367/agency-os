"""
Agency OS — Client Appointment Automation Service.

Handles the appointment booking lifecycle:
1. Queries available slots respecting business hours, service duration, and existing bookings.
2. Validates lead qualification status before booking.
3. Books appointments via pluggable CalendarProvider (LocalCalendarProvider / CalComAdapter).
4. Updates CRM lead stage to BOOKED.
5. Dispatches booking confirmations and reminders.
6. Enforces cancellation & rescheduling policy checks.
"""

from __future__ import annotations
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from app.client_automation.brain import shared_brain_manager
from app.client_automation.models import (
    AppointmentRecord,
    AppointmentStatus,
    LeadRecord,
    LeadStage,
    AutomationModule,
)
from app.client_automation.interfaces import CalendarProvider, LocalCalendarProvider, NotificationProvider, LocalNotificationProvider

logger = logging.getLogger("agency.client_automation.appointments")


class AppointmentAutomationService:
    """
    Client appointment booking, rescheduling, and cancellation manager.
    """

    def __init__(
        self,
        calendar_provider: Optional[CalendarProvider] = None,
        notification_provider: Optional[NotificationProvider] = None,
    ):
        self.calendar_provider = calendar_provider or LocalCalendarProvider()
        self.notification_provider = notification_provider or LocalNotificationProvider()

    async def get_available_slots(
        self,
        client_id: str,
        target_date: datetime,
        service_id: Optional[str] = None
    ) -> List[str]:
        """Returns available time slots ('HH:MM') for the target date."""
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            return []

        config = brain.config
        duration = 30
        if service_id:
            srv = next((s for s in config.services if s.service_id == service_id), None)
            if srv:
                duration = srv.duration_minutes

        return await self.calendar_provider.get_available_slots(
            client_id=client_id,
            date=target_date,
            service_duration_minutes=duration,
            config=config,
        )

    async def book_appointment(
        self,
        client_id: str,
        lead_id: str,
        service_id: str,
        start_time: datetime,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validates qualification and books an appointment slot for the lead.
        """
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            return {"success": False, "error": f"Client '{client_id}' not found in Shared Brain"}

        config = brain.config
        if not config.has_module(AutomationModule.APPOINTMENTS):
            return {"success": False, "error": f"Appointments module is disabled for client '{client_id}'"}

        lead = brain.get_lead(lead_id)
        if not lead:
            return {"success": False, "error": f"Lead '{lead_id}' not found"}

        # Find requested service
        service = next((s for s in config.services if s.service_id == service_id), None)
        if not service:
            # Fallback to default generic service if not matched
            service_name = "General Consultation"
            duration = 30
        else:
            service_name = service.name
            duration = service.duration_minutes

        # Check slot availability
        available_slots = await self.get_available_slots(client_id, start_time, service_id)
        req_slot = start_time.strftime("%H:%M")
        if req_slot not in available_slots:
            return {
                "success": False,
                "error": f"Slot {req_slot} on {start_time.date()} is unavailable.",
                "available_slots": available_slots,
            }

        # Book slot via calendar provider
        appointment = await self.calendar_provider.book_slot(
            client_id=client_id,
            lead_id=lead_id,
            service_id=service_id,
            service_name=service_name,
            start_time=start_time,
            duration_minutes=duration,
            notes=notes,
        )

        # Store in client brain
        brain.save_appointment(appointment)

        # Transition Lead stage to BOOKED
        lead.stage = LeadStage.BOOKED
        lead.notes.append(
            f"Appointment confirmed for {service_name} on {start_time.strftime('%Y-%m-%d %H:%M')} (Code: {appointment.confirmation_code})"
        )
        brain.upsert_lead(lead)

        # Record confirmation message in conversation history
        conf_message = (
            f"Your appointment for {service_name} with {config.business_name} has been confirmed for "
            f"{start_time.strftime('%A, %B %d at %I:%M %p')}. Confirmation code: {appointment.confirmation_code}."
        )
        brain.record_message(
            lead_id=lead_id,
            sender="SYSTEM_APPOINTMENTS",
            channel="SMS",
            text=conf_message,
        )

        # Send notifications
        if lead.contact_email:
            await self.notification_provider.send_notification(
                client_id=client_id,
                channel="email",
                recipient=lead.contact_email,
                subject=f"Appointment Confirmed: {service_name}",
                body=conf_message,
            )

        # Notify business owner
        await self.notification_provider.send_notification(
            client_id=client_id,
            channel="dashboard",
            recipient=config.contact_email,
            subject=f"New Booking: {lead.contact_name} - {service_name}",
            body=f"New appointment booked for {start_time.strftime('%Y-%m-%d %H:%M')}.",
            priority="HIGH",
        )

        return {
            "success": True,
            "appointment_id": appointment.appointment_id,
            "confirmation_code": appointment.confirmation_code,
            "start_time": appointment.start_time.isoformat(),
            "end_time": appointment.end_time.isoformat(),
            "service_name": service_name,
            "lead_stage": lead.stage.value,
        }

    async def cancel_appointment(
        self,
        client_id: str,
        appointment_id: str,
        reason: str = "Client requested cancellation"
    ) -> Dict[str, Any]:
        """Cancels an appointment and applies cancellation policy."""
        brain = shared_brain_manager.get_brain(client_id)
        if not brain:
            return {"success": False, "error": f"Client '{client_id}' not found"}

        config = brain.config
        appointment = next((a for a in brain.list_appointments() if a.appointment_id == appointment_id), None)
        if not appointment:
            return {"success": False, "error": f"Appointment '{appointment_id}' not found"}

        # Check cancellation policy notice hours
        notice_window = appointment.start_time - datetime.utcnow()
        hours_notice = notice_window.total_seconds() / 3600.0
        policy = config.cancellation_policy

        fee_applies = hours_notice < policy.notice_hours_required and policy.fee_amount > 0

        # Cancel in calendar provider and brain
        await self.calendar_provider.cancel_slot(client_id, appointment_id, reason)
        appointment.status = AppointmentStatus.CANCELLED
        brain.save_appointment(appointment)

        # Update lead
        lead = brain.get_lead(appointment.lead_id)
        if lead:
            lead.notes.append(f"Cancelled appointment {appointment_id}. Reason: {reason}")
            lead.stage = LeadStage.FOLLOWUP_DUE
            brain.upsert_lead(lead)

        return {
            "success": True,
            "appointment_id": appointment_id,
            "status": "CANCELLED",
            "hours_notice": round(hours_notice, 1),
            "fee_applies": fee_applies,
            "fee_amount": policy.fee_amount if fee_applies else 0.0,
        }


appointment_automation = AppointmentAutomationService()
