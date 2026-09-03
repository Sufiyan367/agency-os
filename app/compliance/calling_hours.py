"""
Calling Hours & Timezone Compliance Engine.
Enforces TCPA and international regulations: outbound marketing & consultation calls
may only be placed during allowed commercial business hours (08:00 to 20:00 local time).
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from pydantic import BaseModel
import re

from app.core.config import settings


class CallingWindowResult(BaseModel):
    is_allowed: bool
    reason: str
    local_time_iso: str
    local_hour: int
    prospect_timezone: str


class CallingHoursCompliance:
    """Evaluates whether an outbound sales call is legally permissible based on prospect local time."""

    # Timezone offsets in hours relative to UTC
    COUNTRY_CITY_OFFSETS = {
        "US": {
            "default": -5,  # Eastern
            "cities": {
                "new york": -5, "miami": -5, "atlanta": -5, "boston": -5,
                "chicago": -6, "dallas": -6, "houston": -6, "austin": -6,
                "denver": -7, "phoenix": -7, "salt lake city": -7,
                "los angeles": -8, "san francisco": -8, "seattle": -8, "san diego": -8
            }
        },
        "UK": {"default": 0},
        "CA": {
            "default": -5,
            "cities": {"toronto": -5, "montreal": -5, "calgary": -7, "vancouver": -8}
        },
        "AU": {
            "default": 10,
            "cities": {"sydney": 10, "melbourne": 10, "brisbane": 10, "perth": 8}
        },
        "AE": {"default": 4},   # UAE (Dubai, Abu Dhabi)
        "SA": {"default": 3}    # Saudi Arabia (Riyadh, Jeddah)
    }

    @classmethod
    def resolve_timezone_offset(
        cls,
        country: Optional[str] = "US",
        city: Optional[str] = None,
        phone: Optional[str] = None
    ) -> Tuple[int, str]:
        """Resolves UTC offset in hours and human-readable timezone label."""
        c_code = (country or "US").strip().upper()
        if c_code in ("USA", "UNITED STATES"):
            c_code = "US"
        elif c_code in ("UNITED KINGDOM", "ENGLAND", "GB"):
            c_code = "UK"
        elif c_code in ("UAE", "UNITED ARAB EMIRATES"):
            c_code = "AE"
        elif c_code in ("SAUDI ARABIA", "KSA"):
            c_code = "SA"
        elif c_code == "CANADA":
            c_code = "CA"
        elif c_code == "AUSTRALIA":
            c_code = "AU"

        tz_info = cls.COUNTRY_CITY_OFFSETS.get(c_code, {"default": -5})
        offset = tz_info.get("default", -5)
        tz_name = f"UTC{'+' if offset >= 0 else ''}{offset}:00"

        if city and "cities" in tz_info:
            city_norm = city.strip().lower()
            if city_norm in tz_info["cities"]:
                offset = tz_info["cities"][city_norm]
                tz_name = f"{city.title()} (UTC{'+' if offset >= 0 else ''}{offset}:00)"

        return offset, tz_name

    @classmethod
    def is_calling_window_open(
        cls,
        country: Optional[str] = "US",
        city: Optional[str] = None,
        phone: Optional[str] = None,
        current_utc_time: Optional[datetime] = None
    ) -> CallingWindowResult:
        """
        Determines if outbound call is permitted within allowed calling window (default: 8 AM - 8 PM local).
        """
        if not getattr(settings, "ENFORCE_CALLING_HOURS", True):
            now_utc = current_utc_time or datetime.now(timezone.utc)
            return CallingWindowResult(
                is_allowed=True,
                reason="Calling hours compliance enforcement is disabled in settings.",
                local_time_iso=now_utc.isoformat(),
                local_hour=now_utc.hour,
                prospect_timezone="UTC"
            )

        now_utc = current_utc_time or datetime.now(timezone.utc)
        offset_hours, tz_name = cls.resolve_timezone_offset(country=country, city=city, phone=phone)
        local_dt = now_utc + timedelta(hours=offset_hours)
        local_hour = local_dt.hour

        start_h = getattr(settings, "CALLING_HOURS_START", 8)
        end_h = getattr(settings, "CALLING_HOURS_END", 20)

        if start_h <= local_hour < end_h:
            return CallingWindowResult(
                is_allowed=True,
                reason=f"Within permitted calling window ({start_h:02d}:00 - {end_h:02d}:00 local time).",
                local_time_iso=local_dt.strftime("%Y-%m-%d %H:%M:%S"),
                local_hour=local_hour,
                prospect_timezone=tz_name
            )

        return CallingWindowResult(
            is_allowed=False,
            reason=(
                f"Outside permitted calling window. Local prospect time is {local_dt.strftime('%I:%M %p')} ({tz_name}). "
                f"Telephony compliance restricts outbound calls to {start_h:02d}:00 - {end_h:02d}:00."
            ),
            local_time_iso=local_dt.strftime("%Y-%m-%d %H:%M:%S"),
            local_hour=local_hour,
            prospect_timezone=tz_name
        )


calling_hours_compliance = CallingHoursCompliance()
