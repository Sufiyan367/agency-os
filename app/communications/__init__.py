"""
Communications module for autonomous email, voice, and conversational messaging.
"""
from app.communications.whatsapp_adapter import whatsapp_adapter, WhatsAppAdapter
from app.communications.voice_adapter import voice_adapter, VoiceAdapter
from app.communications.voicebox_client import voicebox_client, VoiceboxClient
from app.communications.email_adapter import email_adapter, EmailAdapter
from app.communications.normalizer import conversation_normalizer, ConversationNormalizer
from app.communications.eligibility import channel_eligibility_engine, ChannelEligibilityEngine

__all__ = [
    "whatsapp_adapter",
    "WhatsAppAdapter",
    "voice_adapter",
    "VoiceAdapter",
    "voicebox_client",
    "VoiceboxClient",
    "email_adapter",
    "EmailAdapter",
    "conversation_normalizer",
    "ConversationNormalizer",
    "channel_eligibility_engine",
    "ChannelEligibilityEngine",
]
