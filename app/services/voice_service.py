"""
Voice Sales Service.
Coordinates outbound voice execution, status tracking, transcript qualification,
meeting scheduling, and CRM audit event persistence.
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.config import settings
from app.database.connection import AsyncSessionLocal
from app.database.models import CallLog, Meeting, Business, PipelineStage
from app.communications.voice_provider import get_active_voice_provider, format_e164_phone
from app.agents.voice_sales_agent import VoiceSalesAgent, VoiceQualificationResult

logger = logging.getLogger(__name__)


class VoiceSalesService:
    """Service managing autonomous voice sales operations."""

    @classmethod
    async def initiate_outbound_call(
        cls,
        prospect_phone: str,
        business_name: str,
        niche: str = "Commercial Services",
        city: str = "Austin",
        business_id: Optional[int] = None,
        audit_data: Optional[Dict[str, Any]] = None,
        language: str = "en",
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Places an outbound voice sales call using the active provider."""
        audit_evidence = audit_data or {"performance_score": 48.0, "load_time_seconds": 4.3}
        script = VoiceSalesAgent.generate_call_script(
            business_name=business_name,
            niche=niche,
            city=city,
            audit_evidence=audit_evidence,
            language=language
        )

        provider = get_active_voice_provider()
        call_res = await provider.place_call(
            phone=prospect_phone,
            script_context=script,
            language=language
        )

        # Persist CallLog in database
        async def _save_record(session: AsyncSession):
            call_log = CallLog(
                business_id=business_id,
                call_sid=call_res.call_id,
                caller_id=call_res.caller_id,
                recipient_phone=call_res.recipient_phone,
                direction="OUTBOUND",
                status=call_res.status,
                duration_seconds=call_res.duration_seconds,
                recording_url=call_res.recording_url,
                recording_consent_disclosed=True,
                transcript=call_res.transcript,
                language=language,
                qualification_intent="INITIAL_PITCH",
                action_taken="CALL_DISPATCHED",
                created_at=datetime.utcnow()
            )
            session.add(call_log)
            await session.commit()
            await session.refresh(call_log)
            return call_log

        if db:
            log_entry = await _save_record(db)
        else:
            async with AsyncSessionLocal() as session:
                log_entry = await _save_record(session)

        # If dry-run, immediately evaluate the simulated transcript
        if call_res.dry_run and call_res.transcript:
            await cls.process_call_transcript(
                call_sid=call_res.call_id,
                transcript=call_res.transcript,
                duration=call_res.duration_seconds,
                recording_url=call_res.recording_url
            )

        return {
            "success": call_res.success,
            "call_sid": call_res.call_id,
            "status": call_res.status,
            "provider": call_res.provider,
            "recipient_phone": call_res.recipient_phone,
            "dry_run": call_res.dry_run
        }

    @classmethod
    async def process_call_transcript(
        cls,
        call_sid: str,
        transcript: str,
        duration: int = 0,
        recording_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Processes prospect speech from call recording transcript, handling qualification and booking."""
        async with AsyncSessionLocal() as db:
            q = select(CallLog).where(CallLog.call_sid == call_sid)
            res = await db.execute(q)
            call_log = res.scalar_one_or_none()

            if not call_log:
                logger.warning(f"No call log found for call_sid: {call_sid}")
                return {"status": "NOT_FOUND"}

            # Analyze transcript
            audit_evidence = {"performance_score": 50.0}
            qual = VoiceSalesAgent.process_prospect_speech(
                prospect_utterance=transcript,
                audit_evidence=audit_evidence,
                language=call_log.language
            )

            # Update call log
            call_log.transcript = transcript
            call_log.duration_seconds = duration or call_log.duration_seconds
            if recording_url:
                call_log.recording_url = recording_url
            call_log.qualification_intent = qual.intent
            call_log.action_taken = qual.recommended_action
            call_log.completed_at = datetime.utcnow()
            call_log.status = "COMPLETED"

            # If appointment booked
            meeting_id = None
            if qual.intent == "BOOK_MEETING":
                sched_time = qual.proposed_meeting_time or (datetime.utcnow() + timedelta(days=2))
                meeting = Meeting(
                    business_id=call_log.business_id,
                    prospect_name=f"Lead ({call_log.recipient_phone})",
                    prospect_contact=call_log.recipient_phone,
                    title="Diagnostic Walkthrough Consultation",
                    scheduled_time=sched_time,
                    duration_minutes=15,
                    meeting_url="https://meet.agencygrowth.co/diagnostic-consultation",
                    status="SCHEDULED",
                    notes=f"Autonomous voice sales booking from call {call_sid}."
                )
                db.add(meeting)

                # Update business pipeline stage if linked
                if call_log.business_id:
                    q_biz = select(Business).where(Business.id == call_log.business_id)
                    b_res = await db.execute(q_biz)
                    biz = b_res.scalar_one_or_none()
                    if biz:
                        biz.pipeline_stage = PipelineStage.MEETING.value

            elif qual.escalate_to_human:
                if call_log.business_id:
                    q_biz = select(Business).where(Business.id == call_log.business_id)
                    b_res = await db.execute(q_biz)
                    biz = b_res.scalar_one_or_none()
                    if biz:
                        biz.pipeline_stage = "HUMAN_TAKEOVER"

            await db.commit()

            return {
                "call_sid": call_sid,
                "intent": qual.intent,
                "action_taken": qual.recommended_action,
                "meeting_booked": qual.intent == "BOOK_MEETING",
                "escalated": qual.escalate_to_human
            }

    @classmethod
    async def get_call_logs(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent voice calls for the dashboard."""
        async with AsyncSessionLocal() as db:
            q = select(CallLog).order_by(desc(CallLog.created_at)).limit(limit)
            logs = (await db.execute(q)).scalars().all()
            return [{
                "id": l.id,
                "call_sid": l.call_sid,
                "business_id": l.business_id,
                "recipient_phone": l.recipient_phone,
                "caller_id": l.caller_id,
                "status": l.status,
                "duration_seconds": l.duration_seconds,
                "recording_url": l.recording_url,
                "language": l.language,
                "qualification_intent": l.qualification_intent,
                "action_taken": l.action_taken,
                "transcript": l.transcript,
                "created_at": l.created_at.isoformat() if l.created_at else None
            } for l in logs]

    @classmethod
    async def get_meetings(cls, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves scheduled appointments."""
        async with AsyncSessionLocal() as db:
            q = select(Meeting).order_by(desc(Meeting.scheduled_time)).limit(limit)
            meetings = (await db.execute(q)).scalars().all()
            return [{
                "id": m.id,
                "business_id": m.business_id,
                "prospect_name": m.prospect_name,
                "prospect_contact": m.prospect_contact,
                "title": m.title,
                "scheduled_time": m.scheduled_time.isoformat() if m.scheduled_time else None,
                "duration_minutes": m.duration_minutes,
                "meeting_url": m.meeting_url,
                "status": m.status,
                "notes": m.notes
            } for m in meetings]
