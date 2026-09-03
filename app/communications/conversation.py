"""
Conversation State and Message History Models.
Tracks multi-turn interactions, message timestamps, sentiment, and channel type.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.communications.router import ChannelType


class ConversationMessage(BaseModel):
    message_id: str
    sender: str  # 'AGENT', 'PROSPECT', 'HUMAN_OPERATOR'
    channel: ChannelType
    content: str
    language: str = "en"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    intent: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConversationSession(BaseModel):
    session_id: str
    business_id: Optional[int] = None
    business_name: str
    channel: ChannelType
    language: str = "en"
    messages: List[ConversationMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    handed_off_to_human: bool = False

    def add_message(
        self,
        sender: str,
        content: str,
        intent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ConversationMessage:
        msg = ConversationMessage(
            message_id=f"msg_{len(self.messages) + 1}_{int(datetime.utcnow().timestamp())}",
            sender=sender,
            channel=self.channel,
            content=content,
            language=self.language,
            intent=intent,
            metadata=metadata or {}
        )
        self.messages.append(msg)
        self.updated_at = datetime.utcnow()
        return msg
