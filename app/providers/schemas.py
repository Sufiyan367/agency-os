from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class MessageDeliveryResult(BaseModel):
    message_id: str
    recipient: str
    channel: str
    status: str = Field("DELIVERED", description="MOCKED_SENT, DELIVERED, FAILED")
    sent_at: datetime
    is_mocked: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
