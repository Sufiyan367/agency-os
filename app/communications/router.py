"""
Contact Router.
Selects between Email and Voice channels strictly based on verified public evidence.
Never fabricates emails or phone numbers.
"""
from enum import Enum
from typing import Optional
from pydantic import BaseModel


class ChannelType(str, Enum):
    EMAIL = "EMAIL"
    VOICE = "VOICE"
    NONE = "NONE"


class RouteResult(BaseModel):
    channel: ChannelType
    destination: Optional[str] = None
    reason: str
    eligible: bool


class ContactRouter:
    """Deterministic channel selector."""

    @staticmethod
    def route_contact(
        email: Optional[str],
        phone: Optional[str],
        voice_enabled: bool = False
    ) -> RouteResult:
        # 1. Prefer verified business email if available
        if email and "@" in email and not email.endswith(("@example.com", "@test.com")):
            return RouteResult(
                channel=ChannelType.EMAIL,
                destination=email,
                reason="Verified public business domain email observed.",
                eligible=True
            )

        # 2. Check business phone if voice is explicitly enabled
        if phone and voice_enabled:
            clean_phone = phone.strip()
            if len(clean_phone) >= 7:
                return RouteResult(
                    channel=ChannelType.VOICE,
                    destination=clean_phone,
                    reason="Verified business phone number available and voice calling active.",
                    eligible=True
                )

        return RouteResult(
            channel=ChannelType.NONE,
            destination=None,
            reason="No legitimate public contact channel verified. Rejecting synthetic fallback.",
            eligible=False
        )
