# app.outreach module
from app.outreach.personalization import outreach_personalizer
from app.outreach.queue import outreach_approval_queue
from app.outreach.sender import outreach_sender_adapter
from app.outreach.compliance import compliance_guard

__all__ = [
    "outreach_personalizer",
    "outreach_approval_queue",
    "outreach_sender_adapter",
    "compliance_guard"
]
