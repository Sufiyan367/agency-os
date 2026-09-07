from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo  # type: ignore

from app.core.logging import logger

COUNTRY_TIMEZONE_FALLBACKS = {
    "US": ("America/New_York", -5),
    "UK": ("Europe/London", 0),
    "CA": ("America/Toronto", -5),
    "AU": ("Australia/Sydney", 10),
    "AE": ("Asia/Dubai", 4),
    "SA": ("Asia/Riyadh", 3),
    "DE": ("Europe/Berlin", 1),
    "FR": ("Europe/Paris", 1),
    "NL": ("Europe/Amsterdam", 1),
    "SE": ("Europe/Stockholm", 1),
    "SG": ("Asia/Singapore", 8),
    "JP": ("Asia/Tokyo", 9),
    "NZ": ("Pacific/Auckland", 12),
    "IE": ("Europe/Dublin", 0),
    "ES": ("Europe/Madrid", 1),
    "IT": ("Europe/Rome", 1),
    "CH": ("Europe/Zurich", 1),
    "QA": ("Asia/Qatar", 3),
}


class CampaignScheduler:
    """Evaluates country-aware business hours and local recipient sending windows."""

    def get_local_time(
        self,
        country_code: str,
        timezone_str: Optional[str] = None,
        now_utc: Optional[datetime] = None
    ) -> Tuple[datetime, str]:
        """Resolves local recipient datetime and canonical timezone string."""
        now = now_utc or datetime.now(timezone.utc)
        code = (country_code or "US").strip().upper()
        tz_name = timezone_str or COUNTRY_TIMEZONE_FALLBACKS.get(code, ("UTC", 0))[0]

        try:
            tz = zoneinfo.ZoneInfo(tz_name)
            local_dt = now.astimezone(tz)
            return local_dt, tz_name
        except Exception:
            offset_h = COUNTRY_TIMEZONE_FALLBACKS.get(code, ("UTC", 0))[1]
            local_dt = now + timedelta(hours=offset_h)
            return local_dt, tz_name

    def is_within_sending_window(
        self,
        country_code: str,
        timezone_str: Optional[str] = None,
        window_start: int = 9,
        window_end: int = 17,
        now_utc: Optional[datetime] = None,
        current_time: Optional[datetime] = None,
    ) -> Tuple[bool, datetime, int, str]:
        """
        Determines whether the recipient's local time is strictly within the allowed sending window.
        Returns: (is_allowed, local_datetime, local_hour, timezone_name)
        """
        eval_time = current_time or now_utc
        local_dt, tz_name = self.get_local_time(country_code, timezone_str, eval_time)
        hour = local_dt.hour

        # Check window: window_start <= hour < window_end
        is_allowed = (window_start <= hour < window_end)
        return is_allowed, local_dt, hour, tz_name


campaign_scheduler = CampaignScheduler()
